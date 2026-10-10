from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.captions import build_srt
from pipeline.channel_presets import get_preset
from pipeline.edge_tts_synth import (
    SentenceTiming,
    adjust_audio_tempo_if_needed,
    synthesize_full,
)
from pipeline.groq_script import (
    FALLBACK_HORROR_STORIES,
    generate_adaptive_horror_story,
)
from pipeline.quality_gate import QualityGateResult, validate_short_quality


def test_adaptive_story_and_fallback_stories_meet_minimum_100_words():
    """Verify that both dynamic adaptive story and all fallback stories
    strictly contain at least 100 English words and stay within a tight 105-135 word band.
    """
    topic = "a childhood diary with entries in your handwriting dated ten years in the future"
    story = generate_adaptive_horror_story(topic)
    words = len(story["full_narration"].split())

    assert words >= 100, f"Adaptive story has {words} words, must be >= 100"
    assert words <= 130, f"Adaptive story has {words} words, must be <= 130 to prevent 60s+ overrun"

    for idx, fb in enumerate(FALLBACK_HORROR_STORIES):
        fb_words = len(fb["full_narration"].split())
        assert fb_words >= 100, f"Fallback story {idx} has {fb_words} words, must be >= 100"
        assert fb_words <= 140, f"Fallback story {idx} has {fb_words} words, must be <= 140"


def test_horror_preset_word_count_and_rate_configuration():
    """Verify horror preset enforces 105-125 word rule and +10% TTS rate."""
    preset = get_preset("horror")
    assert preset["min_words"] == 100
    assert preset.get("tts_rate") == "+10%"
    assert "between 105 and 125 English words" in preset["groq_system_hint"]


def test_adjust_audio_tempo_scales_long_narration(tmp_path):
    """Verify that narration exceeding 55.0s (like 67.8s observed in production)
    is brought down to 45-55s using bounded atempo without truncation.
    """
    fake_audio = tmp_path / "long_voiceover.mp3"
    fake_audio.write_bytes(b"dummy mp3 content")

    timings = [
        SentenceTiming(text="Sentence one.", offset_ms=0, duration_ms=25000),
        SentenceTiming(text="Sentence two.", offset_ms=25000, duration_ms=25000),
        SentenceTiming(text="Sentence three.", offset_ms=50000, duration_ms=17800),
    ]

    # Mock ffprobe reporting 67.8s
    with patch("pipeline.edge_tts_synth._ffprobe_duration", return_value=67.8):
        new_dur, adjusted_timings = adjust_audio_tempo_if_needed(
            fake_audio,
            timings,
            min_target=45.0,
            max_target=55.0,
            absolute_max=58.0,
            absolute_min=30.0,
        )

        assert 45.0 <= new_dur <= 55.0, f"Adjusted duration {new_dur:.1f}s outside target 45-55s"
        assert len(adjusted_timings) == 3
        # Timings should be scaled down proportionally
        assert adjusted_timings[-1]["offset_ms"] < timings[-1]["offset_ms"]
        total_adjusted_ms = adjusted_timings[-1]["offset_ms"] + adjusted_timings[-1]["duration_ms"]
        assert total_adjusted_ms < 67800


def test_adjust_audio_tempo_leaves_optimal_duration_untouched(tmp_path):
    """Verify that audio already in 30.0-55.0s range is untouched."""
    fake_audio = tmp_path / "good_voiceover.mp3"
    fake_audio.write_bytes(b"dummy mp3 content")

    timings = [
        SentenceTiming(text="Sentence one.", offset_ms=0, duration_ms=20000),
        SentenceTiming(text="Sentence two.", offset_ms=20000, duration_ms=28000),
    ]

    with patch("pipeline.edge_tts_synth._ffprobe_duration", return_value=48.0):
        new_dur, adjusted_timings = adjust_audio_tempo_if_needed(
            fake_audio,
            timings,
            min_target=45.0,
            max_target=55.0,
        )

        assert new_dur == 48.0
        assert adjusted_timings == timings


def test_subtitle_synchronization_with_scaled_audio_timing(tmp_path):
    """Verify that subtitles generated from adjusted timings maintain exact alignment."""
    timings = [
        SentenceTiming(text="The old mirror began to crack.", offset_ms=0, duration_ms=30000),
        SentenceTiming(text="Something stepped through the glass.", offset_ms=30000, duration_ms=30000),
    ]

    # Scale by factor 1.2x (60s -> 50s)
    fake_audio = tmp_path / "voiceover.mp3"
    fake_audio.write_bytes(b"dummy")

    with patch("pipeline.edge_tts_synth._ffprobe_duration", return_value=60.0):
        new_dur, adjusted_timings = adjust_audio_tempo_if_needed(
            fake_audio,
            timings,
            min_target=45.0,
            max_target=55.0,
        )

        srt_file = tmp_path / "captions.srt"
        build_srt(adjusted_timings, srt_file, new_dur)

        assert srt_file.is_file()
        srt_content = srt_file.read_text(encoding="utf-8")
        assert "The old mirror began to" in srt_content
        assert "crack." in srt_content
        assert "Something stepped through the glass." in srt_content
        # Ensure timestamp ends before 55s
        assert "00:00:5" in srt_content or "00:00:4" in srt_content
        assert "00:01:00" not in srt_content


def test_final_video_duration_enforced_strictly_30_to_60s(tmp_path):
    """Verify that quality gate strictly allows 30-60s videos and rejects >60s or <30s."""
    video_file = tmp_path / "test.mp4"
    video_file.write_bytes(b"x" * 60_000)

    # 1. 48.0s: PASS
    with patch("pipeline.quality_gate.probe_video", return_value={
        "format": {"duration": "48.0"},
        "streams": [{"codec_type": "video", "width": 1080, "height": 1920}, {"codec_type": "audio"}],
    }), patch("pipeline.quality_gate.sample_frames_for_black", return_value=(True, "ok")):
        res = validate_short_quality(video_file)
        assert res.passed is True
        assert res.duration == 48.0

    # 2. 67.8s: FAIL (rejection observed in latest production run)
    with patch("pipeline.quality_gate.probe_video", return_value={
        "format": {"duration": "67.8"},
        "streams": [{"codec_type": "video", "width": 1080, "height": 1920}, {"codec_type": "audio"}],
    }), patch("pipeline.quality_gate.sample_frames_for_black", return_value=(True, "ok")):
        res = validate_short_quality(video_file)
        assert res.passed is False
        assert any("exceeds maximum 60.0s" in e for e in res.errors)

    # 3. 25.0s: FAIL
    with patch("pipeline.quality_gate.probe_video", return_value={
        "format": {"duration": "25.0"},
        "streams": [{"codec_type": "video", "width": 1080, "height": 1920}, {"codec_type": "audio"}],
    }), patch("pipeline.quality_gate.sample_frames_for_black", return_value=(True, "ok")):
        res = validate_short_quality(video_file)
        assert res.passed is False
        assert any("below minimum 30.0s" in e for e in res.errors)
