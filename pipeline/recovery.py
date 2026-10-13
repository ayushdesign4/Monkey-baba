"""Additive recovery and error-handling architecture for Monkey-Baba.

Provides:
  1. Error classification (Transient, Safety Rejection, Unsupported Model, Format, Media, Auth)
  2. RunStatus state management (PUBLISHED, RECOVERED_PUBLISHED, DRY_RUN_SUCCESS, etc.)
  3. Safety-aware prompt rewriting for horror image generation
  4. Thematic/semantic premise matching for story consistency
  5. Scene omission & timeline rebalancing for image generation failures
  6. Idempotent upload reconciliation
  7. Recovery action tracking and diagnostics
"""
from __future__ import annotations

import enum
import re
from pathlib import Path
from typing import Any


class ErrorCategory(str, enum.Enum):
    TRANSIENT = "transient"
    UNSUPPORTED_MODEL = "unsupported_model"
    PROMPT_SAFETY_REJECTION = "prompt_safety_rejection"
    LLM_FORMAT = "llm_format"
    SEMANTIC_MISMATCH = "semantic_mismatch"
    SCENE_UNAVAILABLE = "scene_unavailable"
    MEDIA_INTEGRITY = "media_integrity"
    AUTH_PERMANENT = "auth_permanent"
    UNKNOWN = "unknown"


class RunStatus(str, enum.Enum):
    PUBLISHED = "PUBLISHED"
    PUBLISHED_PROCESSING = "PUBLISHED_PROCESSING"
    RECOVERED_PUBLISHED = "RECOVERED_PUBLISHED"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    FAILED_ACTION_REQUIRED = "FAILED_ACTION_REQUIRED"
    DRY_RUN_SUCCESS = "DRY_RUN_SUCCESS"
    DRY_RUN_FAILED = "DRY_RUN_FAILED"


# ─────────────────────────────────────────────────────────────────────────────
# 1. Error Classification
# ─────────────────────────────────────────────────────────────────────────────

def classify_error(err: Exception | str) -> ErrorCategory:
    """Classify an exception or error string into an actionable ErrorCategory."""
    err_str = str(err).lower()

    # Permanent auth / quota / payment errors
    if any(k in err_str for k in ("401", "unauthorized", "invalid_api_key", "402", "payment required", "403", "forbidden", "access denied")):
        return ErrorCategory.AUTH_PERMANENT

    # Safety / Content Policy rejections (HTTP 400 with moderation triggers)
    if any(k in err_str for k in ("safety", "content policy", "nsfw", "moderation", "prohibited", "filter", "prompt blocked")) or (
        "400" in err_str and any(k in err_str for k in ("bad request", "rejected", "policy", "content"))
    ):
        return ErrorCategory.PROMPT_SAFETY_REJECTION

    # Model not found / deprecated
    if any(k in err_str for k in ("404", "model_not_found", "model not found", "does not exist", "unsupported model", "deprecated")):
        return ErrorCategory.UNSUPPORTED_MODEL

    # Transient network / server / rate-limit errors
    if any(k in err_str for k in ("429", "rate limit", "500", "502", "503", "504", "timeout", "timed out", "connection", "network error", "econnreset")):
        return ErrorCategory.TRANSIENT

    # LLM formatting / JSON issues
    if any(k in err_str for k in ("jsondecodeerror", "unterminated string", "missing required field", "expecting value")):
        return ErrorCategory.LLM_FORMAT

    # Semantic divergence
    if any(k in err_str for k in ("story mismatch", "consistency", "divergence", "premise")):
        return ErrorCategory.SEMANTIC_MISMATCH

    # Media corruption / duration bounds
    if any(k in err_str for k in ("corrupt", "quality gate", "duration", "aspect ratio", "atempo", "ffmpeg")):
        return ErrorCategory.MEDIA_INTEGRITY

    # Scene generation failures
    if any(k in err_str for k in ("scene", "procedural", "image generator")):
        return ErrorCategory.SCENE_UNAVAILABLE

    return ErrorCategory.UNKNOWN


# ─────────────────────────────────────────────────────────────────────────────
# 2. Safety-Aware Prompt Rewriting
# ─────────────────────────────────────────────────────────────────────────────

