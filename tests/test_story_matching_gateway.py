"""Focused tests for the loosened Monkey-baba Story Matching Gateway.

Tests:
1. Creative metaphors (e.g. Haunted Lake -> cursed shoreline, mysterious water, underwater voices)
2. Indirect thematic relevance (e.g. lighthouse -> lantern room, crashing sea, beacon)
3. Different wording with the same story vibe (e.g. mirror -> silver glass, looking glass, reflections)
4. Genuinely unrelated stories (rejected firmly)
5. Empty content validation (rejected fail-closed)
6. Semantic API failure / network timeout handling (permissive fallback, never cancels upload)
"""
from unittest.mock import patch
import pytest

from pipeline.recovery import semantic_premise_match, _check_relevance_via_ai
from pipeline.story_validator import validate_story_consistency, StoryConsistencyError


# ─────────────────────────────────────────────────────────────────────────────
# 1. Creative Metaphors
# ─────────────────────────────────────────────────────────────────────────────

def test_creative_metaphors_haunted_lake():
    """Topic 'Haunted Lake' should accept creative water/shoreline/submerged stories without exact keyword matches."""
    topic = "Haunted Lake"
    title = "The Cursed Shoreline #Shorts"
    script = (
        "At twilight, a lonely investigator stood upon the misty shoreline. "
        "Mysterious currents swirled beneath the dark water without any wind. "
        "Hushed underwater voices called out from the depths, repeating the names of travelers lost decades ago."
    )
    scenes = [
        "Cinematic misty shoreline with calm dark water at twilight",
        "Sunken ferry wreck visible beneath the murky surface",
    ]

    # Must pass without raising StoryConsistencyError
    validate_story_consistency(topic, title, script, scenes)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Indirect Thematic Relevance
# ─────────────────────────────────────────────────────────────────────────────

def test_indirect_thematic_relevance_lighthouse():
    """Topic 'The Abandoned Lighthouse' accepts stories about lantern rooms, crashing sea, and rotating beacons."""
    topic = "The Abandoned Lighthouse"
    title = "The Glass Tower's Final Beacon #Shorts"
    script = (
        "High above the crashing sea, the solitary keeper climbed the spiral staircase into the dark lantern room. "
        "The ancient rotating lens began to glow with unearthly light, illuminating silhouettes standing motionless on the rocky shore."
    )
    scenes = [
        "Crashing waves against tall sea cliffs",
        "Lantern room with blinding beam piercing the storm fog",
    ]

    validate_story_consistency(topic, title, script, scenes)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Different Wording with the Same Story Vibe
# ─────────────────────────────────────────────────────────────────────────────

def test_different_wording_same_vibe_mirror():
    """Topic about cursed mirror accepts silver glass, reflections, and unblinking stares."""
    topic = "a cursed mirror that traps wanderers"
    title = "The Silver Glass Reflection #Shorts"
    script = (
        "In a quiet antique shop, a silver frame hung against the aged wallpaper. "
        "When visitors gazed upon the cold glass, another pair of unblinking eyes stared back from the gloom."
    )
    scenes = [
        "Antique shop interior with relics",
        "Looking glass reflection of an eerie silhouette",
    ]

    validate_story_consistency(topic, title, script, scenes)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Genuinely Unrelated Stories
# ─────────────────────────────────────────────────────────────────────────────

def test_genuinely_unrelated_story_rejected():
    """Stories describing completely conflicting premises (e.g. Lake vs Antique Mirror) must still be rejected."""
    topic = "a lake where the water remains unnaturally still even during thunderstorms"
    title = "The Antique Mirror That Blinks Late #Shorts"
    script = (
        "In the corner of a dusty antique shop, Maya noticed a tall gilded mirror with an ornate mahogany frame. "
        "When she smiled, her reflection stared back with wide unblinking eyes."
    )
    scenes = [
        "Dusty antique shop filled with relics",
        "Tall gilded mirror in a dusty parlor",
    ]

    with pytest.raises(StoryConsistencyError) as exc_info:
        validate_story_consistency(topic, title, script, scenes)

    err = str(exc_info.value)
    assert "Story mismatch detected" in err
    assert "lake" in err
    assert "Mirror" in err or "mirror" in err.lower()


def test_genuinely_unrelated_clock_vs_forest():
    topic = "an ancient grandfather clock chiming backward"
    title = "Lost in the Deep Pines #Shorts"
    script = "The hiker lost the overgrown trail as darkness fell among the ancient timber and pine trees."
    scenes = ["Dark pine forest with tall trees"]

    with pytest.raises(StoryConsistencyError) as exc_info:
        validate_story_consistency(topic, title, script, scenes)

    assert "Story mismatch detected" in str(exc_info.value)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Empty Content
# ─────────────────────────────────────────────────────────────────────────────

def test_empty_content_strictly_rejected():
    with pytest.raises(StoryConsistencyError, match="Selected topic is empty"):
        validate_story_consistency("", "Title", "Script narration", ["Scene 1"])

    with pytest.raises(StoryConsistencyError, match="Story title is empty"):
        validate_story_consistency("Topic", "   ", "Script narration", ["Scene 1"])

    with pytest.raises(StoryConsistencyError, match="Story script narration is empty"):
        validate_story_consistency("Topic", "Title", "", ["Scene 1"])

    with pytest.raises(StoryConsistencyError, match="Scene prompts list is empty"):
        validate_story_consistency("Topic", "Title", "Script narration", [])


# ─────────────────────────────────────────────────────────────────────────────
# 6. Semantic API Failure & Permissive Fallback
# ─────────────────────────────────────────────────────────────────────────────

def test_semantic_api_failure_does_not_cancel_upload():
    """When the AI relevance check throws an exception or network error, permissive fallback allows usable content."""
    topic = "The Forgotten Underground Station"
    title = "The Midnight Commute #Shorts"
    script = (
        "Deep below the city streets, a traveler waited upon the dimly lit subway platform. "
        "The steel rails began to hum with an approaching train that was never scheduled on any timetable."
    )
    scenes = ["Subway platform at midnight", "Approaching train lights in the tunnel"]

    # Mock _check_relevance_via_ai to simulate an API outage / timeout
    with patch("pipeline.recovery._check_relevance_via_ai", side_effect=RuntimeError("API Gateway 504 Timeout")):
        # Must not raise StoryConsistencyError or RuntimeError!
        validate_story_consistency(topic, title, script, scenes)


def test_ai_relevance_check_explicit_yes():
    """When the AI provider returns YES, the gateway immediately accepts."""
    with patch("pipeline.recovery._check_relevance_via_ai", return_value=True):
        assert semantic_premise_match(
            "An abstract psychological horror concept",
            "Shadows of the Mind #Shorts",
            "A psychologist explores an eerie abandoned asylum ward at midnight.",
            ["Asylum hallway"],
            use_ai=True,
        ) is True


def test_ai_relevance_check_explicit_no():
    """When the AI provider returns NO, the gateway rejects."""
    with patch("pipeline.recovery._check_relevance_via_ai", return_value=False):
        assert semantic_premise_match(
            "A haunted lake",
            "The Antique Pocket Watch #Shorts",
            "A watchmaker repairs a small gold watch in his clock repair parlor.",
            ["Clock repair shop"],
            use_ai=True,
        ) is False
