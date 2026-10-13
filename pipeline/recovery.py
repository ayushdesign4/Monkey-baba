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
import os
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

THEMATIC_CLUSTERS: dict[str, set[str]] = {
    "water": {
        "water", "lake", "ocean", "sea", "river", "pond", "depths", "surface", "shore",
        "shoreline", "tide", "reservoir", "waves", "submerged", "drowned", "aquatic",
        "swamp", "marsh", "creek", "dock", "pier", "boat", "fisherman", "island", "abyss",
        "aquarium", "well", "ferry", "drowning", "bank", "deep", "fluid", "currents", "underwater",
    },
    "mirror": {
        "mirror", "reflection", "glass", "silver", "frame", "looking", "stare", "antique",
        "double", "gazing", "gaze", "eyes", "glance", "doppelganger", "speculum", "glimpse",
        "vanity", "blinks", "unblinking", "staring",
    },
    "doll": {
        "doll", "puppet", "toy", "mannequin", "porcelain", "figurine", "plaything", "effigy",
        "marionette", "dollhouse", "dummy", "plush", "childhood",
    },
    "forest": {
        "forest", "woods", "trees", "pines", "branches", "clearing", "cabin", "timber",
        "grove", "wilderness", "jungle", "foliage", "leaves", "roots", "canopy", "hike",
        "camper", "campfire", "tent", "ranger", "trail", "path",
    },
    "house": {
        "house", "mansion", "home", "cabin", "manor", "residence", "estate", "attic",
        "basement", "cellar", "room", "hallway", "corridor", "door", "window", "stairs",
        "staircase", "walls", "floor", "porch", "asylum", "hospital", "hotel", "motel",
        "building", "chapel", "church", "crypt",
    },
    "clock": {
        "clock", "time", "chime", "chimes", "chiming", "midnight", "hour", "pendulum",
        "ticks", "ticking", "watch", "seconds", "minutes", "alarm", "antique", "gear",
    },
    "ghost": {
        "ghost", "spirit", "phantom", "specter", "spectre", "apparition", "shadow", "entity",
        "presence", "whisper", "haunt", "haunted", "haunting", "poltergeist", "wraith",
        "shade", "demon", "monster", "creature", "beast", "fiend", "ghoul",
    },
    "whisper": {
        "whisper", "voice", "sound", "murmur", "calling", "echo", "echoes", "hiss",
        "breathe", "breathing", "cry", "crying", "wail", "shriek", "groan", "footsteps",
        "tapping", "scratching", "humming", "breathless",
    },
    "dream": {
        "dream", "nightmare", "sleep", "sleeping", "awake", "slumber", "waking", "vision",
        "paralysis", "hallucination", "trance", "hypnosis",
    },
    "painting": {
        "painting", "portrait", "canvas", "frame", "artist", "brush", "eyes", "picture",
        "gallery", "exhibit", "artwork",
    },
    "stairs": {
        "stairs", "staircase", "steps", "basement", "cellar", "attic", "creak", "below",
        "underneath", "spiral", "banister", "landing", "trapdoor",
    },
    "storm": {
        "storm", "thunder", "thunderstorm", "thunderstorms", "lightning", "rain", "tempest",
        "clouds", "darkness", "night", "wind", "gale", "fog", "mist", "blizzard", "chill",
        "cold", "frozen", "ice",
    },
    "shadow": {
        "shadow", "silhouette", "figure", "darkness", "shape", "outline", "shade",
        "stalker", "lurking", "unseen", "blackness",
    },
    "grave": {
        "grave", "graves", "cemetery", "graveyard", "tomb", "crypt", "coffin", "burial",
        "buried", "bones", "skeleton", "corpse", "dead", "death", "tombstone",
    },
    "car": {
        "car", "road", "highway", "drive", "driving", "headlights", "asphalt", "vehicle",
        "bridge", "tunnel", "traffic", "hitchhiker",
    },
    "radio": {
        "radio", "tape", "recording", "broadcast", "frequency", "signal", "radiator",
        "static", "channel", "cassette", "transmission", "antenna",
    },
    "phone": {
        "phone", "call", "calling", "screen", "message", "text", "ring", "ringing",
        "voicemail", "camera", "photo", "recording", "video",
    },
    "book": {
        "book", "diary", "journal", "pages", "parchment", "letter", "notes", "tome",
        "manuscript", "symbols", "runes", "scroll",
    },
    "music": {
        "music", "melody", "song", "instrument", "violin", "piano", "strings", "chords",
        "lullaby", "tune", "notes", "orchestra",
    },
    "subway": {
        "subway", "train", "station", "platform", "tracks", "tunnel", "commute", "underground", "rail",
    },
}

WORD_TO_THEMES: dict[str, set[str]] = {}
for _theme, _words in THEMATIC_CLUSTERS.items():
    for _w in _words:
        WORD_TO_THEMES.setdefault(_w, set()).add(_theme)


