import json
import pytest
from pathlib import Path
from pipeline.story_history import (
    CorruptHistoryError,
    check_duplicate,
    compute_fingerprint,
    compute_similarity,
    normalize_text,
    reserve_topic,
    _safe_read_json,
)


def test_normalize_text():
    assert normalize_text("The Haunted Mirror #Shorts!") == "the haunted mirror shorts"
    assert normalize_text("   GHOST... in the Woods?   ") == "ghost in the woods"


def test_compute_fingerprint_stability():
    fp1 = compute_fingerprint("A whisper in the dark night.")
    fp2 = compute_fingerprint("  a whisper in the dark night.  ")
    assert fp1 == fp2


def test_compute_similarity():
    text1 = "A ghost whispers in the dark cellar every midnight."
    text2 = "A ghost whispers in the dark cellar every midnight."
    assert compute_similarity(text1, text2) == 1.0

    text3 = "A mysterious radio plays music on an abandoned mountain highway."
    assert compute_similarity(text1, text3) < 0.2


def test_corrupt_history_fail_closed(tmp_path):
    bad_file = tmp_path / "corrupt_history.json"
    bad_file.write_text("{ unclosed bad json content", encoding="utf-8")
    
    with pytest.raises(CorruptHistoryError):
        _safe_read_json(bad_file, list)


def test_reserve_and_check_duplicate():
    title = "Test Unique Story of the Foggy Lake 999"
    summary = "A traveler sees strange green lights floating above an icy lake."
    
    # First check: not duplicate
    is_dup, _ = check_duplicate(title)
    
    # Reserve it
    topic_id = reserve_topic(title, summary, run_id="test_run")
    assert topic_id.startswith("topic_")
    
    # Second check: should now be duplicate
    is_dup_after, reason = check_duplicate(title)
    assert is_dup_after is True
    assert "Exact topic match" in reason
