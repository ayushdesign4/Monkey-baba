"""Unit tests for Agnes video and image providers, endpoints, and fallbacks."""

import unittest
import json
from unittest.mock import patch, MagicMock
from pathlib import Path

from src.video.agnes import AgnesVideoProvider
from src.thumbnail.agnes import AgnesImageProvider
from src.video.manager import VideoManager
from src.thumbnail.manager import ThumbnailManager

class TestAgnesProviders(unittest.TestCase):

    def test_default_base_url_and_configured(self):
        """Verify Agnes providers default to official apihub.agnes-ai.com endpoint."""
        v_prov = AgnesVideoProvider(api_key="sk_test_key_12345")
        self.assertEqual(v_prov.base_url, "https://apihub.agnes-ai.com/v1")
        self.assertTrue(v_prov.is_configured())

        img_prov = AgnesImageProvider(api_key="sk_test_key_12345")
        self.assertEqual(img_prov.base_url, "https://apihub.agnes-ai.com/v1")
        self.assertTrue(img_prov.is_configured())

        unconf_v = AgnesVideoProvider(api_key="")
        self.assertFalse(unconf_v.is_configured())

    def test_video_generation_request_format(self):
        """Verify video generation sends POST to /videos with correct headers and payload."""
        v_prov = AgnesVideoProvider(api_key="sk_test_key_12345")
        captured_requests = []

        def mock_urlopen(req, timeout=None):
            captured_requests.append(req)
            resp = MagicMock()
            resp.__enter__.return_value = resp
            if req.full_url.endswith("/videos"):
                resp.read.return_value = json.dumps({"video_id": "task_12345"}).encode("utf-8")
            elif "agnesapi" in req.full_url:
                resp.read.return_value = json.dumps({
                    "status": "completed",
                    "video_url": "https://cdn.agnes-ai.com/output.mp4"
                }).encode("utf-8")
            elif "output.mp4" in req.full_url:
                resp.read.return_value = b"MOCK_MP4_BYTES"
            return resp

        out_path = Path("tests/mock_scene.mp4")
        with patch("urllib.request.urlopen", side_effect=mock_urlopen), \
             patch("time.sleep", return_value=None):
            try:
                res = v_prov.generate_clip("A futuristic city", out_path, duration_seconds=5)
                self.assertEqual(res, out_path)
                self.assertTrue(out_path.exists())
            finally:
                if out_path.exists():
                    out_path.unlink()

        self.assertGreaterEqual(len(captured_requests), 2)
        submit_req = captured_requests[0]
        self.assertEqual(submit_req.full_url, "https://apihub.agnes-ai.com/v1/videos")
        self.assertEqual(submit_req.headers.get("User-agent"), "Monkey-Baba/1.0")
        self.assertEqual(submit_req.headers.get("Authorization"), "Bearer sk_test_key_12345")

    def test_image_generation_request_format(self):
        """Verify image generation sends POST to /images/generations with correct headers."""
        img_prov = AgnesImageProvider(api_key="sk_test_key_12345")
        captured_requests = []

        def mock_urlopen(req, timeout=None):
            captured_requests.append(req)
            resp = MagicMock()
            resp.__enter__.return_value = resp
            if req.full_url.endswith("/images/generations"):
                resp.read.return_value = json.dumps({
                    "data": [{"url": "https://cdn.agnes-ai.com/thumb.jpg"}]
                }).encode("utf-8")
            elif "thumb.jpg" in req.full_url:
                resp.read.return_value = b"MOCK_JPG_BYTES"
            return resp

        out_path = Path("tests/mock_thumb.jpg")
        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            try:
                res = img_prov.generate_image("A futuristic cityscape", out_path)
                self.assertEqual(res, out_path)
                self.assertTrue(out_path.exists())
            finally:
                if out_path.exists():
                    out_path.unlink()

        self.assertEqual(len(captured_requests), 2)
        img_req = captured_requests[0]
        self.assertEqual(img_req.full_url, "https://apihub.agnes-ai.com/v1/images/generations")
        self.assertEqual(img_req.headers.get("User-agent"), "Monkey-Baba/1.0")
        self.assertEqual(img_req.headers.get("Authorization"), "Bearer sk_test_key_12345")

    def test_video_fallback_triggers_on_agnes_failure(self):
        """Verify VideoManager falls back to procedural FFmpeg when Agnes fails."""
        vm = VideoManager()
        vm.primary.is_configured = MagicMock(return_value=True)
        vm.primary.generate_clip = MagicMock(side_effect=RuntimeError("DNS failure"))
        vm.fallback.generate_clip = MagicMock(return_value=Path("mock.mp4"))

        scenes = [{"scene_number": 1, "duration_seconds": 5, "video_prompt": "Prompt"}]
        run_dir = Path("tests/mock_run")
        run_dir.mkdir(exist_ok=True)

        try:
            clips, provider, fallback_used = vm.generate_scene_clips(scenes, run_dir)
            self.assertEqual(provider, "fallback")
            self.assertTrue(fallback_used)
            self.assertEqual(vm.fallback.generate_clip.call_count, 1)
        finally:
            if (run_dir / "clips").exists():
                import shutil
                shutil.rmtree(run_dir)

if __name__ == "__main__":
    unittest.main()
