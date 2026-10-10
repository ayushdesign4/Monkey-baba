"""Layered deduplication, persistent state management, and history tracking.

Persists state to:
  data/topic_history.json
  data/upload_history.json
  data/run_state.json

Enforces:
  1. Exact topic/title match (normalized)
  2. Exact story fingerprint (SHA-256 of normalized narration)
  3. Near-duplicate script detection (token/word similarity > 0.65)
  4. Video SHA-256 fingerprint check before upload
  5. Upload record check (video_id and fingerprint uniqueness)
  6. Reserve-before-generation pattern
  7. Fail-closed on corrupt history (raises CorruptHistoryError)
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

TOPIC_HISTORY_PATH = DATA_DIR / "topic_history.json"
UPLOAD_HISTORY_PATH = DATA_DIR / "upload_history.json"
RUN_STATE_PATH = DATA_DIR / "run_state.json"

MAX_HISTORY_ENTRIES = 500


class CorruptHistoryError(RuntimeError):
    """Raised when an existing history/state file cannot be parsed.
    The pipeline fails closed to prevent duplicate uploads.
    """
    pass


def normalize_text(text: str) -> str:
    """Normalize text for consistent comparison (lowercase, alphanumeric + space)."""
    text = (text or "").lower().strip()
    text = re.sub(r"[#\-_/\\.,:;!?\"'()[\]{}<>]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def compute_fingerprint(text: str) -> str:
    """Compute stable SHA-256 fingerprint of normalized text."""
    norm = normalize_text(text)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def compute_file_sha256(file_path: Path) -> str:
    """Compute SHA-256 of a local file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def compute_similarity(text_a: str, text_b: str) -> float:
    """Compute word-level Jaccard similarity between two texts."""
    norm_a = normalize_text(text_a)
    norm_b = normalize_text(text_b)
    if not norm_a or not norm_b:
        return 0.0
    words_a = set(norm_a.split())
    words_b = set(norm_b.split())
    intersection = words_a.intersection(words_b)
    union = words_a.union(words_b)
    if not union:
        return 0.0
    return len(intersection) / len(union)


def _safe_read_json(file_path: Path, default_factory: Any) -> Any:
    """Read JSON file with fail-closed semantics for corruption."""
    if not file_path.is_file():
        return default_factory()
    content = file_path.read_text(encoding="utf-8").strip()
    if not content:
        return default_factory()
    try:
        return json.loads(content)
    except Exception as exc:
        raise CorruptHistoryError(
            f"Corrupt state file detected at {file_path}: {exc}. "
            "Failing closed to prevent duplicate processing or upload."
        ) from exc


def _safe_write_json(file_path: Path, data: Any) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = file_path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    temp_path.replace(file_path)


# ── Topic History ─────────────────────────────────────────────────────────

