"""Fallback #2 Brain Provider: Configurable OpenAI-compatible LLM."""

import json
import urllib.request
import urllib.error
from typing import Optional
from src.config import BACKUP_LLM_API_KEY, BACKUP_LLM_BASE_URL, BACKUP_LLM_MODEL

class BackupLLMProvider:
    name = "backup"

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or BACKUP_LLM_API_KEY
        self.base_url = (base_url or BACKUP_LLM_BASE_URL).rstrip("/")
        self.model = model or BACKUP_LLM_MODEL

    def is_configured(self) -> bool:
        return bool(self.api_key and len(self.api_key) > 5)

    def generate(self, prompt: str, system_instruction: str = "") -> str:
        """Call OpenAI-compatible backup provider."""
        if not self.is_configured():
            raise ValueError("BACKUP_LLM_API_KEY is not configured.")

        url = f"{self.base_url}/chat/completions"

        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            },
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            raise RuntimeError(f"Backup LLM provider failed: {e}")
