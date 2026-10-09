"""Primary Brain Provider: Google Gemini API with bounded retries and exponential backoff."""

import json
import os
import time
import urllib.request
import urllib.error
from typing import Optional
from src.config import GEMINI_API_KEY
from src.utils.logging import log, log_warn, log_error

TRANSIENT_HTTP_CODES = {429, 500, 502, 503, 504}
PERMANENT_HTTP_CODES = {400, 401, 403, 404}

class GeminiProvider:
    name = "gemini"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_retries: int = 3,
        initial_delay: float = 2.0,
        backoff_factor: float = 2.0,
        max_delay: float = 30.0
    ):
        self.api_key = api_key or GEMINI_API_KEY
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.backoff_factor = backoff_factor
        self.max_delay = max_delay

    def is_configured(self) -> bool:
        return bool(self.api_key and len(self.api_key) > 5)

    def generate(self, prompt: str, system_instruction: str = "") -> str:
        """Call Gemini REST endpoint with bounded exponential backoff on transient errors."""
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

        delay = self.initial_delay
        last_error = None

        for attempt in range(1, self.max_retries + 1):
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "Monkey-Baba/1.0"
                },
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
                last_error = RuntimeError(f"Gemini HTTP {e.code}: {err_body}")

                # Do not retry permanent errors
                if e.code in PERMANENT_HTTP_CODES or e.code not in TRANSIENT_HTTP_CODES:
                    log_warn("GEMINI", f"Permanent HTTP {e.code} error from Gemini. Not retrying.")
                    raise last_error

                # Transient error handling (503, 429, 500, etc.)
                if attempt >= self.max_retries:
                    log_error("GEMINI", f"Gemini HTTP {e.code} failed after {self.max_retries} attempts.")
                    raise last_error

                # Respect Retry-After header if provided
                wait_time = delay
                retry_after = e.headers.get("Retry-After") if hasattr(e, "headers") and e.headers else None
                if retry_after:
                    try:
                        parsed_wait = float(retry_after)
                        if parsed_wait > 0:
                            wait_time = min(parsed_wait, self.max_delay)
                    except ValueError:
                        pass

                log_warn("GEMINI", f"Transient HTTP {e.code} (attempt {attempt}/{self.max_retries}). Retrying in {wait_time:.1f}s...")
                time.sleep(wait_time)
                delay = min(delay * self.backoff_factor, self.max_delay)

            except (urllib.error.URLError, TimeoutError) as e:
                last_error = RuntimeError(f"Gemini connection error: {e}")
                if attempt >= self.max_retries:
                    log_error("GEMINI", f"Gemini request failed after {self.max_retries} attempts: {e}")
                    raise last_error

                log_warn("GEMINI", f"Connection error on attempt {attempt}/{self.max_retries}: {e}. Retrying in {delay:.1f}s...")
                time.sleep(delay)
                delay = min(delay * self.backoff_factor, self.max_delay)

            except Exception as e:
                last_error = RuntimeError(f"Gemini API request failed: {e}")
                raise last_error

        raise last_error or RuntimeError("Gemini failed with unknown error.")
