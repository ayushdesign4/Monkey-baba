"""Google Gemini LLM Provider with dynamic model discovery and failover.

Implements primary text generation provider for Monkey-Baba:
1. Supports GEMINI_API_KEY.
2. Dynamically discovers generateContent models (gemini-2.5-flash, gemini-2.0-flash, gemini-1.5-flash).
3. Handles transient 503/500 with bounded retries and Retry-After support.
4. On 429 quota exhaustion, immediately fails over to next candidate Gemini model.
5. Completely redacts GEMINI_API_KEY from logs and errors.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any
import urllib.error
import urllib.request

from pipeline.channel_presets import ChannelPreset

REQUEST_TIMEOUT = 25.0
MAX_RETRIES = 2
BACKOFF_FACTOR = 1.5
INITIAL_DELAY = 1.0
MAX_DELAY = 10.0

DEFAULT_CANDIDATE_MODELS = [
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
]


class GeminiProvider:
    """Stateful model discovery cache, active model retention, and quota tracker."""
    _cached_models: list[str] = []
    _cache_timestamp: float = 0.0
    _exhausted_models: set[str] = set()
    _active_model: str | None = None

    @classmethod
    def reset(cls) -> None:
        cls._cached_models = []
        cls._cache_timestamp = 0.0
        cls._exhausted_models.clear()
        cls._active_model = None


def is_gemini_configured() -> bool:
    """Return True if GEMINI_API_KEY is present and non-empty."""
    return bool(os.environ.get("GEMINI_API_KEY", "").strip())


def sanitize_text(text: str, secret: str | None = None) -> str:
    """Remove sensitive API key strings from text."""
    if not text:
        return ""
    keys_to_redact = [
        secret,
        os.environ.get("GEMINI_API_KEY"),
        os.environ.get("GROQ_API_KEY"),
        os.environ.get("OPENROUTER_API_KEY"),
    ]
    sanitized = text
    for key in keys_to_redact:
        if key and len(key) >= 6:
            sanitized = sanitized.replace(key, "[REDACTED]")
    return sanitized


def discover_gemini_models(api_key: str) -> list[str]:
    """Query Google Gemini models API to discover eligible text generation models."""
    now = time.time()
    if GeminiProvider._cached_models and (now - GeminiProvider._cache_timestamp < 300.0):
        return list(GeminiProvider._cached_models)

    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Monkey-Baba/1.0"},
        method="GET",
    )

    discovered: list[str] = []
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            raw_models = data.get("models", [])
            for m in raw_models:
                methods = m.get("supportedGenerationMethods", [])
                if "generateContent" not in methods:
                    continue

                raw_name = m.get("name", "")
                mid = raw_name.split("/")[-1] if raw_name.startswith("models/") else raw_name
                lower_id = mid.lower()

                if any(k in lower_id for k in ["embedding", "imagen", "aqa", "tts", "whisper"]):
                    continue

                discovered.append(mid)

            def model_priority(m_id: str) -> tuple[int, float, str]:
                l = m_id.lower()
                is_flash = 0 if "flash" in l else 1
                match = re.search(r"gemini-(\d+(?:\.\d+)?)", l)
                ver = float(match.group(1)) if match else 1.0
                return (is_flash, -ver, m_id)

            discovered.sort(key=model_priority)
    except Exception as exc:
        print(f"[WARN] Gemini models discovery failed ({sanitize_text(str(exc), api_key)}). Using fallback list.")

    candidates = list(discovered) if discovered else list(DEFAULT_CANDIDATE_MODELS)
    GeminiProvider._cached_models = candidates
    GeminiProvider._cache_timestamp = now
    return candidates


def _execute_gemini_request(
    api_key: str,
    model_id: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
) -> str:
    """Execute generateContent POST request to a single Gemini model with bounded retries."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={api_key}"

    contents = []
    if system_prompt:
        contents.append({"role": "user", "parts": [{"text": f"System context: {system_prompt}"}]})
        contents.append({"role": "model", "parts": [{"text": "Understood."}]})
    contents.append({"role": "user", "parts": [{"text": user_prompt}]})

    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": 3072,
            "responseMimeType": "application/json",
        },
    }

    delay = INITIAL_DELAY
    for attempt in range(1, MAX_RETRIES + 1):
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Monkey-Baba/1.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                candidates = data.get("candidates", [])
                if not candidates:
                    raise RuntimeError(f"Gemini returned empty candidates list for {model_id}")
                parts = candidates[0].get("content", {}).get("parts", [])
                text_part = parts[0].get("text", "") if parts else ""
                if not text_part.strip():
                    raise RuntimeError(f"Gemini returned empty content text for {model_id}")
                return text_part.strip()

        except urllib.error.HTTPError as e:
            err_body = sanitize_text(e.read().decode("utf-8", errors="ignore"), api_key)
            if e.code == 400 and "responseMimeType" in err_body:
                # Retry once without responseMimeType
                payload["generationConfig"].pop("responseMimeType", None)
                continue

            if e.code in (500, 502, 503, 504) and attempt < MAX_RETRIES:
                wait_time = delay
                retry_after = e.headers.get("Retry-After") if e.headers else None
                if retry_after:
                    try:
                        wait_time = min(float(retry_after), MAX_DELAY)
                    except ValueError:
                        pass
                print(f"[WARN] Transient HTTP {e.code} on Gemini '{model_id}' (attempt {attempt}/{MAX_RETRIES}). Retrying in {wait_time:.1f}s...")
                time.sleep(wait_time)
                delay = min(delay * BACKOFF_FACTOR, MAX_DELAY)
                continue

            raise RuntimeError(f"HTTP {e.code}: {err_body[:150]}")


