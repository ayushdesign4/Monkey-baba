"""Unit tests for the visual-quality upload gate."""

import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import tempfile
from PIL import Image

from src.video.quality_gate import VisualQualityGate, VisualQualityError
from src.youtube.uploader import YouTubeUploader

class TestVisualQualityGate(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_missing_or_tiny_file_fails(self):
        """Verify non-existent or suspiciously small files are rejected."""
        missing = self.tmp_path / "missing.mp4"
        with self.assertRaises(VisualQualityError):
            VisualQualityGate.validate_or_raise(missing)

        tiny = self.tmp_path / "tiny.mp4"
        tiny.write_bytes(b"12345")
        with self.assertRaises(VisualQualityError):
            VisualQualityGate.validate_or_raise(tiny)

    def test_duration_out_of_bounds_fails(self):
        """Verify video duration shorter than min or longer than max fails."""
        dummy_video = self.tmp_path / "test.mp4"
        dummy_video.write_bytes(b"0" * 60_000)

        # Mock metadata with duration = 15s (too short for 30s min)
        with patch.object(VisualQualityGate, "inspect_metadata", return_value={"duration": 15.0, "width": 1080, "height": 1920}):
            with self.assertRaises(VisualQualityError) as ctx:
                VisualQualityGate.validate_or_raise(dummy_video, min_duration=30.0, max_duration=60.0)
            self.assertIn("duration", str(ctx.exception).lower())

        # Mock metadata with duration = 75s (too long for 60s max)
        with patch.object(VisualQualityGate, "inspect_metadata", return_value={"duration": 75.0, "width": 1080, "height": 1920}):
            with self.assertRaises(VisualQualityError) as ctx:
                VisualQualityGate.validate_or_raise(dummy_video, min_duration=30.0, max_duration=60.0)
            self.assertIn("duration", str(ctx.exception).lower())

    def test_wrong_aspect_ratio_fails(self):
        """Verify landscape (16:9) or non-vertical aspect ratios fail."""
        dummy_video = self.tmp_path / "test.mp4"
        dummy_video.write_bytes(b"0" * 60_000)

        # 1920x1080 horizontal landscape
        with patch.object(VisualQualityGate, "inspect_metadata", return_value={"duration": 45.0, "width": 1920, "height": 1080}):
            with self.assertRaises(VisualQualityError) as ctx:
                VisualQualityGate.validate_or_raise(dummy_video)
            self.assertIn("aspect ratio", str(ctx.exception).lower())

    def test_black_frames_fail_quality_gate(self):
        """Verify video where all sample frames are pitch black fails upload gate."""
        dummy_video = self.tmp_path / "test.mp4"
        dummy_video.write_bytes(b"0" * 60_000)

        meta = {"duration": 45.0, "width": 1080, "height": 1920}
        black_stats = [
            {"brightness": 0.0, "std_dev": 0.0},
            {"brightness": 0.2, "std_dev": 0.1},
            {"brightness": 0.0, "std_dev": 0.0},
            {"brightness": 0.1, "std_dev": 0.1},
        ]

        with patch.object(VisualQualityGate, "inspect_metadata", return_value=meta), \
             patch.object(VisualQualityGate, "inspect_sample_frames", return_value=black_stats):
            with self.assertRaises(VisualQualityError) as ctx:
                VisualQualityGate.validate_or_raise(dummy_video)
            self.assertIn("pitch black", str(ctx.exception).lower())

    def test_flat_blank_color_fails_quality_gate(self):
        """Verify video with flat single solid color and zero visual detail fails."""
        dummy_video = self.tmp_path / "test.mp4"
        dummy_video.write_bytes(b"0" * 60_000)

        meta = {"duration": 45.0, "width": 1080, "height": 1920}
        flat_stats = [
            {"brightness": 50.0, "std_dev": 0.0},
            {"brightness": 50.0, "std_dev": 0.2},
            {"brightness": 50.0, "std_dev": 0.1},
            {"brightness": 50.0, "std_dev": 0.0},
        ]

        with patch.object(VisualQualityGate, "inspect_metadata", return_value=meta), \
             patch.object(VisualQualityGate, "inspect_sample_frames", return_value=flat_stats):
            with self.assertRaises(VisualQualityError) as ctx:
                VisualQualityGate.validate_or_raise(dummy_video)
            self.assertIn("lacks visible visual imagery", str(ctx.exception).lower())

    def test_valid_video_with_visible_imagery_passes(self):
        """Verify video with valid dimensions, duration, and rich visual detail passes gate."""
        dummy_video = self.tmp_path / "test.mp4"
        dummy_video.write_bytes(b"0" * 60_000)

        meta = {"duration": 45.0, "width": 1080, "height": 1920}
        good_stats = [
            {"brightness": 45.0, "std_dev": 28.0},
            {"brightness": 60.0, "std_dev": 35.0},
            {"brightness": 40.0, "std_dev": 22.0},
            {"brightness": 55.0, "std_dev": 30.0},
        ]

        with patch.object(VisualQualityGate, "inspect_metadata", return_value=meta), \
             patch.object(VisualQualityGate, "inspect_sample_frames", return_value=good_stats):
            result = VisualQualityGate.validate_or_raise(dummy_video)
            self.assertTrue(result["passed"])
            self.assertEqual(result["duration"], 45.0)
            self.assertEqual(result["width"], 1080)
            self.assertEqual(result["height"], 1920)

    def test_youtube_uploader_stops_upload_on_bad_video(self):
        """Verify YouTube uploader calls quality gate and halts when video is broken."""
        uploader = YouTubeUploader()
        broken_video = self.tmp_path / "broken.mp4"
        broken_video.write_bytes(b"0" * 10)  # Under 50KB

        metadata = {"title": "Test Short #Shorts"}
        with self.assertRaises(VisualQualityError):
            uploader.upload_short(broken_video, metadata, dry_run=True)

if __name__ == "__main__":
    unittest.main()