def load_topic_history() -> list[dict[str, Any]]:
    """Load topic history from data/topic_history.json.
    Migrates legacy data/topics.json if present.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not TOPIC_HISTORY_PATH.is_file() and (DATA_DIR / "topics.json").is_file():
        legacy = _safe_read_json(DATA_DIR / "topics.json", list)
        migrated = []
        for item in legacy:
            migrated.append({
                "topic_id": item.get("topic_id", f"migrated-{len(migrated)}"),
                "normalized_topic": normalize_text(item.get("topic", "")),
                "topic_title": item.get("topic", ""),
                "topic_summary": item.get("story_summary", ""),
                "story_fingerprint": compute_fingerprint(item.get("story_summary", "")),
                "key_entities": [],
                "story_type": "horror",
                "created_at_utc": item.get("date", datetime.now(timezone.utc).isoformat()),
                "run_id": "legacy_migration",
                "status": item.get("status", "completed"),
                "youtube_video_id": item.get("video_id"),
                "youtube_url": f"https://www.youtube.com/watch?v={item['video_id']}" if item.get("video_id") else None,
            })
        _safe_write_json(TOPIC_HISTORY_PATH, migrated)
        return migrated

    return _safe_read_json(TOPIC_HISTORY_PATH, list)


def check_duplicate(
    candidate_topic: str,
    candidate_script: str = "",
    *,
    similarity_threshold: float = 0.65,
) -> tuple[bool, str]:
    """Check candidate topic/script against topic history.
    Returns (is_duplicate, reason).
    """
    history = load_topic_history()
    cand_norm = normalize_text(candidate_topic)
    cand_fp = compute_fingerprint(candidate_script) if candidate_script else ""

    for item in history:
        # Skip failed/abandoned topics if needed, but uploaded/reserved/generated count
        status = item.get("status", "")
        if status in ("failed", "abandoned"):
            continue

        # 1. Exact normalized topic match
        if item.get("normalized_topic") == cand_norm:
            return True, f"Exact topic match with prior topic '{item.get('topic_title')}' (id: {item.get('topic_id')})"

        # 2. Exact script fingerprint match
        if cand_fp and item.get("story_fingerprint") == cand_fp:
            return True, f"Exact script fingerprint match with topic '{item.get('topic_title')}'"

        # 3. Near-duplicate script check
        prior_summary = item.get("topic_summary", "")
        if candidate_script and prior_summary:
            sim = compute_similarity(candidate_script, prior_summary)
            if sim >= similarity_threshold:
                return True, f"Script similarity {sim:.2f} >= {similarity_threshold} with '{item.get('topic_title')}'"

    return False, ""


def reserve_topic(
    topic_title: str,
    summary: str = "",
    *,
    run_id: str = "manual",
    story_type: str = "horror",
    key_entities: list[str] | None = None,
) -> str:
    """Reserve a topic in persistent state before expensive generation."""
    history = load_topic_history()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    topic_id = f"topic_{ts}_{abs(hash(topic_title)) % 10000:04d}"

    record = {
        "topic_id": topic_id,
        "normalized_topic": normalize_text(topic_title),
        "topic_title": topic_title.strip(),
        "topic_summary": summary.strip(),
        "story_fingerprint": compute_fingerprint(summary),
        "key_entities": key_entities or [],
        "story_type": story_type,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "status": "reserved",
        "youtube_video_id": None,
        "youtube_url": None,
    }

    history.append(record)
    history = history[-MAX_HISTORY_ENTRIES:]
    _safe_write_json(TOPIC_HISTORY_PATH, history)
    return topic_id


def update_topic_status(
    topic_id: str,
    status: str,
    *,
    script: str | None = None,
    video_id: str | None = None,
) -> None:
    """Update topic record status (e.g. generated, uploaded, failed)."""
    history = load_topic_history()
    for item in history:
        if item.get("topic_id") == topic_id:
            item["status"] = status
            if script:
                item["story_fingerprint"] = compute_fingerprint(script)
            if video_id:
                item["youtube_video_id"] = video_id
                item["youtube_url"] = f"https://www.youtube.com/watch?v={video_id}"
            break
    _safe_write_json(TOPIC_HISTORY_PATH, history)


# ── Upload History ────────────────────────────────────────────────────────

def load_upload_history() -> list[dict[str, Any]]:
    """Load upload history from data/upload_history.json.
    Migrates legacy data/uploads.json if present.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not UPLOAD_HISTORY_PATH.is_file() and (DATA_DIR / "uploads.json").is_file():
        legacy = _safe_read_json(DATA_DIR / "uploads.json", list)
        migrated = []
        for item in legacy:
            migrated.append({
                "video_id": item.get("video_id"),
                "video_url": item.get("youtube_url", f"https://www.youtube.com/watch?v={item.get('video_id')}"),
                "title": item.get("title", ""),
                "topic_id": item.get("topic_id", "legacy"),
                "story_fingerprint": "",
                "video_sha256": "",
                "duration_seconds": 45,
                "language": "en",
                "niche": "horror",
                "uploaded_at_utc": datetime.now(timezone.utc).isoformat(),
                "run_id": "legacy_migration",
                "status": item.get("status", "uploaded"),
                "dry_run": item.get("dry_run", False),
                "notification_status": "sent" if not item.get("dry_run") else "skipped",
            })
        _safe_write_json(UPLOAD_HISTORY_PATH, migrated)
        return migrated

    return _safe_read_json(UPLOAD_HISTORY_PATH, list)


