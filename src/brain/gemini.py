"""Primary Brain Provider: Google Gemini API."""

import json
import os
import urllib.request
import urllib.error
from typing import Optional
from src.config import GEMINI_API_KEY
from src.utils.logging import log, log_error

class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or GEMINI_API_KEY
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

    def is_configured(self) -> bool:
        return bool(self.api_key and len(self.api_key) > 5)

    def generate(self, prompt: str, system_instruction: str = "") -> str:
        """Call Gemini REST endpoint."""
        if not self.is_configured():
            raise ValueError("GEMINI_API_KEY is not configured or invalid.")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

        contents = []
        if system_instruction:
            contents.append({"role": "user", "parts": [{"text": f"System context: {system_instruction}"}]})
            contents.append({"role": "model", "parts": [{"text": "Understood."}]})
        
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.7,
                "topP": 0.95,
                "maxOutputTokens": 4096,
            }
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                candidates = data.get("candidates", [])
                if not candidates:
                    raise RuntimeError("Gemini returned empty candidate list.")
                text_part = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                if not text_part:
                    raise RuntimeError("Gemini returned empty content text.")
                return text_part.strip()
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Gemini HTTP {e.code}: {err_body}")
        except Exception as e:
            raise RuntimeError(f"Gemini API request failed: {e}")
