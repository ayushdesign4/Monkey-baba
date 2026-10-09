"""End-to-End preflight integration test for Monkey-Baba pipeline stages."""

import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import tempfile
import json
import shutil

from src.orchestrator import MonkeyBabaOrchestrator
from src.video.quality_gate import VisualQualityGate, VisualQualityError

class TestPipelineIntegration(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)

    @patch("src.orchestrator.concatenate_clips")
    @patch("src.orchestrator.VideoFinalizer.finalize_video")
    @patch("src.orchestrator.get_media_duration", return_value=45.0)
    @patch("src.video.quality_gate.VisualQualityGate.validate_or_raise")
    def test_full_orchestrator_pipeline_flow(
        self,
        mock_quality_gate,
        mock_get_dur,
        mock_finalize,
        mock_concat
    ):
        """Test full orchestrator pipeline stage transitions from topic to simulated upload."""
        orchestrator = MonkeyBabaOrchestrator()

        # Mock video generation to produce mock scene files
        def side_effect_gen_clips(scenes, run_dir):
            clips_dir = run_dir / "clips"
            clips_dir.mkdir(parents=True, exist_ok=True)
            paths = []
            for s in scenes:
                p = clips_dir / f"scene_{s['scene_number']:03d}.mp4"
                p.write_bytes(b"MOCK_CLIP")
                paths.append(p)
            return paths, "agnes", False

        orchestrator.video_mgr.generate_scene_clips = MagicMock(side_effect=side_effect_gen_clips)

        # Mock finalize to write dummy final video
        def side_effect_finalize(reel_path, narration_path, thumbnail_path, output_path, include_thumbnail_intro=True):
            output_path.write_bytes(b"0" * 60_000)
            return output_path

        mock_finalize.side_effect = side_effect_finalize

        # Mock TTS to write dummy audio
        def side_effect_tts(text, output_path):
            output_path.write_bytes(b"0" * 5_000)
            return output_path

        orchestrator.tts_mgr.generate_speech = MagicMock(side_effect=side_effect_tts)

        # Execute pipeline in dry_run mode
        record = orchestrator.run_pipeline(
            forced_topic="The Lost Whispering Oasis of the Sahara",
            dry_run=True
        )

        self.assertIsNotNone(record)
        self.assertEqual(record["status"], "simulated")
        self.assertEqual(record["topic"], "The Lost Whispering Oasis of the Sahara")
        self.assertIn("The Lost Whispering Oasis", record["title"])
        self.assertTrue(mock_quality_gate.called)
        self.assertEqual(record["duration_seconds"], 45.0)
        self.assertTrue(Path(record["youtube_url"]).as_posix() or "youtube" in record["youtube_url"])

    def test_quality_gate_stops_pipeline_before_upload(self):
        """Verify pipeline halts at QUALITY_GATE stage when video is defective, never uploading."""
        orchestrator = MonkeyBabaOrchestrator()

        orchestrator.video_mgr.generate_scene_clips = MagicMock(return_value=([Path("dummy.mp4")], "fallback", True))
        orchestrator.tts_mgr.generate_speech = MagicMock(side_effect=lambda text, path: path.write_bytes(b"0"*5000))

        with patch("src.orchestrator.concatenate_clips"), \
             patch("src.orchestrator.VideoFinalizer.finalize_video", side_effect=lambda **kwargs: kwargs["output_path"].write_bytes(b"0"*60000)), \
             patch("src.video.quality_gate.VisualQualityGate.validate_or_raise", side_effect=VisualQualityError("Black frames")), \
             patch.object(orchestrator.uploader, "upload_short") as mock_upload:

            with self.assertRaises(VisualQualityError):
                orchestrator.run_pipeline(forced_topic="Defective Video Test", dry_run=True)

            # CRITICAL: Uploader must NEVER have been called!
            self.assertFalse(mock_upload.called)

    def tearDown(self):
        self.temp_dir.cleanup()

if __name__ == "__main__":
    unittest.main()