def _check_relevance_via_ai(
    topic: str,
    title: str,
    script: str,
    scene_prompts: list[str] | None = None,
    *,
    timeout: float = 30.0,
) -> bool | None:
    """Lightweight bounded AI check using configured LLM provider (Groq, Gemini, or OpenRouter).
    Returns:
      True  -> Confirmed reasonably related
      False -> Confirmed clearly unrelated
      None  -> Provider unavailable, timed out, or error (fall back safely to deterministic check)
    """
    prompt = (
        "You are an automated relevance gate for a horror storytelling channel.\n"
        "Evaluate whether the Story is reasonably related in theme, setting, atmosphere, or premise to the Topic.\n"
        "Creative metaphors, related horror tropes, and atmospheric variations ARE ACCEPTABLE.\n"
        "Reject ONLY if the story is about a completely different, unrelated topic (e.g. a lake story versus an antique mirror in a shop).\n\n"
        f"Topic: {topic}\n"
        f"Title: {title}\n"
        f"Story: {script[:350]}\n\n"
        "Respond with ONLY 'YES' if reasonably related, or 'NO' if clearly unrelated."
    )

    # 1. Try Groq if configured
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    if groq_key:
        try:
            from groq import Groq
            client = Groq(api_key=groq_key, timeout=timeout)
            model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
            resp = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                max_tokens=8,
                temperature=0.0,
            )
            ans = (resp.choices[0].message.content or "").strip().upper()
            if "YES" in ans:
                return True
            if "NO" in ans:
                return False
        except Exception as e:
            print(f"[RELEVANCE GATE] Groq relevance check skipped ({e}). Falling back.")

    # 2. Try Gemini if configured
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if gemini_key:
        try:
            import json
            import urllib.request
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
            payload = json.dumps({
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": 8, "temperature": 0.0},
            }).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        ans = parts[0].get("text", "").strip().upper()
                        if "YES" in ans:
                            return True
                        if "NO" in ans:
                            return False
        except Exception as e:
            print(f"[RELEVANCE GATE] Gemini relevance check skipped ({e}). Falling back.")

    # 3. Try OpenRouter if configured
    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if openrouter_key:
        try:
            import json
            import urllib.request
            base_url = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
            model = os.environ.get("OPENROUTER_MODEL", "meta-llama/llama-3.2-3b-instruct:free")
            url = f"{base_url}/chat/completions"
            payload = json.dumps({
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 8,
                "temperature": 0.0,
            }).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Authorization": f"Bearer {openrouter_key}", "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
                choices = data.get("choices", [])
                if choices:
                    ans = (choices[0].get("message", {}).get("content") or "").strip().upper()
                    if "YES" in ans:
                        return True
                    if "NO" in ans:
                        return False
        except Exception as e:
            print(f"[RELEVANCE GATE] OpenRouter relevance check skipped ({e}). Falling back.")

    return None


def semantic_premise_match(
    topic: str,
    title: str,
    script: str,
    scene_prompts: list[str] | None = None,
    *,
    use_ai: bool = True,
) -> bool:
    """Verify that topic, title, and script share a reasonably coherent premise or theme.
    
    Permissive acceptance policy:
    - Accepts creative storytelling, metaphors, atmospheric variations, and related tropes.
    - Fast-path deterministic evaluation using direct keywords, stems, and thematic clusters.
    - Lightweight bounded AI/LLM check when practical.
    - If AI check fails, times out, or is unavailable, uses a permissive fallback to prevent
      unnecessary upload cancellations.
    - Rejects only clearly unrelated stories or empty content.
    """
    from pipeline.story_validator import extract_keywords

    topic_str = (topic or "").strip()
    if not topic_str:
        return False

    title_str = (title or "").strip()
    script_str = (script or "").strip()
    if not title_str and not script_str:
        return False

    combined_content = f"{title_str.lower()} {script_str.lower()}"
    if scene_prompts:
        combined_content += " " + " ".join(scene_prompts).lower()

    topic_keywords = extract_keywords(topic_str)
    if not topic_keywords:
        topic_keywords = set(re.findall(r"\b[a-zA-Z]{3,}\b", topic_str.lower()))
    if not topic_keywords:
        return True

    # ── 1. Fast-Path Deterministic Check: Direct Keyword or Stem Match ──
    for kw in topic_keywords:
        if re.search(r"\b" + re.escape(kw) + r"\b", combined_content):
            return True
        if len(kw) >= 4:
            stem = kw[:-1] if kw.endswith("s") or kw.endswith("e") else kw
            if len(stem) >= 4 and re.search(r"\b" + re.escape(stem), combined_content):
                return True

    # ── 2. Thematic Cluster Match ──────────────────────────────────────
    topic_themes: set[str] = set()
    for kw in topic_keywords:
        if kw in WORD_TO_THEMES:
            topic_themes.update(WORD_TO_THEMES[kw])
        if len(kw) >= 4:
            stem = kw[:-1] if kw.endswith("s") or kw.endswith("e") else kw
            for word, themes in WORD_TO_THEMES.items():
                if word.startswith(stem) or stem.startswith(word):
                    topic_themes.update(themes)

    if topic_themes:
        for theme in topic_themes:
            cluster_words = THEMATIC_CLUSTERS.get(theme, set())
            for cword in cluster_words:
                if re.search(r"\b" + re.escape(cword) + r"\b", combined_content):
                    return True

    # ── 3. AI Relevance Check (if enabled and configured) ──────────────
    if use_ai:
        try:
            ai_verdict = _check_relevance_via_ai(topic_str, title_str, script_str, scene_prompts)
            if ai_verdict is True:
                return True
            if ai_verdict is False:
                return False
        except Exception as e:
            print(f"[RELEVANCE GATE] AI relevance check error: {e}. Falling back to permissive evaluation.")

    # ── 4. Permissive Deterministic Fallback on Ambiguity / API Failure ──
    content_words = set(re.findall(r"\b[a-zA-Z]{3,}\b", combined_content))
    content_themes: set[str] = set()
    for cw in content_words:
        if cw in WORD_TO_THEMES:
            content_themes.update(WORD_TO_THEMES[cw])

    if topic_themes and content_themes:
        overlap = topic_themes.intersection(content_themes)
        if not overlap:
            return False

    return True


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
