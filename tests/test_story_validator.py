import pytest
from pipeline.story_validator import validate_story_consistency, StoryConsistencyError


def test_story_consistency_success():
    topic = "a lake where the water remains unnaturally still even during thunderstorms"
    title = "A Lake Where The Water Remains Unnaturally Still Even During Thunderstorms #Shorts"
    script = (
        "For decades, locals spoke in hushed whispers about a lake where the water remains unnaturally still "
        "even during thunderstorms. A curious traveler investigated the mysterious lake at midnight. "
        "Armed with a flashlight, he approached the still water as dark storm clouds rolled in. "
        "The lake surface was glass-smooth despite raging lightning above. Standing motionless in the lake mist, "
        "shadowy figures appeared beneath the surface."
    )
    scenes = [
        "Cinematic wide establishing shot of a lake where the water remains unnaturally still at twilight",
        "A lonely investigator approaching the unnaturally calm lake in a storm",
    ]

    # Should pass without raising
    validate_story_consistency(topic, title, script, scenes)


def test_story_consistency_mismatch_rejected():
    topic = "a lake where the water remains unnaturally still even during thunderstorms"
    title = "The Antique Mirror That Blinks Late #Shorts"
    script = (
        "In the corner of a dusty antique shop, Maya noticed a tall gilded mirror with an ornate mahogany frame. "
        "When she smiled, her reflection smiled back normally. But when she blinked, her reflection stared back "
        "with wide unblinking eyes."
    )
    scenes = [
        "Dusty antique shop filled with relics",
        "Young woman standing before a tall ornate gilded mirror",
    ]

    with pytest.raises(StoryConsistencyError) as exc_info:
        validate_story_consistency(topic, title, script, scenes)

    err = str(exc_info.value)
    assert "Story mismatch detected" in err
    assert "lake" in err
    assert "Mirror" in err or "mirror" in err.lower()


def test_story_consistency_empty_components():
    with pytest.raises(StoryConsistencyError):
        validate_story_consistency("", "Title", "Script", ["Scene 1"])
    with pytest.raises(StoryConsistencyError):
        validate_story_consistency("Topic", "", "Script", ["Scene 1"])
    with pytest.raises(StoryConsistencyError):
        validate_story_consistency("Topic", "Title", "", ["Scene 1"])
    with pytest.raises(StoryConsistencyError):
        validate_story_consistency("Topic", "Title", "Script", [])
