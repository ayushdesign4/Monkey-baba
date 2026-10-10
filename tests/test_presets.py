import pytest
from pipeline.channel_presets import get_preset, list_channel_ids, PRESETS


def test_horror_preset_exists():
    assert "horror" in list_channel_ids()
    preset = get_preset("horror")
    assert preset["id"] == "horror"
    assert preset["language"] == "en"
    assert preset["aspect_ratio"] == "9:16"
    assert preset["min_words"] >= 100
    assert preset["scene_count_min"] == 6
    assert preset["scene_count_max"] == 8
    assert preset["segment_count"] == 6
    assert len(preset["topic_pool"]) >= 20


def test_horror_preset_system_hint():
    preset = get_preset("horror")
    hint = preset["groq_system_hint"].lower()
    assert "horror" in hint
    assert "100" in hint or "words" in hint
    assert "image_style_suffix" in preset
    assert "image_negative_prompt" in preset


def test_ghost_stories_backward_compatibility():
    preset = get_preset("ghost_stories")
    assert preset["id"] == "ghost_stories"
    assert preset["min_words"] >= 100