# Horror concept replacements: softens graphic/prohibited physical violence/gore
# into eerie, psychological, and atmospheric imagery acceptable to image AI moderation.
SAFETY_REPLACEMENTS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(mutilated|severed|dismembered|disemboweled)\b", re.IGNORECASE), "grotesquely contorted"),
    (re.compile(r"\b(corpse|dead body|cadaver)\b", re.IGNORECASE), "motionless draped silhouette"),
    (re.compile(r"\b(bloody|covered in blood|blood-soaked|dripping blood)\b", re.IGNORECASE), "stained with dark shadows"),
    (re.compile(r"\b(blood|pool of blood)\b", re.IGNORECASE), "dark crimson gloom"),
    (re.compile(r"\b(gore|gory|carnage|viscera)\b", re.IGNORECASE), "macabre chilling decay"),
    (re.compile(r"\b(strangled|strangling|choked to death)\b", re.IGNORECASE), "trapped in breathless terror"),
    (re.compile(r"\b(hanging body|hung by the neck|hanged)\b", re.IGNORECASE), "suspended silhouette swaying gently"),
    (re.compile(r"\b(suicide|kill oneself)\b", re.IGNORECASE), "haunting tragic disappearance"),
    (re.compile(r"\b(murder|slaughter|massacre|killing)\b", re.IGNORECASE), "sinister eerie incident"),
    (re.compile(r"\b(murdered|slain|butchered)\b", re.IGNORECASE), "consumed by darkness"),
    (re.compile(r"\b(knife wound|stab wound|gaping wound|slashed throat)\b", re.IGNORECASE), "ominous scarred marks"),
    (re.compile(r"\b(decapitated|headless body)\b", re.IGNORECASE), "faceless veiled phantom"),
    (re.compile(r"\b(flesh|torn flesh)\b", re.IGNORECASE), "decayed fabric and bark"),
    (re.compile(r"\b(screaming in agony|screaming in pain)\b", re.IGNORECASE), "frozen in silent horror"),
    (re.compile(r"\b(torture|tortured)\b", re.IGNORECASE), "tormented by unseen presences"),
]


def rewrite_prompt_for_safety(prompt: str) -> str:
    """Softens explicit graphic/gore terms into psychological, atmospheric horror cues.
    Preserves visual composition, lighting, camera angles, and sinister mood
    while ensuring compliance with AI safety/moderation filters.
    """
    cleaned = prompt
    for pattern, replacement in SAFETY_REPLACEMENTS:
        cleaned = pattern.sub(replacement, cleaned)

    # Normalize double spaces that may result from replacement
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


# ─────────────────────────────────────────────────────────────────────────────
# 3. Thematic / Semantic Premise Broad Matching
# ─────────────────────────────────────────────────────────────────────────────

THEMATIC_SYNONYMS: dict[str, set[str]] = {
    "lake": {"water", "lake", "ocean", "sea", "pond", "depths", "surface", "shore", "tide", "reservoir", "waves", "still"},
    "water": {"water", "lake", "ocean", "sea", "pond", "depths", "surface", "shore", "tide", "reservoir", "submerged", "drowned"},
    "mirror": {"mirror", "reflection", "glass", "silver", "surface", "looking", "stare", "antique", "frame", "double", "gazing"},
    "doll": {"doll", "puppet", "toy", "mannequin", "porcelain", "figurine", "plaything", "effigy"},
    "forest": {"forest", "woods", "trees", "pines", "branches", "clearing", "cabin", "timber", "grove", "wilderness"},
    "house": {"house", "mansion", "home", "cabin", "manor", "residence", "estate", "attic", "basement", "room", "hallway"},
    "clock": {"clock", "time", "chime", "midnight", "hour", "pendulum", "ticks", "ticking", "watch"},
    "ghost": {"ghost", "spirit", "phantom", "specter", "spectre", "apparition", "shadow", "entity", "presence", "whisper"},
    "whisper": {"whisper", "voice", "sound", "murmur", "calling", "echo", "hiss", "breathe", "breathing"},
    "dream": {"dream", "nightmare", "sleep", "awake", "slumber", "waking", "vision"},
    "painting": {"painting", "portrait", "canvas", "frame", "artist", "brush", "eyes", "picture"},
    "stairs": {"stairs", "staircase", "steps", "basement", "cellar", "attic", "creak", "below", "underneath"},
    "storm": {"storm", "thunder", "lightning", "rain", "tempest", "clouds", "darkness", "night"},
    "shadow": {"shadow", "silhouette", "figure", "darkness", "shape", "outline", "shade"},
}