def is_video_already_uploaded(video_id: str | None, video_sha256: str | None) -> tuple[bool, str]:
    """Check if video ID or video SHA-256 is already recorded in upload history."""
    uploads = load_upload_history()
    for item in uploads:
        if video_id and item.get("video_id") == video_id and not item.get("dry_run"):
            return True, f"Video ID {video_id} already recorded as uploaded"
        if video_sha256 and item.get("video_sha256") == video_sha256 and not item.get("dry_run"):
            return True, f"Video file SHA-256 matches already uploaded video ({item.get('video_id')})"
    return False, ""


def record_upload(
    *,
    video_id: str,
    title: str,
    topic_id: str,
    story_fingerprint: str,
    video_sha256: str,
    duration_seconds: float,
    run_id: str,
    language: str = "en",
    niche: str = "horror",
    dry_run: bool = False,
    notification_status: str = "pending",
) -> dict[str, Any]:
    """Record successful upload record into upload_history.json."""
    uploads = load_upload_history()
    record = {
        "video_id": video_id,
        "video_url": f"https://www.youtube.com/watch?v={video_id}",
        "title": title.strip(),
        "topic_id": topic_id,
        "story_fingerprint": story_fingerprint,
        "video_sha256": video_sha256,
        "duration_seconds": round(duration_seconds, 1),
        "language": language,
        "niche": niche,
        "uploaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "status": "simulated" if dry_run else "uploaded",
        "dry_run": dry_run,
        "notification_status": notification_status,
    }
    uploads.append(record)
    uploads = uploads[-MAX_HISTORY_ENTRIES:]
    _safe_write_json(UPLOAD_HISTORY_PATH, uploads)

    # Also update topic_history status
    update_topic_status(topic_id, "uploaded" if not dry_run else "simulated", video_id=video_id)
    return record


def update_notification_status(video_id: str, status: str) -> None:
    """Update notification status for an uploaded video."""
    uploads = load_upload_history()
    for item in uploads:
        if item.get("video_id") == video_id:
            item["notification_status"] = status
            item["notification_sent_at_utc"] = datetime.now(timezone.utc).isoformat()
            break
    _safe_write_json(UPLOAD_HISTORY_PATH, uploads)


# ── Run State ─────────────────────────────────────────────────────────────

def load_run_state() -> dict[str, Any]:
    return _safe_read_json(RUN_STATE_PATH, dict)


def save_run_state(state: dict[str, Any]) -> None:
    _safe_write_json(RUN_STATE_PATH, state)


# ── Prompt Injection Block for LLM ────────────────────────────────────────

def history_prompt_block(channel: str = "horror") -> str:
    """Returns a string to inject into the LLM prompt to prevent repeating past stories."""
    history = load_topic_history()
    if not history:
        return ""
    recent = history[-25:]
    lines = []
    for entry in recent:
        t = entry.get("topic_title") or entry.get("topic", "")
        s = entry.get("topic_summary") or entry.get("story_summary", "")
        if s:
            lines.append(f'  - "{t}": {s[:80]}...')
        elif t:
            lines.append(f'  - "{t}"')
    if not lines:
        return ""
    return (
        "\n\nIMPORTANT — Do NOT repeat or closely resemble any of these past stories. "
        "Pick a COMPLETELY different plot, setting, characters, and theme:\n" + "\n".join(lines) + "\n"
    )


def save_title(channel: str, title: str, summary: str = "") -> None:
    """Legacy helper for backward compatibility."""
    reserve_topic(title, summary, story_type=channel)
