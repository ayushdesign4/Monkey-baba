import pytest
from pipeline.channel_presets import get_preset
from pipeline.groq_script import generate_local_fallback, generate_short_pack


def test_deterministic_local_fallback_horror():
    preset = get_preset("horror")
    pack = generate_local_fallback(preset, topic_hint="an antique mirror")
    
    assert "youtube_title" in pack
    assert "youtube_description" in pack
    assert "full_narration" in pack
    assert "image_prompts" in pack
    
    narration = pack["full_narration"]
    word_count = len(narration.split())
    assert word_count >= 100, f"Expected >= 100 words, got {word_count}"
    assert len(pack["image_prompts"]) == 6
    for p in pack["image_prompts"]:
        assert isinstance(p, str) and len(p) > 20


def test_generate_short_pack_without_api_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    preset = get_preset("horror")
    pack = generate_short_pack(preset)
    
    assert "youtube_title" in pack
    assert len(pack["full_narration"].split()) >= 100
    assert len(pack["image_prompts"]) == 6
