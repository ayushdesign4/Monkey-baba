import pytest
from unittest.mock import patch
from pathlib import Path
from pipeline.quality_gate import validate_short_quality, QualityGateResult


def test_missing_video_fails_quality_gate():
    res = validate_short_quality(Path("non_existent_file.mp4"))
    assert isinstance(res, QualityGateResult)
    assert res.passed is False
    assert any("File does not exist" in e for e in res.errors)


def test_tiny_file_fails_quality_gate(tmp_path):
    fake_video = tmp_path / "tiny.mp4"
    fake_video.write_bytes(b"too small")
    res = validate_short_quality(fake_video)
    assert res.passed is False
    assert any("too small" in e or "ffprobe" in e for e in res.errors)


def test_duration_under_30s_fails_quality_gate(tmp_path):
    # Proves 25s fails under the new 30-60s quality gate rule
    fake_video = tmp_path / "valid_size.mp4"
    fake_video.write_bytes(b"x" * 60_000)

    mock_probe = {
        "format": {"duration": "25.4"},
        "streams": [
            {"codec_type": "video", "width": 1080, "height": 1920},
            {"codec_type": "audio"},
        ],
    }

    with patch("pipeline.quality_gate.probe_video", return_value=mock_probe), \
         patch("pipeline.quality_gate.sample_frames_for_black", return_value=(True, "ok")):
        res = validate_short_quality(fake_video)
        assert res.passed is False
        assert any("below minimum 30.0s" in e for e in res.errors)


def test_duration_valid_30_to_60s_passes_quality_gate(tmp_path):
    fake_video = tmp_path / "valid_short.mp4"
    fake_video.write_bytes(b"x" * 60_000)

    mock_probe = {
        "format": {"duration": "42.0"},
        "streams": [
            {"codec_type": "video", "width": 1080, "height": 1920},
            {"codec_type": "audio"},
        ],
    }

    with patch("pipeline.quality_gate.probe_video", return_value=mock_probe), \
         patch("pipeline.quality_gate.sample_frames_for_black", return_value=(True, "ok")):
        res = validate_short_quality(fake_video)
        assert res.passed is True
        assert res.duration == 42.0
