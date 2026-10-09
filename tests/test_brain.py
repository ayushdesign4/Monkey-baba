"""Unit tests for Brain providers, headers, retries, and fallback transitions."""

import unittest
import json
from unittest.mock import patch, MagicMock
import urllib.error

from src.brain.gemini import GeminiProvider
from src.brain.groq import GroqProvider
from src.brain.backup import LocalFallbackProvider
from src.brain.manager import BrainManager

class TestBrainProviders(unittest.TestCase):

    def test_groq_request_headers(self):
        """Verify GroqProvider sets User-Agent: Monkey-Baba/1.0 and headers correctly."""
        provider = GroqProvider(api_key="gsk_test12345678901234567890")
        
        captured_req = None

        def mock_urlopen(req, timeout=None):
            nonlocal captured_req
            captured_req = req
            mock_resp = MagicMock()
            mock_resp.__enter__.return_value = mock_resp
            mock_resp.read.return_value = json.dumps({
                "choices": [{"message": {"content": "GROQ_OK"}}]
            }).encode("utf-8")
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            res = provider.generate("Test prompt")
            self.assertEqual(res, "GROQ_OK")
            self.assertEqual(provider.model, "openai/gpt-oss-120b")
            self.assertIsNotNone(captured_req)
            self.assertEqual(captured_req.headers.get("User-agent"), "Monkey-Baba/1.0")
            self.assertEqual(captured_req.headers.get("Content-type"), "application/json")
            self.assertIn("Bearer gsk_test", captured_req.headers.get("Authorization", ""))

    def test_gemini_retries_transient_error_and_succeeds(self):
        """Verify GeminiProvider retries HTTP 503 and respects backoff before succeeding."""
        provider = GeminiProvider(
            api_key="AIzaSyTestKey12345678901234567890",
            max_retries=3,
            initial_delay=0.01,
            backoff_factor=1.5
        )

        attempts = 0

        def mock_urlopen(req, timeout=None):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                fp = MagicMock()
                fp.read.return_value = b'{"error": {"code": 503, "message": "High demand"}}'
                headers = MagicMock()
                headers.get.side_effect = lambda k: "0.01" if k == "Retry-After" else None
                raise urllib.error.HTTPError(req.full_url, 503, "Service Unavailable", headers, fp)
            
            mock_resp = MagicMock()
            mock_resp.__enter__.return_value = mock_resp
            mock_resp.read.return_value = json.dumps({
                "candidates": [{"content": {"parts": [{"text": "GEMINI_OK"}]}}]
            }).encode("utf-8")
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            res = provider.generate("Test prompt")
            self.assertEqual(res, "GEMINI_OK")
            self.assertEqual(attempts, 2)

    def test_gemini_fails_fast_on_permanent_error(self):
        """Verify GeminiProvider does NOT retry on HTTP 401/403/404/400."""
        provider = GeminiProvider(
            api_key="AIzaSyTestKey12345678901234567890",
            max_retries=3,
            initial_delay=0.01
        )

        attempts = 0

        def mock_urlopen(req, timeout=None):
            nonlocal attempts
            attempts += 1
            fp = MagicMock()
            fp.read.return_value = b'{"error": {"code": 401, "message": "Invalid API Key"}}'
            raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, fp)

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            with self.assertRaises(RuntimeError) as ctx:
                provider.generate("Test prompt")
            self.assertIn("HTTP 401", str(ctx.exception))
            self.assertEqual(attempts, 1)

    def test_fallback_transitions_to_groq_and_local(self):
        """Verify BrainManager transitions: Gemini fails -> Groq fails -> Local Python fallback."""
        manager = BrainManager()
        manager.primary.is_configured = MagicMock(return_value=True)
        manager.fallback_1.is_configured = MagicMock(return_value=True)

        # Mock Gemini to fail
        manager.primary.generate = MagicMock(side_effect=RuntimeError("Gemini unavailable"))
        # Mock Groq to succeed first
        manager.fallback_1.generate = MagicMock(return_value="GROQ_RESPONSE")
        
        text, provider, fallback_used = manager.generate_text("Test prompt")
        self.assertEqual(text, "GROQ_RESPONSE")
        self.assertEqual(provider, "groq")
        self.assertTrue(fallback_used)

        # Now mock Groq to also fail -> should cleanly transition to local fallback
        manager.fallback_1.generate = MagicMock(side_effect=RuntimeError("Groq unavailable"))
        text2, provider2, fallback_used2 = manager.generate_text("Provide one sentence about space exploration.")
        self.assertEqual(provider2, "local")
        self.assertTrue(fallback_used2)
        self.assertIn("Space exploration", text2)

    def test_local_fallback_produces_script_and_scenes(self):
        """Verify local fallback produces valid script >= 100 words and 7 scenes."""
        local_fb = LocalFallbackProvider()
        self.assertTrue(local_fb.is_configured())

        script_json_str = local_fb.generate('Topic: "The Bermuda Enigma" Master Storyteller full_narration min_words: 100')
        script = json.loads(script_json_str)
        self.assertIn("full_narration", script)
        self.assertGreaterEqual(len(script["full_narration"].split()), 100)
        self.assertEqual(len(script["scenes"]), 7)

if __name__ == "__main__":
    unittest.main()
