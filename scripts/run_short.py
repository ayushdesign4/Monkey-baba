#!/usr/bin/env python3
"""Monkey-Baba × ZeroCost-Shorts Orchestrator.
Fully automated YouTube Shorts pipeline for English horror storytelling.

Stages:
  1. Load config & validate environment
  2. Pick topic & enforce duplicate protection
  3. Reserve topic in data/topic_history.json
  4. Generate script (Groq -> deterministic local fallback)
  5. Validate story consistency (topic <-> title <-> narration <-> scenes)
  6. Generate 9:16 vertical visual assets (DeAPI / HF / Pollinations / PIL)
  7. Enforce Visual Quality Policy (block upload if procedural placeholders used without flag)
  8. Synthesize audio with Edge TTS
  9. Build captions SRT
  10. Assemble vertical short with FFmpeg (Ken Burns zoompan + fadeblack)
  11. Visual Quality Gate validation (aspect ratio, duration 30-60s, frames)
  12. Re-check duplicate history before upload
  13. Upload to YouTube via OAuth2 (strictly disabled in dry-run mode)
  14. Save upload history & update topic state
  15. Send rich SMTP notification email (strictly skipped in dry-run mode)
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env")
load_dotenv(REPO_ROOT / "scripts" / ".env")

from pipeline.captions import build_srt
from pipeline.channel_presets import get_preset, list_channel_ids
from pipeline.edge_tts_synth import adjust_audio_tempo_if_needed, synthesize_full
from pipeline.email_notifier import send_pipeline_failure_email, send_upload_success_email
from pipeline.groq_script import generate_short_pack
from pipeline.images import (
    DEFAULT_NEGATIVE,
    full_visual_prompt,
    save_scene_image,
    validate_visual_quality_policy,
)
from pipeline.quality_gate import validate_short_quality
from pipeline.render_short import render_vertical_short
from pipeline.story_validator import validate_story_consistency
from pipeline.story_history import (
    check_duplicate,
    compute_file_sha256,
    compute_fingerprint,
    is_video_already_uploaded,
    record_upload,
    reserve_topic,
    save_run_state,
    update_notification_status,
    update_topic_status,
)


def run_pipeline(
    channel_id: str = "horror",
    topic_override: str = "",
    upload_enabled: bool = False,
    dry_run: bool = False,
    privacy: str = "private",
    run_id: str = "manual",
    run_url: str = "",
    allow_procedural_fallback: bool = False,
) -> dict:
    """Execute the full end-to-end Short generation and upload pipeline."""
    preset = get_preset(channel_id)
    stages_passed: list[str] = []
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = REPO_ROOT / "output" / "runs" / f"{channel_id}_{ts}"
    img_dir = run_dir / "images"
    img_dir.mkdir(parents=True, exist_ok=True)

    topic_id = ""
    topic_title = ""
    selected_topic = ""
    upload_attempted = False

    # Check dry-run environment flag
    is_dry_run = dry_run or os.environ.get("DRY_RUN", "false").lower() in ("true", "1", "yes")
    should_upload = bool(upload_enabled and not is_dry_run)

    # Check procedural fallback permission
    allow_procedural = (
        allow_procedural_fallback
        or os.environ.get("ALLOW_PROCEDURAL_FALLBACK", "false").lower() in ("true", "1", "yes")
    )

    if is_dry_run:
        print("[DRY_RUN] Dry-run mode active: YouTube upload and live email notifications are strictly disabled.")

    # Initialize run state
    save_run_state({
        "run_id": run_id,
        "channel": channel_id,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "stage": "started",
        "status": "in_progress",
        "dry_run": is_dry_run,
        "allow_procedural_fallback": allow_procedural,
    })

    try:
        # ── 1. Topic selection & deduplication ───────────────────────────
        print(f"[STAGE 1] Selecting topic for channel '{channel_id}'...")
        candidate_pool = list(preset.get("topic_pool") or [])
        random.shuffle(candidate_pool)

        if topic_override.strip():
            candidates = [topic_override.strip()]
        else:
            candidates = candidate_pool if candidate_pool else ["A chilling midnight encounter"]

        for cand in candidates:
            is_dup, reason = check_duplicate(cand)
            if not is_dup:
                selected_topic = cand
                break
            else:
                print(f"   [DEDUP] Skipping duplicate candidate '{cand}': {reason}")

        if not selected_topic:
            # Generate randomized variation if all pool entries were exhausted
            selected_topic = f"{random.choice(candidates)} (unexplained anomaly {ts[-4:]})"
            print(f"   [DEDUP] Using fresh topic variation: {selected_topic}")

        print(f"   Selected Topic: {selected_topic}")

        # Reserve topic before expensive generation
        topic_title = selected_topic
        topic_id = reserve_topic(
            topic_title=topic_title,
            summary="",
            run_id=run_id,
            story_type=preset.get("niche", "horror"),
        )
        print(f"   Reserved Topic ID: {topic_id}")
        stages_passed.append("Topic Selection & Dedup")

        # ── 2. Script generation via Groq (with local fallback) ─────────
        print("\n[STAGE 2] Generating script & scene prompts...")
        pack = generate_short_pack(preset, topic_hint=selected_topic, channel_id=channel_id)
        (run_dir / "script.json").write_text(json.dumps(pack, indent=2, ensure_ascii=False), encoding="utf-8")

        title = pack.get("youtube_title", "").strip()
        description = pack.get("youtube_description", "").strip()
        narration = pack.get("full_narration", "").strip()
        image_prompts = pack.get("image_prompts", [])
        provider = pack.get("_provider", "unknown")
        model_used = pack.get("_model", "unknown")

        print(f"   [SCRIPT PROVIDER] Generated via: {provider} (model: {model_used})")
        print(f"   Title: {title}")
        word_count = len(narration.split())
        min_words = preset.get("min_words", 100)
        print(f"   Narration word count: {word_count} (minimum required: {min_words})")
        print(f"   Scenes count: {len(image_prompts)}")

        if word_count < min_words:
            raise ValueError(f"Script word count {word_count} < required {min_words}")
        if not (6 <= len(image_prompts) <= 8):
            print(f"   [WARN] Image prompts count is {len(image_prompts)}, target is 6-8")

        # ── 2b. Story consistency validation ────────────────────────────
        print("\n   Validating story topic-title-script-scenes consistency...")
        validate_story_consistency(selected_topic, title, narration, image_prompts)
        print("   [CONSISTENCY] Story consistency check passed.")

        # Update topic record with generated script fingerprint
        update_topic_status(topic_id, "generated", script=narration)
        stages_passed.append("Script Generation")

        # ── 3. Visual asset generation (vertical 9:16) ──────────────────
        print(f"\n[STAGE 3] Generating {len(image_prompts)} visual scenes (9:16 vertical)...")
        w = int(os.environ.get("IMAGE_WIDTH", "720"))
        h = int(os.environ.get("IMAGE_HEIGHT", "1280"))
        style_suffix = preset.get("image_style_suffix")
        negative = preset.get("image_negative_prompt", DEFAULT_NEGATIVE)
        cooldown = int(os.environ.get("IMAGE_COOLDOWN", "1"))

        image_paths: list[Path] = []
        scene_manifest: dict[int, str] = {}

        for i, prompt_text in enumerate(image_prompts):
            full_prompt = full_visual_prompt(prompt_text, style_suffix=style_suffix)
            out_img = img_dir / f"scene_{i + 1:02d}.png"
            status, detail = save_scene_image(i + 1, full_prompt, out_img, width=w, height=h, negative=negative)
            if status != "ok":
                raise RuntimeError(f"Failed to generate scene {i + 1}: {detail}")
            provider_name = detail.split()[0]
            scene_manifest[i + 1] = detail
            print(f"   Scene {i + 1}/{len(image_prompts)}: provider={detail}")
            image_paths.append(out_img)
            if i < len(image_prompts) - 1 and cooldown > 0:
                time.sleep(cooldown)

        # ── 3b. Enforce Visual Quality Policy ───────────────────────────
        print("\n   Enforcing visual quality policy against scene manifest...")
        validate_visual_quality_policy(scene_manifest, allow_procedural=allow_procedural)
        print("   [VISUAL POLICY] Visual quality policy passed.")
        stages_passed.append("Visual Assets")

        # ── 4. Edge TTS voiceover synthesis ─────────────────────────────
        print("\n[STAGE 4] Synthesizing voiceover narration with Edge TTS...")
        audio_path = run_dir / "voiceover.mp3"
        voice = preset.get("tts_voice") or os.environ.get("EDGE_TTS_VOICE") or "en-US-ChristopherNeural"
        rate = preset.get("tts_rate") or os.environ.get("EDGE_TTS_RATE", "+10%")
        total_dur, sentence_timings = synthesize_full(narration, audio_path, voice=voice, rate=rate)
        print(f"   Raw audio duration: {total_dur:.1f}s ({len(sentence_timings)} sentences tracked)")

        # Enforce bounded duration (45-55s target, strictly 30-58s) with atempo adjustment if needed
        total_dur, sentence_timings = adjust_audio_tempo_if_needed(
            audio_path,
            sentence_timings,
            min_target=45.0,
            max_target=55.0,
            absolute_max=58.0,
            absolute_min=30.0,
        )
        print(f"   Final narration duration: {total_dur:.1f}s")

        stages_passed.append("TTS Narration")

        # ── 5. Captions generation ──────────────────────────────────────
        print("\n[STAGE 5] Building subtitles SRT...")
        srt_path = run_dir / "captions.srt"
        build_srt(sentence_timings, srt_path, total_dur)
        stages_passed.append("Captions")

        # ── 6. Assemble vertical Short with FFmpeg ──────────────────────
        print("\n[STAGE 6] Rendering 1080×1920 vertical Short with FFmpeg...")
        video_path = run_dir / "short_horror.mp4"
        font_file = preset.get("caption_font", "CreepsterCaps.ttf")
        font_name = preset.get("caption_font_name", "Creepster")

        render_vertical_short(
            image_paths,
            total_dur,
            audio_path,
            srt_path,
            video_path,
            width=1080,
            height=1920,
            font_file=font_file,
            font_name=font_name,
        )
        file_size = video_path.stat().st_size if video_path.is_file() else 0
        print(f"   Rendered video: {video_path} ({file_size} bytes)")
        stages_passed.append("FFmpeg Render")

        # ── 7. Visual Quality Gate ──────────────────────────────────────
        print("\n[STAGE 7] Executing Visual Quality Gate (strict 30.0–60.0s requirement)...")
        qg_result = validate_short_quality(
            video_path,
            min_duration=30.0,
            max_duration=60.0,
            enforce_vertical=True,
            check_frames=True,
        )
        if not qg_result.passed:
            raise RuntimeError(f"Visual quality gate failed: {'; '.join(qg_result.errors)}")

        print(f"   Quality gate PASSED (Duration: {qg_result.duration:.1f}s, Res: {qg_result.width}x{qg_result.height})")
        stages_passed.append("Visual Quality Gate")

        # ── 8. Duplicate check before upload ────────────────────────────
        print("\n[STAGE 8] Pre-upload duplicate check...")
        video_sha256 = compute_file_sha256(video_path) if video_path.is_file() else "mock_sha256"
        is_dup_vid, dup_vid_reason = is_video_already_uploaded(None, video_sha256)

        if is_dup_vid:
            raise RuntimeError(f"Duplicate video check failed: {dup_vid_reason}")

        stages_passed.append("Pre-upload Verification")

        # ── 9. YouTube upload ───────────────────────────────────────────
        video_id = ""
        summary_text = " ".join(narration.split()[:28]) + "..."

        if should_upload:
            print("\n[STAGE 9] Uploading video to YouTube...")
            upload_attempted = True
            from pipeline.youtube_upload import upload_short

            tags = [
                "horror", "scary stories", "horror shorts", "creepy",
                "urban legends", "short horror story", "mystery",
            ]
            video_id = upload_short(
                video_path,
                title,
                description,
                tags=tags,
                privacy_status=privacy,
                refresh_token_env=preset.get("yt_token_env", "YT_REFRESH_TOKEN"),
            )
            print(f"   UPLOAD CONFIRMED: https://www.youtube.com/watch?v={video_id}")
            stages_passed.append("YouTube Upload")
        else:
            sim_id = f"sim_{ts[-8:]}"
            video_id = sim_id
            print(f"\n[STAGE 9] Upload SKIPPED (dry-run={is_dry_run}, upload_enabled={upload_enabled}). Simulated ID: {sim_id}")
            stages_passed.append("Upload (Simulated)")

        # ── 10. Record upload history ───────────────────────────────────
        print("\n[STAGE 10] Persisting state to data/...")
        record_upload(
            video_id=video_id,
            title=title,
            topic_id=topic_id,
            story_fingerprint=compute_fingerprint(narration),
            video_sha256=video_sha256,
            duration_seconds=qg_result.duration,
            run_id=run_id,
            language="en",
            niche=preset.get("niche", "horror"),
            dry_run=not should_upload,
            notification_status="pending",
        )

        # ── 11. Send SMTP notification email ────────────────────────────
        print("\n[STAGE 11] Sending notification email...")
        if should_upload:
            email_ok, email_msg = send_upload_success_email(
                title=title,
                video_id=video_id,
                summary=summary_text,
                duration_seconds=qg_result.duration,
                run_id=run_id,
                run_url=run_url,
                niche="Horror Storytelling",
                stages_passed=stages_passed,
            )
            print(f"   Email notification: {email_msg}")
            update_notification_status(video_id, "sent" if email_ok else "failed")
        else:
            print("   [DRY_RUN] Dry-run mode: skipping live success email.")
            update_notification_status(video_id, "skipped")

        # Save finished run state
        save_run_state({
            "run_id": run_id,
            "channel": channel_id,
            "started_at_utc": ts,
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "stage": "completed",
            "status": "success",
            "topic_id": topic_id,
            "video_id": video_id,
            "upload_status": "uploaded" if should_upload else "simulated",
            "dry_run": is_dry_run,
            "script_provider": provider,
            "script_model": model_used,
            "scene_manifest": scene_manifest,
            "video_path": str(video_path),
        })

        print("\nPipeline execution finished successfully.")
        return {
            "status": "success",
            "title": title,
            "video_id": video_id,
            "video_url": f"https://www.youtube.com/watch?v={video_id}",
            "duration": qg_result.duration,
            "topic_id": topic_id,
            "stages_passed": stages_passed,
            "dry_run": is_dry_run,
            "script_provider": provider,
        }

    except Exception as exc:
        print(f"\n[ERROR] Pipeline failed: {exc}", file=sys.stderr)
        if topic_id:
            update_topic_status(topic_id, "failed")

        save_run_state({
            "run_id": run_id,
            "channel": channel_id,
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "stage": "failed",
            "status": "failed",
            "topic_id": topic_id,
            "dry_run": is_dry_run,
            "last_error_summary": str(exc)[:300],
        })

        # Only attempt to send failure alert if not in dry-run mode and upload was attempted or ambiguous
        if not is_dry_run:
            try:
                send_pipeline_failure_email(
                    failed_stage=stages_passed[-1] if stages_passed else "Initialization",
                    error_summary=str(exc),
                    topic_title=topic_title,
                    run_id=run_id,
                    run_url=run_url,
                    upload_attempted=upload_attempted,
                )
            except Exception as e_mail:
                print(f"[WARN] Failed to send failure email: {e_mail}")
        else:
            print("   [DRY_RUN] Dry-run mode: skipping failure email alert.")

        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate and upload horror storytelling YouTube Short.")
    parser.add_argument("--channel", default="horror", choices=list_channel_ids())
    parser.add_argument("--topic", default="", help="Optional specific topic prompt")
    parser.add_argument("--upload", action="store_true", help="Enable actual upload to YouTube")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without publishing to YouTube")
    parser.add_argument(
        "--allow-procedural-fallback",
        action="store_true",
        help="Explicitly permit procedural visual placeholders if AI image generation fails",
    )
    parser.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
    parser.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", "manual_run"))
    parser.add_argument(
        "--run-url",
        default=os.environ.get(
            "GITHUB_RUN_URL",
            f"https://github.com/{os.environ.get('GITHUB_REPOSITORY', 'ayushdesign4/Monkey-baba')}/actions",
        ),
    )
    args = parser.parse_args()

    # If --dry-run is passed, upload is strictly disabled
    is_dry_run = args.dry_run or os.environ.get("DRY_RUN", "false").lower() in ("true", "1", "yes")
    upload_enabled = args.upload and not is_dry_run

    run_pipeline(
        channel_id=args.channel,
        topic_override=args.topic,
        upload_enabled=upload_enabled,
        dry_run=is_dry_run,
        privacy=args.privacy,
        run_id=args.run_id,
        run_url=args.run_url,
        allow_procedural_fallback=args.allow_procedural_fallback,
    )


if __name__ == "__main__":
    main()
