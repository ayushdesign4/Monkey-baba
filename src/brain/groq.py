"""Fallback #1 Brain Provider: Groq API."""

import json
import urllib.request
import urllib.error
from typing import Optional
from src.config import GROQ_API_KEY
from src.utils.logging import log

class GroqProvider:
    name = "groq"

    def __init__(self, api_key: Optional[str] = None, model: str = "llama-3.3-70b-versatile"):
        self.api_key = api_key or GROQ_API_KEY
        self.model = model

    def is_configured(self) -> bool:
        return bool(self.api_key and len(self.api_key) > 5)

    def generate(self, prompt: str, system_instruction: str = "") -> str:
        """Call Groq chat completion API with descriptive User-Agent header."""
        if not self.is_configured():
            raise ValueError("GROQ_API_KEY is not configured or invalid.")

        url = "https://api.groq.com/openai/v1/chat/completions"

        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 4096
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": "Monkey-Baba/1.0"
            },
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                choices = data.get("choices", [])
                if not choices:
                    raise RuntimeError("Groq returned empty choices.")
                return choices[0].get("message", {}).get("content", "").strip()
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Groq HTTP {e.code}: {err_body}")
        except Exception as e:
            raise RuntimeError(f"Groq request failed: {e}")
