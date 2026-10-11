"""OpenRouter Free-Model LLM Provider with dynamic catalogue discovery and failover.

Implements robust, zero-cost text generation fallback for Monkey-Baba:
1. Supports OPENROUTER_API_KEY, OPENROUTER_BASE_URL, OPENROUTER_MODEL.
2. Dynamically queries GET /models to discover free text-generation models (:free, price=0).
3. Strictly excludes paid models.
4. Handles transient errors (429 rate limit, 5xx, timeouts, invalid JSON) by rotating to next free model.
5. Handles account/auth errors (401, 403, 402) cleanly without pointless sweeps.
6. Reuses active model across calls in the same run; caches catalogue with TTL.
7. Completely redacts credentials from logs and error messages.
"""
from __future__ import annotations

import json
import os
import random
import re
import time
from typing import Any
import urllib.error
import urllib.request

from pipeline.channel_presets import ChannelPreset

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openrouter/free"
REQUEST_TIMEOUT = 25.0
CACHE_TTL = 300.0  # 5 minutes
MAX_MODEL_ATTEMPTS = 4

# HTTP Status codes classification
ACCOUNT_ERROR_CODES = {401, 402, 403}
TRANSIENT_ERROR_CODES = {408, 429, 500, 502, 503, 504}


class OpenRouterConfigError(RuntimeError):
    """Raised when OpenRouter API key is invalid or account restrictions prevent calls."""
    pass


class OpenRouterCatalogue:
    """In-memory cache and session state for OpenRouter models."""
    _cached_models: list[str] = []
    _cache_timestamp: float = 0.0
    _active_model: str | None = None
    _failed_in_run: set[str] = set()

    @classmethod
    def reset(cls) -> None:
        """Reset state (useful for tests)."""
        cls._cached_models = []
        cls._cache_timestamp = 0.0
        cls._active_model = None
        cls._failed_in_run.clear()


def is_openrouter_configured() -> bool:
    """Return True if OPENROUTER_API_KEY is present and non-empty."""
    return bool(os.environ.get("OPENROUTER_API_KEY", "").strip())


def sanitize_text(text: str, secret: str | None = None) -> str:
    """Remove sensitive API key strings from text."""
    if not text:
        return ""
    keys_to_redact = [
        secret,
        os.environ.get("OPENROUTER_API_KEY"),
        os.environ.get("GROQ_API_KEY"),
        os.environ.get("GEMINI_API_KEY"),
    ]
    sanitized = text
    for key in keys_to_redact:
        if key and len(key) >= 6:
            sanitized = sanitized.replace(key, "[REDACTED]")
    # Redact Authorization header format if present
    sanitized = re.sub(r'Bearer\s+[A-Za-z0-9_\-\.]{8,}', 'Bearer [REDACTED]', sanitized)
    return sanitized


def parse_json_safely(raw_text: str) -> dict[str, Any]:
    """Parse JSON from model response, handling markdown code fences and boundary trimming."""
    if not raw_text or not raw_text.strip():
        raise ValueError("Empty response text from model")

    cleaned = raw_text.strip()
    # Strip markdown code blocks ```json ... ```
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    # Locate outermost JSON object { ... }
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]

    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("Parsed JSON content is not an object")
    return data


def is_eligible_free_model(item: dict[str, Any]) -> bool:
    """Validate that a model catalogue entry is explicitly free, zero-priced, and suitable for text generation."""
    model_id = str(item.get("id", "")).strip()
    if not model_id:
        return False

    # 1. Must be identified as free variant or openrouter/free
    if not (model_id.endswith(":free") or model_id == "openrouter/free"):
        return False

    # 2. Strict Pricing check: prompt and completion cost must both be strictly 0
    pricing = item.get("pricing")
    if pricing and isinstance(pricing, dict):
        try:
            prompt_cost = float(pricing.get("prompt", 0) or 0)
            completion_cost = float(pricing.get("completion", 0) or 0)
            request_cost = float(pricing.get("request", 0) or 0)
            if prompt_cost > 0.0 or completion_cost > 0.0 or request_cost > 0.0:
                return False  # Exclude paid model
        except (ValueError, TypeError):
            return False

    # 3. Filter out non-text generation modalities (e.g. embeddings, vision-only, audio, text->image)
    arch = item.get("architecture")
    if arch and isinstance(arch, dict):
        modality = str(arch.get("modality", "")).lower()
        if modality:
            if "->" in modality:
                output_mod = modality.split("->")[-1]
                if "text" not in output_mod:
                    return False
            elif "text" not in modality:
                return False

    context_len = item.get("context_length")
    if context_len is not None and isinstance(context_len, (int, float)) and context_len < 2048:
        return False

    lower_id = model_id.lower()
    excluded_keywords = ["embed", "whisper", "tts", "diffusion", "vision-only", "guard", "moderation", "flux", "image"]
    if any(kw in lower_id for kw in excluded_keywords):
        return False

    return True