def call_gemini(
    preset: ChannelPreset,
    user_prompt: str,
    *,
    temperature: float = 0.85,
) -> dict[str, Any]:
    """Call Google Gemini with model discovery, retries, and quota failover.
    Returns parsed JSON dictionary.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    models = discover_gemini_models(api_key)
    candidates = [m for m in models if m not in GeminiProvider._exhausted_models]
    if not candidates:
        GeminiProvider._exhausted_models.clear()
        candidates = list(models)

    if not candidates:
        raise RuntimeError("No available Gemini models found.")

    # Re-use active model first if available and not exhausted
    if GeminiProvider._active_model and GeminiProvider._active_model in candidates:
        candidates.remove(GeminiProvider._active_model)
        candidates.insert(0, GeminiProvider._active_model)

    system_prompt = preset.get("groq_system_hint", "You are an expert horror writer.")
    last_error: Exception | None = None

    for model in candidates:
        print(f"[GEMINI] Attempting text generation with model '{model}'...")
        try:
            raw_text = _execute_gemini_request(api_key, model, system_prompt, user_prompt, temperature)

            # Strip markdown fences if present
            cleaned = raw_text.strip()
            if cleaned.startswith("```"):
                lines = cleaned.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip().startswith("```"):
                    lines = lines[:-1]
                cleaned = "\n".join(lines).strip()

            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1 and end > start:
                cleaned = cleaned[start : end + 1]

            data = json.loads(cleaned)
            data["_provider"] = "gemini"
            data["_model"] = model

            GeminiProvider._active_model = model
            print(f"[GEMINI] Text generation succeeded with model '{model}' (retained as active model).")
            return data

        except Exception as exc:
            err_msg = sanitize_text(str(exc), api_key)
            last_error = exc
            if "404" in err_msg or "not_found" in err_msg.lower() or "not found" in err_msg.lower():
                print(f"[WARN] Gemini model '{model}' not found (404). Marking unavailable and rotating...")
                GeminiProvider._exhausted_models.add(model)
                if GeminiProvider._active_model == model:
                    GeminiProvider._active_model = None
                continue

            if "429" in err_msg or "quota" in err_msg.lower() or "resource_exhausted" in err_msg.lower():
                print(f"[WARN] Gemini model '{model}' quota exhausted (429). Rotating to next model...")
                GeminiProvider._exhausted_models.add(model)
                if GeminiProvider._active_model == model:
                    GeminiProvider._active_model = None
                continue

            if "401" in err_msg or "403" in err_msg:
                print(f"[WARN] Permanent Gemini authorization error ({err_msg[:120]}). Halting Gemini sweep.")
                raise

            print(f"[WARN] Gemini model '{model}' failed: {err_msg[:120]}. Rotating...")
            GeminiProvider._exhausted_models.add(model)
            if GeminiProvider._active_model == model:
                GeminiProvider._active_model = None
            continue

    raise RuntimeError(f"All candidate Gemini models failed. Last error: {last_error}")