def semantic_premise_match(
    topic: str,
    title: str,
    script: str,
    scene_prompts: list[str] | None = None,
) -> bool:
    """Verify that topic, title, and script share coherent thematic concepts,
    expanding known horror domain synonyms to permit creative metaphors.
    """
    from pipeline.story_validator import extract_keywords

    topic_keywords = extract_keywords(topic)
    if not topic_keywords:
        return False

    title_text = (title or "").lower()
    script_text = (script or "").lower()
    combined_content = f"{title_text} {script_text}"
    if scene_prompts:
        combined_content += " " + " ".join(scene_prompts).lower()

    matched_themes = 0
    for word in topic_keywords:
        # Check direct keyword presence as a distinct word
        if re.search(r"\b" + re.escape(word) + r"\b", combined_content):
            matched_themes += 1
            continue

        # Check synonym cluster
        cluster = THEMATIC_SYNONYMS.get(word)
        if cluster:
            if any(re.search(r"\b" + re.escape(syn) + r"\b", combined_content) for syn in cluster):
                matched_themes += 1
                continue

    return matched_themes > 0


# ─────────────────────────────────────────────────────────────────────────────
# 4. Scene Omission and Rebalancing
# ─────────────────────────────────────────────────────────────────────────────

def rebalance_scenes_on_omission(
    valid_image_paths: list[Path],
    scene_manifest: dict[int, str],
    total_duration: float,
    *,
    min_required_scenes: int = 4,
) -> tuple[list[Path], dict[int, str], float]:
    """If a non-critical visual scene fails across all AI generators and cannot be synthesized,
    omit the missing scene and rebalance duration evenly across remaining valid AI scenes.
    Ensures video rendering succeeds without violating visual quality policy (no procedural placeholders).
    """
    # Keep only files that exist and are valid images (> 1000 bytes)
    active_paths = [p for p in valid_image_paths if p.is_file() and p.stat().st_size >= 1000]

    if len(active_paths) < min_required_scenes:
        raise ValueError(
            f"Cannot rebalance scenes: only {len(active_paths)} valid scenes available, "
            f"minimum required is {min_required_scenes}."
        )

    # Filter scene manifest to record omission
    updated_manifest: dict[int, str] = {}
    for idx, path in enumerate(active_paths, start=1):
        original_entry = scene_manifest.get(idx, "ai_generated")
        updated_manifest[idx] = f"{original_entry} (rebalanced scene {idx}/{len(active_paths)})"

    return active_paths, updated_manifest, total_duration


# ─────────────────────────────────────────────────────────────────────────────
# 5. Idempotent Upload Reconciliation
# ─────────────────────────────────────────────────────────────────────────────

def reconcile_upload_state(
    narration: str,
    video_sha256: str | None = None,
) -> tuple[bool, str]:
    """Check if this story or video has already been recorded as uploaded.
    Prevents accidental duplicate YouTube uploads during retry or network recovery.
    """
    from pipeline.story_history import is_video_already_uploaded, check_duplicate

    is_dup, reason = check_duplicate(narration[:60])
    if is_dup:
        return True, reason

    if video_sha256:
        is_dup_vid, dup_vid_reason = is_video_already_uploaded(None, video_sha256)
        if is_dup_vid:
            return True, dup_vid_reason

    return False, "ok"


# ─────────────────────────────────────────────────────────────────────────────
# 6. Recovery Tracker
# ─────────────────────────────────────────────────────────────────────────────

class RecoveryTracker:
    """Additive telemetry tracker to record all recovered failures in a run."""

    def __init__(self) -> None:
        self.actions_taken: list[dict[str, Any]] = []
        self.rewritten_prompts: int = 0
        self.omitted_scenes: int = 0
        self.retries: int = 0

    def record_action(self, stage: str, action: str, details: str) -> None:
        self.actions_taken.append({
            "stage": stage,
            "action": action,
            "details": details,
        })

    def record_prompt_rewrite(self, original: str, rewritten: str) -> None:
        self.rewritten_prompts += 1
        self.record_action(
            stage="visual_prompt",
            action="safety_rewrite",
            details=f"Rewrote prompt to remove moderation triggers (length {len(original)} -> {len(rewritten)})",
        )

    def record_scene_omission(self, omitted_index: int, total_scenes: int) -> None:
        self.omitted_scenes += 1
        self.record_action(
            stage="visual_generation",
            action="scene_omission",
            details=f"Omitted scene {omitted_index} and rebalanced timeline across {total_scenes} remaining AI scenes",
        )

    def summary(self) -> dict[str, Any]:
        return {
            "recovered_count": len(self.actions_taken),
            "rewritten_prompts": self.rewritten_prompts,
            "omitted_scenes": self.omitted_scenes,
            "actions": self.actions_taken,
        }