def discover_free_models(
    api_key: str,
    base_url: str,
    *,
    force_refresh: bool = False,
) -> list[str]:
    """Query OpenRouter models catalogue and return verified free model IDs.
    Caches catalogue for CACHE_TTL seconds.
    """
    now = time.time()
    if not force_refresh and OpenRouterCatalogue._cached_models and (now - OpenRouterCatalogue._cache_timestamp < CACHE_TTL):
        return list(OpenRouterCatalogue._cached_models)

    models_url = f"{base_url}/models"
    req = urllib.request.Request(
        models_url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://github.com/ayushdesign4/Monkey-baba",
            "X-Title": "Monkey-Baba",
            "User-Agent": "Monkey-Baba/1.0",
        },
        method="GET",
    )

    discovered: list[str] = []
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            raw_items = data.get("data", [])
            for item in raw_items:
                if is_eligible_free_model(item):
                    mid = str(item.get("id")).strip()
                    if mid not in discovered:
                        discovered.append(mid)

    except urllib.error.HTTPError as e:
        body = sanitize_text(e.read().decode("utf-8", errors="ignore"), api_key)
        if e.code in ACCOUNT_ERROR_CODES:
            raise OpenRouterConfigError(f"OpenRouter models discovery failed: HTTP {e.code} ({body[:150]})")
        print(f"[WARN] OpenRouter models endpoint returned HTTP {e.code}: {body[:120]}")
    except Exception as exc:
        print(f"[WARN] OpenRouter models discovery failed ({type(exc).__name__}: {sanitize_text(str(exc), api_key)})")

    # High capability models prioritization
    def priority_sort(mid: str) -> tuple[int, str]:
        l = mid.lower()
        if "70b" in l or "72b" in l:
            return (0, mid)
        if "24b" in l or "14b" in l:
            return (1, mid)
        if "8b" in l:
            return (2, mid)
        return (3, mid)

    discovered.sort(key=priority_sort)

    if discovered:
        OpenRouterCatalogue._cached_models = discovered
        OpenRouterCatalogue._cache_timestamp = now
        print(f"[OPENROUTER] Discovered {len(discovered)} eligible free models from catalogue.")
        return list(discovered)

    # If cached exists, return cached
    if OpenRouterCatalogue._cached_models:
        return list(OpenRouterCatalogue._cached_models)

    # Safe built-in fallback candidates (all known free tier variants)
    fallback_free = [
        "openrouter/free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "meta-llama/llama-3.1-8b-instruct:free",
        "mistralai/mistral-7b-instruct:free",
    ]
    OpenRouterCatalogue._cached_models = fallback_free
    OpenRouterCatalogue._cache_timestamp = now
    return list(fallback_free)


def build_candidate_models(
    preferred_model: str,
    discovered: list[str],
    exclude_failed: bool = True,
) -> list[str]:
    """Construct ordered list of candidate free models to try."""
    candidates: list[str] = []

    # 1. If an active model previously succeeded in this run, try it first
    if OpenRouterCatalogue._active_model and OpenRouterCatalogue._active_model not in OpenRouterCatalogue._failed_in_run:
        candidates.append(OpenRouterCatalogue._active_model)

    # 2. Preferred model (e.g. openrouter/free or user-configured)
    if preferred_model and preferred_model not in candidates:
        if not exclude_failed or preferred_model not in OpenRouterCatalogue._failed_in_run:
            candidates.append(preferred_model)

    # 3. Add discovered free models
    for m in discovered:
        if m not in candidates:
            if not exclude_failed or m not in OpenRouterCatalogue._failed_in_run:
                candidates.append(m)

    return candidates


def _execute_chat_completion(
    api_key: str,
    base_url: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    *,
    with_response_format: bool = True,
) -> str:
    """Send chat completions POST request to OpenRouter for a single model."""
    url = f"{base_url}/chat/completions"
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": 3072,
    }
    if with_response_format:
        payload["response_format"] = {"type": "json_object"}

    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data_bytes,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/ayushdesign4/Monkey-baba",
            "X-Title": "Monkey-Baba",
            "User-Agent": "Monkey-Baba/1.0",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        resp_json = json.loads(resp.read().decode("utf-8"))
        choices = resp_json.get("choices", [])
        if not choices:
            raise RuntimeError(f"OpenRouter returned empty choices array for model '{model}'")
        msg = choices[0].get("message", {})
        content = msg.get("content", "")
        if not content or not content.strip():
            raise RuntimeError(f"OpenRouter returned empty message content for model '{model}'")
        return str(content).strip()


