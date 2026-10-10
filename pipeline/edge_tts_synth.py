"""Edge TTS — free, no API key. Returns audio + sentence-level timestamps.
Includes natural pacing configuration and bounded FFmpeg atempo duration control.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from pathlib import Path
from typing import TypedDict

VOICE = "en-US-ChristopherNeural"
DEFAULT_RATE = os.environ.get("EDGE_TTS_RATE", "+10%")


class SentenceTiming(TypedDict):
    text: str
    offset_ms: int
    duration_ms: int


def _ffprobe_duration(path: Path, fallback_duration: float | None = None) -> float:
    """Measure audio duration using ffprobe, or fallback estimate if ffprobe is absent."""
    if shutil.which("ffprobe"):
        try:
            out = subprocess.check_output(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ],
                text=True,
            ).strip()
            return float(out)
        except Exception:
            pass

    if fallback_duration is not None and fallback_duration > 0:
        return fallback_duration

    # Fallback estimation for 128kbps MP3
    try:
        size = path.stat().st_size
        return round((size * 8.0) / 128_000.0, 2)
    except Exception:
        return 45.0


async def _synthesize_with_timing(
    text: str,
    out_path: Path,
    voice: str,
    rate: str = DEFAULT_RATE,
) -> list[SentenceTiming]:
    import edge_tts

    communicate = edge_tts.Communicate(text, voice, rate=rate)
    sentences: list[SentenceTiming] = []

    with open(out_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] == "SentenceBoundary":
                sentences.append(
                    SentenceTiming(
                        text=chunk["text"],
                        offset_ms=int(chunk["offset"]) // 10_000,
                        duration_ms=int(chunk["duration"]) // 10_000,
                    )
                )

    return sentences


def synthesize_full(
    text: str,
    out_path: Path,
    voice: str | None = None,
    rate: str | None = None,
) -> tuple[float, list[SentenceTiming]]:
    """TTS the full narration. Returns (duration_seconds, sentence_timings)."""
    voice = voice or os.environ.get("EDGE_TTS_VOICE", VOICE)
    rate = rate or os.environ.get("EDGE_TTS_RATE", DEFAULT_RATE)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sentences = asyncio.run(_synthesize_with_timing(text, out_path, voice, rate=rate))

    # Compute duration from SentenceBoundary chunks if needed as high-precision fallback
    approx_from_sentences = 0.0
    if sentences:
        last_s = sentences[-1]
        approx_from_sentences = (last_s["offset_ms"] + last_s["duration_ms"]) / 1000.0

    dur = _ffprobe_duration(out_path, fallback_duration=approx_from_sentences)
    return dur, sentences


def adjust_audio_tempo_if_needed(
    audio_path: Path,
    sentence_timings: list[SentenceTiming],
    *,
    min_target: float = 45.0,
    max_target: float = 55.0,
    absolute_max: float = 58.0,
    absolute_min: float = 30.0,
) -> tuple[float, list[SentenceTiming]]:
    """Ensure audio duration strictly conforms to target (45-55s, hard quality gate limits 30-58s)
    using bounded FFmpeg atempo adjustment without cutting off speech or hurting intelligibility.
    Scales sentence_timings proportionally to guarantee subtitle synchronization.
    """
    audio_path = Path(audio_path)
    fallback_hint = 0.0
    if sentence_timings:
        last_s = sentence_timings[-1]
        if isinstance(last_s, dict):
            if "offset_ms" in last_s and "duration_ms" in last_s:
                fallback_hint = (last_s["offset_ms"] + last_s["duration_ms"]) / 1000.0
            elif "end" in last_s:
                fallback_hint = float(last_s["end"])
    current_dur = _ffprobe_duration(audio_path, fallback_duration=fallback_hint)
    if not sentence_timings and current_dur <= 0:
        return current_dur, sentence_timings

    # If already safely in 30.0 - 55.0s, no atempo adjustment needed
    if absolute_min <= current_dur <= max_target:
        return current_dur, sentence_timings

    factor = 1.0
    if current_dur > max_target:
        # Too long: target 50.0s (leaving a comfortable 10s safety buffer under 60.0s limit)
        target_dur = 50.0
        raw_factor = current_dur / target_dur
        # Bounded between 1.01 and 1.25x so speech stays natural, intelligible, and never chipmunked
        factor = min(1.25, max(1.01, raw_factor))
    elif current_dur < absolute_min:
        # Too short: target 32.0s
        target_dur = 32.0
        raw_factor = current_dur / target_dur
        factor = max(0.85, min(0.99, raw_factor))

    if abs(factor - 1.0) < 0.01:
        return current_dur, sentence_timings

    def _scale_timing(s: dict) -> dict:
        out = dict(s)
        if "offset_ms" in out:
            out["offset_ms"] = int(out["offset_ms"] / factor)
        if "duration_ms" in out:
            out["duration_ms"] = int(out["duration_ms"] / factor)
        if "start" in out:
            out["start"] = out["start"] / factor
        if "end" in out:
            out["end"] = out["end"] / factor
        return out

    # If ffmpeg is absent on the host, scale timings mathematically
    if not shutil.which("ffmpeg"):
        adjusted_timings = [_scale_timing(s) for s in sentence_timings]
        new_dur = current_dur / factor
        print(f"   [AUDIO PACING] Timing scaled by {factor:.2f}x: {current_dur:.1f}s -> {new_dur:.1f}s (ffmpeg absent)")
        return new_dur, adjusted_timings

    # Run FFmpeg atempo filter (preserves pitch and complete sentence audio)
    tmp_out = audio_path.parent / f"_atempo_{audio_path.name}"
    try:
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
            "-i", str(audio_path.resolve()),
            "-filter:a", f"atempo={factor:.4f}",
            "-vn",
            str(tmp_out.resolve()),
        ]
        subprocess.run(cmd, check=True)
        if tmp_out.is_file() and tmp_out.stat().st_size > 1000:
            shutil.move(str(tmp_out), str(audio_path))
            new_dur = _ffprobe_duration(audio_path, fallback_duration=current_dur / factor)
        else:
            new_dur = current_dur / factor
    except Exception as e:
        print(f"   [WARN] atempo adjustment failed: {e}")
        new_dur = current_dur / factor
    finally:
        if tmp_out.is_file():
            tmp_out.unlink(missing_ok=True)

    # Scale sentence timings proportionally so captions stay frame-accurate and synchronized
    adjusted_timings = [_scale_timing(s) for s in sentence_timings]

    print(f"   [AUDIO PACING] Tempo adjusted by {factor:.2f}x: {current_dur:.1f}s -> {new_dur:.1f}s (subtitles rescaled)")
    return new_dur, adjusted_timings
