"""Unit tests for additive recovery layer (pipeline/recovery.py)."""
import tempfile
from pathlib import Path
import pytest

from pipeline.recovery import (
    ErrorCategory,
    RunStatus,
    classify_error,
    rewrite_prompt_for_safety,
    semantic_premise_match,
    rebalance_scenes_on_omission,
    reconcile_upload_state,
    RecoveryTracker,
)
from pipeline.story_validator import validate_story_consistency, StoryConsistencyError


# ─────────────────────────────────────────────────────────────────────────────
# 1. Error Classification Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_classify_error_categories():
    assert classify_error("HTTP 401 Unauthorized: Invalid API key") == ErrorCategory.AUTH_PERMANENT
    assert classify_error("402 Payment Required: Insufficient pollen credits") == ErrorCategory.AUTH_PERMANENT
    assert classify_error("403 Forbidden: Access denied") == ErrorCategory.AUTH_PERMANENT

    assert classify_error("HTTP 400 Bad Request: Prompt violated content policy") == ErrorCategory.PROMPT_SAFETY_REJECTION
    assert classify_error("Generation rejected by safety filter") == ErrorCategory.PROMPT_SAFETY_REJECTION

    assert classify_error("404 model_not_found: The model does not exist") == ErrorCategory.UNSUPPORTED_MODEL
    assert classify_error("Unsupported model: llama-deprecated") == ErrorCategory.UNSUPPORTED_MODEL

    assert classify_error("504 Gateway Timeout") == ErrorCategory.TRANSIENT
    assert classify_error("Connection timed out after 30s") == ErrorCategory.TRANSIENT
    assert classify_error("HTTP 429: Too Many Requests") == ErrorCategory.TRANSIENT

    assert classify_error("JSONDecodeError: Unterminated string starting at line 1") == ErrorCategory.LLM_FORMAT
    assert classify_error("Story mismatch detected! Topic keywords do not match") == ErrorCategory.SEMANTIC_MISMATCH
    assert classify_error("Visual quality gate failed: duration out of bounds") == ErrorCategory.MEDIA_INTEGRITY


# ─────────────────────────────────────────────────────────────────────────────
# 2. Safety Prompt Rewriter Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_rewrite_prompt_for_safety_replaces_gore():
    raw_prompt = "A mutilated corpse covered in blood lying beside a severed arm in a dark room"
    rewritten = rewrite_prompt_for_safety(raw_prompt)

    assert "mutilated" not in rewritten.lower()
    assert "corpse" not in rewritten.lower()
    assert "blood" not in rewritten.lower()
    assert "severed" not in rewritten.lower()
    assert "grotesquely contorted" in rewritten
    assert "motionless draped silhouette" in rewritten
    assert "stained with dark shadows" in rewritten


def test_rewrite_prompt_preserves_clean_prompt():
    clean_prompt = "A chilling dark hallway with flickering candlelight and long shadows"
    assert rewrite_prompt_for_safety(clean_prompt) == clean_prompt


# ─────────────────────────────────────────────────────────────────────────────
# 3. Semantic Premise Match Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_semantic_premise_match_synonyms():
    # Mirror and reflection/glass should match
    assert semantic_premise_match(
        topic="an antique mirror holding trapped souls",
        title="The Silver Glass Reflection #Shorts",
        script="A young woman stared into the silver glass and noticed another face staring back.",
    )

    # Lake and water/submerged should match
    assert semantic_premise_match(
        topic="a lake that never ripples",
        title="The Still Depths #Shorts",
        script="Deep beneath the surface of the quiet water, an anomaly waited in silence.",
    )


def test_semantic_premise_match_divergent():
    # Lake vs antique clock/clockmaker has no thematic link
    assert not semantic_premise_match(
        topic="a lake where the water remains unnaturally still",
        title="The Clockmaker's Midnight Chime #Shorts",
        script="The old pocket watch chimed twelve times in the deserted attic.",
    )


def test_story_validator_integration_with_semantic_recovery():
    # Topic uses "mirror", title uses "glass reflection"
    topic = "an antique mirror that traps wanderers"
    title = "The Ancient Glass Reflection #Shorts"
    script = (
        "In the forgotten corner of the antique shop, a silver glass stood tall. "
        "Every wanderer who gazed into its reflection was never seen again. "
        "The glass surface remained cold and dark."
    )
    scenes = [
        "Dusty shop with an ancient silver glass frame",
        "Wanderer looking into the eerie reflection",
    ]

    # Should pass thanks to semantic premise recovery
    validate_story_consistency(topic, title, script, scenes)


def test_story_validator_still_rejects_truly_divergent_runs():
    topic = "a lake where the water remains unnaturally still even during thunderstorms"
    title = "The Haunted Doll in the Attic #Shorts"
    script = "A creepy porcelain doll sat on a wooden rocking chair in the dusty attic."
    scenes = ["Attic scene with porcelain doll"]

    with pytest.raises(StoryConsistencyError) as exc_info:
        validate_story_consistency(topic, title, script, scenes)
    assert "Story mismatch detected" in str(exc_info.value)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Scene Omission and Rebalancing Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_rebalance_scenes_on_omission():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        paths = []
        for i in range(5):
            p = tmp_path / f"scene_{i+1}.png"
            p.write_bytes(b"dummy image data " * 100)  # > 1000 bytes
            paths.append(p)

        manifest = {1: "pollinations", 2: "pollinations", 3: "procedural", 4: "pollinations", 5: "pollinations"}

        # Suppose scene 3 was procedural and we filter to only genuine AI images (scenes 1, 2, 4, 5)
        ai_paths = [paths[0], paths[1], paths[3], paths[4]]
        active_paths, new_manifest, dur = rebalance_scenes_on_omission(
            ai_paths, manifest, total_duration=50.0, min_required_scenes=4
        )

        assert len(active_paths) == 4
        assert dur == 50.0
        assert len(new_manifest) == 4
        assert "rebalanced" in new_manifest[1]


def test_rebalance_scenes_raises_if_insufficient():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        p = tmp_path / "scene_1.png"
        p.write_bytes(b"dummy image data " * 100)

        with pytest.raises(ValueError, match="minimum required is 4"):
            rebalance_scenes_on_omission([p], {1: "pollinations"}, total_duration=45.0, min_required_scenes=4)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Recovery Tracker Telemetry Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_recovery_tracker():
    tracker = RecoveryTracker()
    tracker.record_prompt_rewrite("original graphic prompt", "softened atmospheric prompt")
    tracker.record_scene_omission(3, 5)

    summary = tracker.summary()
    assert summary["recovered_count"] == 2
    assert summary["rewritten_prompts"] == 1
    assert summary["omitted_scenes"] == 1