def call_openrouter(
    preset: ChannelPreset,
    user_prompt: str,
    *,
    temperature: float = 0.85,
) -> dict[str, Any]:
    """Call OpenRouter with dynamic free-model discovery and failover.
    Returns validated JSON dictionary matching script generation contract.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured")

    base_url = os.environ.get("OPENROUTER_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    preferred_model = os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL).strip()
    system_prompt = preset.get("groq_system_hint", "You are an expert horror writer.")

    # 1. Discover eligible free models
    discovered = discover_free_models(api_key, base_url)
    candidates = build_candidate_models(preferred_model, discovered, exclude_failed=True)

    # If all eligible models were exhausted in run state, reset run failure memory and retry
    if not candidates:
        OpenRouterCatalogue._failed_in_run.clear()
        candidates = build_candidate_models(preferred_model, discovered, exclude_failed=False)

    if not candidates:
        raise RuntimeError("No eligible free models available on OpenRouter.")

    attempted_this_call: set[str] = set()
    last_error: Exception | None = None
    max_attempts = min(MAX_MODEL_ATTEMPTS, len(candidates))

    for attempt in range(max_attempts):
        # Pick the next candidate not yet attempted in this call
        model_to_try = None
        for cand in candidates:
            if cand not in attempted_this_call:
                model_to_try = cand
                break

        if not model_to_try:
            break

        attempted_this_call.add(model_to_try)
        print(f"[OPENROUTER] Attempt {attempt + 1}/{max_attempts} with model '{model_to_try}'...")

        try:
            # First try with response_format: json_object
            try:
                raw_content = _execute_chat_completion(
                    api_key, base_url, model_to_try, system_prompt, user_prompt, temperature, with_response_format=True
                )
            except urllib.error.HTTPError as he:
                # If HTTP 400 rejected response_format, retry without response_format
                err_text = he.read().decode("utf-8", errors="ignore")
                if he.code == 400 and ("response_format" in err_text.lower() or "schema" in err_text.lower()):
                    raw_content = _execute_chat_completion(
                        api_key, base_url, model_to_try, system_prompt, user_prompt, temperature, with_response_format=False
                    )
                else:
                    raise

            # Parse JSON
            data = parse_json_safely(raw_content)
            data["_provider"] = "openrouter"
            data["_model"] = model_to_try

            # Success: mark model active for subsequent calls
            OpenRouterCatalogue._active_model = model_to_try
            print(f"[OPENROUTER] Generation succeeded with model '{model_to_try}' (retained as active model).")
            return data

        except urllib.error.HTTPError as e:
            err_body = sanitize_text(e.read().decode("utf-8", errors="ignore"), api_key)
            last_error = RuntimeError(f"HTTP {e.code}: {err_body[:150]}")

            # 401/403/402: Account-level failure. Halt sweep immediately!
            if e.code in ACCOUNT_ERROR_CODES:
                print(f"[WARN] OpenRouter account configuration failure (HTTP {e.code}): {err_body[:150]}. Halting sweep.")
                OpenRouterCatalogue._active_model = None
                raise OpenRouterConfigError(f"OpenRouter account error HTTP {e.code}: {err_body[:150]}")

            # 404 (model not found) / 429 (rate limit) / 5xx (transient server error)
            category = "RateLimit" if e.code == 429 else ("NotFound" if e.code == 404 else f"Server{e.code}")
            print(f"[WARN] OpenRouter model '{model_to_try}' failed ({category}: HTTP {e.code}). Rotating to next free model...")
            OpenRouterCatalogue._failed_in_run.add(model_to_try)
            if OpenRouterCatalogue._active_model == model_to_try:
                OpenRouterCatalogue._active_model = None

            # Bounded backoff with jitter
            backoff = min(1.5, 0.2 * (2 ** attempt)) + random.uniform(0.05, 0.15)
            time.sleep(backoff)
            continue

        except (urllib.error.URLError, TimeoutError) as e:
            sanitized_msg = sanitize_text(str(e), api_key)
            print(f"[WARN] OpenRouter connection/timeout error on '{model_to_try}': {sanitized_msg}. Rotating to next free model...")
            last_error = RuntimeError(f"Connection error on {model_to_try}: {sanitized_msg}")
            OpenRouterCatalogue._failed_in_run.add(model_to_try)
            if OpenRouterCatalogue._active_model == model_to_try:
                OpenRouterCatalogue._active_model = None
            continue

        except (ValueError, json.JSONDecodeError) as e:
            sanitized_msg = sanitize_text(str(e), api_key)
            print(f"[WARN] OpenRouter model '{model_to_try}' returned invalid/malformed JSON: {sanitized_msg}. Rotating...")
            last_error = RuntimeError(f"Invalid JSON from {model_to_try}: {sanitized_msg}")
            OpenRouterCatalogue._failed_in_run.add(model_to_try)
            if OpenRouterCatalogue._active_model == model_to_try:
                OpenRouterCatalogue._active_model = None
            continue

        except Exception as e:
            sanitized_msg = sanitize_text(str(e), api_key)
            print(f"[WARN] OpenRouter unexpected error on model '{model_to_try}': {sanitized_msg}. Rotating...")
            last_error = e
            OpenRouterCatalogue._failed_in_run.add(model_to_try)
            if OpenRouterCatalogue._active_model == model_to_try:
                OpenRouterCatalogue._active_model = None
            continue

    raise RuntimeError(f"All attempted OpenRouter free models failed. Last error: {last_error}")
