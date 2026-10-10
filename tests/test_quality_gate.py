import pytest
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
