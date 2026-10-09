"""Primary Brain Provider: Google Gemini API with dynamic model discovery, quota failover, and bounded retries."""

import json
import os
import time
import urllib.request
import urllib.error
from typing import Optional, List, Set
from src.config import GEMINI_API_KEY
from src.utils.logging import log, log_warn, log_error

TRANSIENT_HTTP_CODES = {500, 502, 503, 504}
PERMANENT_HTTP_CODES = {400, 401, 403, 404}

class GeminiProvider:
    name = "gemini"

    # Run-level caches to avoid redundant API calls
    _cached_models: Optional[List[str]] = None
    _exhausted_models: Set[str] = set()

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_retries: int = 2,
        initial_delay: float = 1.0,
        backoff_factor: float = 2.0,
        max_delay: float = 10.0
    ):
        self.api_key = api_key or GEMINI_API_KEY
        self.explicit_model = model or os.getenv("GEMINI_MODEL")
        self.active_model: Optional[str] = None
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.backoff_factor = backoff_factor
        self.max_delay = max_delay

    @classmethod
    def reset_cache(cls):
        """Reset discovery cache and exhausted models tracker (useful for tests and new runs)."""
        cls._cached_models = None
        cls._exhausted_models = set()

    @property
    def model(self) -> str:
        """Return the active model or top eligible model."""
        if self.active_model:
            return self.active_model
        if self.explicit_model:
            return self.explicit_model
        models = self.discover_models()
        return models[0] if models else "gemini-2.5-flash"

    @model.setter
    def model(self, val: str):
        self.explicit_model = val
        self.active_model = val

    def is_configured(self) -> bool:
        return bool(self.api_key and len(self.api_key) > 5)

    def discover_models(self) -> List[str]:
        """
        Discover eligible text-generation models via the official Gemini Models API.
        Caches results for the run to avoid redundant calls.
        """
        if GeminiProvider._cached_models is not None:
            return GeminiProvider._cached_models

        if not self.is_configured():
            return []

        # If user explicitly set a model via param or env, prioritize it
        candidate_list: List[str] = []
        if self.explicit_model:
            candidate_list.append(self.explicit_model)

        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={self.api_key}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Monkey-Baba/1.0",
                "Content-Type": "application/json"
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            raw_models = data.get("models", [])
            discovered: List[str] = []
            for m in raw_models:
                methods = m.get("supportedGenerationMethods", [])
                if "generateContent" not in methods:
                    continue

                raw_name = m.get("name", "")
                mid = raw_name.split("/")[-1] if raw_name.startswith("models/") else raw_name
                lower_id = mid.lower()

                # Filter out embeddings, vision/image-only, audio-only
                if any(k in lower_id for k in ["embedding", "imagen", "aqa", "tts", "whisper"]):
                    continue

                discovered.append(mid)

            # Sort with preference for fast, suitable text-generation models:
            # 1. Flash models (e.g. gemini-2.5-flash > gemini-2.0-flash > gemini-1.5-flash)
            # 2. Pro models
            # 3. Other general models
            def model_priority(m_id: str) -> tuple:
                l = m_id.lower()
                is_flash = 0 if "flash" in l else 1
                ver = 99
                if "2.5" in l:
                    ver = 0
                elif "2.0" in l:
                    ver = 1
                elif "1.5" in l:
                    ver = 2
                elif "3." in l:
                    ver = 3
                return (is_flash, ver, m_id)

            discovered.sort(key=model_priority)
            for d in discovered:
                if d not in candidate_list:
                    candidate_list.append(d)

            log("GEMINI", f"Discovered {len(discovered)} eligible generateContent models. Candidates: {candidate_list[:4]}")
            GeminiProvider._cached_models = candidate_list
            return candidate_list

        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="ignore")
            log_warn("GEMINI", f"Gemini Models API returned HTTP {e.code}: {err[:150]}")
            if candidate_list:
                GeminiProvider._cached_models = candidate_list
                return candidate_list
            return []
        except Exception as e:
            log_warn("GEMINI", f"Gemini Models discovery failed ({e}).")
            if candidate_list:
                GeminiProvider._cached_models = candidate_list
                return candidate_list
            return []

    def generate(self, prompt: str, system_instruction: str = "") -> str:
        """
        Call Gemini REST endpoint trying discovered eligible models.
        When a model returns HTTP 429 quota exhaustion, immediately tries the next eligible model without sleeping.
        """
        if not self.is_configured():
            raise ValueError("GEMINI_API_KEY is not configured or invalid.")

        models = self.discover_models()
        candidates = [m for m in models if m not in GeminiProvider._exhausted_models]

        if not candidates:
            raise RuntimeError("No available Gemini models (all exhausted or none discovered).")

        last_error = None

        for model in candidates:
            log("GEMINI", f"Attempting text generation with Gemini model '{model}'...")
            try:
                result = self._execute_model_call(model, prompt, system_instruction)
                self.active_model = model
                return result

            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="ignore")
                # Redact API key if present in error
                if self.api_key and self.api_key in err_body:
                    err_body = err_body.replace(self.api_key, "[REDACTED]")

                # HTTP 429 / Quota Exhaustion
                if e.code == 429 or "quota" in err_body.lower() or "resource_exhausted" in err_body.lower():
                    log_warn("GEMINI", f"Model '{model}' quota exhausted (HTTP 429). Marking exhausted and trying next model immediately...")
                    GeminiProvider._exhausted_models.add(model)
                    last_error = RuntimeError(f"Gemini HTTP 429 quota exhausted for {model}")
                    continue  # Do not sleep or retry this model; try next model immediately!

                # Permanent errors (e.g. invalid key 401, permission 403, bad request 400)
                if e.code in PERMANENT_HTTP_CODES:
                    log_warn("GEMINI", f"Permanent HTTP {e.code} error from Gemini ({model}). Not retrying.")
                    raise RuntimeError(f"Gemini HTTP {e.code}: {err_body[:200]}")

                # Transient errors (500, 502, 503, 504)
                log_warn("GEMINI", f"HTTP {e.code} error on model '{model}'. Trying next eligible model...")
                last_error = RuntimeError(f"Gemini HTTP {e.code}: {err_body[:200]}")
                continue

            except (urllib.error.URLError, TimeoutError) as e:
                log_warn("GEMINI", f"Network connection error calling model '{model}': {e}. Trying next model...")
                last_error = RuntimeError(f"Gemini connection error: {e}")
                continue

            except Exception as e:
                log_warn("GEMINI", f"Unexpected error calling model '{model}': {e}. Trying next model...")
                last_error = e
                continue

        raise last_error or RuntimeError("All eligible Gemini models failed.")

    def _execute_model_call(self, model_id: str, prompt: str, system_instruction: str = "") -> str:
        """Execute request to a single Gemini model with bounded retries for transient HTTP 503."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={self.api_key}"

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
                # If HTTP 503 or 500, do bounded retry for this specific model
                if e.code in TRANSIENT_HTTP_CODES and attempt < self.max_retries:
                    wait_time = delay
                    retry_after = e.headers.get("Retry-After") if hasattr(e, "headers") and e.headers else None
                    if retry_after:
                        try:
                            wait_time = min(float(retry_after), self.max_delay)
                        except ValueError:
                            pass
                    log_warn("GEMINI", f"Transient HTTP {e.code} on '{model_id}' (attempt {attempt}/{self.max_retries}). Retrying in {wait_time:.1f}s...")
                    time.sleep(wait_time)
                    delay = min(delay * self.backoff_factor, self.max_delay)
                    continue

                # Re-raise to let caller handle 429, permanent, or move to next model
                raise
