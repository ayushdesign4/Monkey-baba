"""Comprehensive unit tests for OpenRouter dynamic free-model provider and 4-tier LLM fallback hierarchy."""
import json
from typing import Any
from unittest.mock import MagicMock, patch
import urllib.error

import pytest

from pipeline.channel_presets import get_preset
from pipeline.groq_script import generate_short_pack
from pipeline.openrouter_provider import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    OpenRouterCatalogue,
    OpenRouterConfigError,
    build_candidate_models,
    call_openrouter,
    discover_free_models,
    is_eligible_free_model,
    is_openrouter_configured,
    parse_json_safely,
    sanitize_text,
)

SAMPLE_VALID_NARRATION = (
    "Every night at three in the morning the grandfather clock struck thirteen times echoing down the dark corridor. "
    "Maya held her breath as the dusty floorboards began to groan under the weight of footsteps that had no owner. "
    "She crept toward the hallway clutching her brass flashlight with trembling hands. When the beam illuminated the "
    "floral wallpaper, the painted flowers appeared to wither and curl in real time. From deep inside the plaster, "
    "a raspy voice whispered her mother's maiden name, a secret buried for forty years. Maya took a step backward as "
    "the hallway temperature plummeted below freezing. In the cracked wall seam, a pale porcelain finger beckoned."
)

SAMPLE_VALID_PACK = {
    "youtube_title": "The Thirteen Chimes of Midnight #Shorts",
    "youtube_description": "A forbidden clock and a secret behind the wallpaper. #HorrorShorts #ScaryStories #Shorts",
    "full_narration": SAMPLE_VALID_NARRATION,
    "image_prompts": [
        "A towering antique grandfather clock striking in a dark abandoned Victorian hallway at 3 AM, 9:16 vertical",
        "Creepy wooden floorboards bending under invisible footsteps in the gloomy shadows",
        "A trembling young woman aiming a brass flashlight down a narrow corridor",
        "Victorian wallpaper with painted roses visibly wilting and decaying under the beam of light",
        "A cracked wall seam revealing dark voids within the ancient plaster",
        "A chilling porcelain hand reaching from behind broken wallpaper into the dark",
    ],
}


@pytest.fixture(autouse=True)
def reset_catalogue():
    """Reset OpenRouter catalogue state before each test."""
    OpenRouterCatalogue.reset()
    yield
    OpenRouterCatalogue.reset()


def make_mock_http_response(json_data: dict[str, Any], status: int = 200):
    """Helper to mock urllib.request.urlopen returning json_data."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(json_data).encode("utf-8")
    mock_resp.status = status
    mock_resp.__enter__.return_value = mock_resp
    return mock_resp


def make_mock_chat_completion_resp(content: str, model: str = "openrouter/free"):
    """Helper to construct OpenRouter chat completions response JSON."""
    return {
        "id": "gen-12345",
        "model": model,
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": "stop",
            }
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: Gemini succeeds — OpenRouter is not called
# ─────────────────────────────────────────────────────────────────────────────
def test_gemini_succeeds_openrouter_not_called(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gemini_mock_key_12345")
    monkeypatch.setenv("GROQ_API_KEY", "groq_mock_key_12345")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-mock-key-12345")

    preset = get_preset("horror")
    mock_gemini = MagicMock(return_value=dict(SAMPLE_VALID_PACK, _provider="gemini", _model="gemini-2.5-flash"))
    mock_groq = MagicMock()
    mock_openrouter = MagicMock()

    with patch("pipeline.groq_script.call_gemini", mock_gemini), \
         patch("pipeline.groq_script._call_groq", mock_groq), \
         patch("pipeline.groq_script.call_openrouter", mock_openrouter):

        pack = generate_short_pack(preset)
        assert pack["_provider"] == "gemini"
        assert mock_gemini.call_count >= 1
        assert mock_groq.call_count == 0
        assert mock_openrouter.call_count == 0


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: Gemini fails and Groq succeeds — OpenRouter is not called
# ─────────────────────────────────────────────────────────────────────────────
def test_gemini_fails_groq_succeeds_openrouter_not_called(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gemini_mock_key_12345")
    monkeypatch.setenv("GROQ_API_KEY", "groq_mock_key_12345")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-mock-key-12345")

    preset = get_preset("horror")
    mock_gemini = MagicMock(side_effect=RuntimeError("Gemini quota 429"))
    mock_groq = MagicMock(return_value=dict(SAMPLE_VALID_PACK, _provider="groq", _model="llama-3.1-8b-instant"))
    mock_openrouter = MagicMock()

    with patch("pipeline.groq_script.call_gemini", mock_gemini), \
         patch("pipeline.groq_script._call_groq", mock_groq), \
         patch("pipeline.groq_script.call_openrouter", mock_openrouter):

        pack = generate_short_pack(preset)
        assert pack["_provider"] == "groq"
        assert mock_gemini.call_count >= 1
        assert mock_groq.call_count >= 1
        assert mock_openrouter.call_count == 0


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: Gemini and Groq fail — OpenRouter is attempted
# ─────────────────────────────────────────────────────────────────────────────
def test_gemini_and_groq_fail_openrouter_attempted(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gemini_mock_key_12345")
    monkeypatch.setenv("GROQ_API_KEY", "groq_mock_key_12345")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-mock-key-12345")

    preset = get_preset("horror")
    mock_gemini = MagicMock(side_effect=RuntimeError("Gemini 503"))
    mock_groq = MagicMock(side_effect=RuntimeError("Groq 404 model_not_found"))
    mock_openrouter = MagicMock(return_value=dict(SAMPLE_VALID_PACK, _provider="openrouter", _model="openrouter/free"))

    with patch("pipeline.groq_script.call_gemini", mock_gemini), \
         patch("pipeline.groq_script._call_groq", mock_groq), \
         patch("pipeline.groq_script.call_openrouter", mock_openrouter):

        pack = generate_short_pack(preset)
        assert pack["_provider"] == "openrouter"
        assert mock_openrouter.call_count >= 1


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: openrouter/free succeeds — response accepted and model ID logged
# ─────────────────────────────────────────────────────────────────────────────
def test_openrouter_free_succeeds_logs_model_id(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-mock-key-12345")
    preset = get_preset("horror")

    catalogue_data = {
        "data": [
            {"id": "openrouter/free", "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "meta-llama/llama-3.3-70b-instruct:free", "pricing": {"prompt": "0", "completion": "0"}},
        ]
    }
    chat_resp_data = make_mock_chat_completion_resp(json.dumps(SAMPLE_VALID_PACK), model="openrouter/free")

    def mock_urlopen(req, timeout=None):
        url = req.full_url
        if "/models" in url:
            return make_mock_http_response(catalogue_data)
        elif "/chat/completions" in url:
            return make_mock_http_response(chat_resp_data)
        raise ValueError(f"Unexpected url: {url}")

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        res = call_openrouter(preset, "Write a horror story")
        assert res["_provider"] == "openrouter"
        assert res["_model"] == "openrouter/free"
        assert OpenRouterCatalogue._active_model == "openrouter/free"


# ─────────────────────────────────────────────────────────────────────────────
# Test 5: First free model fails and second free model succeeds
# ─────────────────────────────────────────────────────────────────────────────
def test_first_free_model_fails_second_succeeds(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-mock-key-12345")
    monkeypatch.setenv("OPENROUTER_MODEL", "openrouter/free")
    preset = get_preset("horror")

    catalogue_data = {
        "data": [
            {"id": "openrouter/free", "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "meta-llama/llama-3.3-70b-instruct:free", "pricing": {"prompt": "0", "completion": "0"}},
        ]
    }

    call_counts = {}

    def mock_urlopen(req, timeout=None):
        url = req.full_url
        if "/models" in url:
            return make_mock_http_response(catalogue_data)
        elif "/chat/completions" in url:
            payload = json.loads(req.data.decode("utf-8"))
            model = payload.get("model")
            call_counts[model] = call_counts.get(model, 0) + 1

            if model == "openrouter/free":
                # First model fails with transient HTTP 503
                fp = MagicMock()
                fp.read.return_value = b'{"error": "Provider temporarily unavailable"}'
                raise urllib.error.HTTPError(url, 503, "Service Unavailable", {}, fp)

            # Second model succeeds
            return make_mock_http_response(
                make_mock_chat_completion_resp(json.dumps(SAMPLE_VALID_PACK), model=model)
            )
        raise ValueError(f"Unexpected url: {url}")

    with patch("urllib.request.urlopen", side_effect=mock_urlopen), \
         patch("time.sleep"):  # Avoid test delays
        res = call_openrouter(preset, "Write a horror story")
        assert res["_provider"] == "openrouter"
        assert res["_model"] == "meta-llama/llama-3.3-70b-instruct:free"
        assert call_counts.get("openrouter/free") == 1
        assert call_counts.get("meta-llama/llama-3.3-70b-instruct:free") == 1
        assert OpenRouterCatalogue._active_model == "meta-llama/llama-3.3-70b-instruct:free"


# ─────────────────────────────────────────────────────────────────────────────
# Test 6: Multiple free models fail — next eligible model attempted without repeats
# ─────────────────────────────────────────────────────────────────────────────
def test_multiple_free_models_fail_without_repeating(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-mock-key-12345")
    monkeypatch.setenv("OPENROUTER_MODEL", "model-1:free")
    preset = get_preset("horror")

    catalogue_data = {
        "data": [
            {"id": "model-1:free", "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "model-2:free", "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "model-3:free", "pricing": {"prompt": "0", "completion": "0"}},
        ]
    }

    attempted_models = []

    def mock_urlopen(req, timeout=None):
        url = req.full_url
        if "/models" in url:
            return make_mock_http_response(catalogue_data)
        elif "/chat/completions" in url:
            payload = json.loads(req.data.decode("utf-8"))
            model = payload.get("model")
            attempted_models.append(model)
            if model in ("model-1:free", "model-2:free"):
                fp = MagicMock()
                fp.read.return_value = b'{"error": "rate limited"}'
                raise urllib.error.HTTPError(url, 429, "Rate Limited", {}, fp)
            # Third model succeeds
            return make_mock_http_response(
                make_mock_chat_completion_resp(json.dumps(SAMPLE_VALID_PACK), model=model)
            )
        raise ValueError(f"Unexpected url: {url}")

    with patch("urllib.request.urlopen", side_effect=mock_urlopen), patch("time.sleep"):
        res = call_openrouter(preset, "Write a horror story")
        assert res["_model"] == "model-3:free"
        assert attempted_models == ["model-1:free", "model-2:free", "model-3:free"]
        # Ensure no duplicates attempted
        assert len(attempted_models) == len(set(attempted_models))


# ─────────────────────────────────────────────────────────────────────────────
# Test 7: No free models available — existing local fallback executes
# ─────────────────────────────────────────────────────────────────────────────
def test_no_free_models_available_local_fallback_executes(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-mock-key-12345")

    preset = get_preset("horror")

    # Mock call_openrouter to fail
    with patch("pipeline.groq_script.call_openrouter", side_effect=RuntimeError("All free models exhausted")):
        pack = generate_short_pack(preset, topic_hint="an abandoned asylum")
        assert pack["_provider"] == "deterministic_local_fallback"
        assert len(pack["full_narration"].split()) >= 100
        assert len(pack["image_prompts"]) == 6


# ─────────────────────────────────────────────────────────────────────────────
# Test 8: Paid models are never attempted, even if listed by catalogue
# ─────────────────────────────────────────────────────────────────────────────
def test_paid_models_strictly_excluded(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-mock-key-12345")

    catalogue_data = {
        "data": [
            # Explicitly paid model
            {"id": "openai/gpt-4o", "pricing": {"prompt": "0.000005", "completion": "0.000015"}},
            # Paid model deceptively ending in free or non-zero price
            {"id": "sneaky/paid-model:free", "pricing": {"prompt": "0.000001", "completion": "0.0"}},
            # Non-text modality
            {"id": "black-forest-labs/flux-schnell:free", "architecture": {"modality": "text->image"}, "pricing": {"prompt": "0", "completion": "0"}},
            # Legitimate free model
            {"id": "meta-llama/llama-3.1-8b-instruct:free", "pricing": {"prompt": "0", "completion": "0"}},
        ]
    }

    # Verify is_eligible_free_model directly
    assert not is_eligible_free_model(catalogue_data["data"][0])
    assert not is_eligible_free_model(catalogue_data["data"][1])
    assert not is_eligible_free_model(catalogue_data["data"][2])
    assert is_eligible_free_model(catalogue_data["data"][3])

    def mock_urlopen(req, timeout=None):
        url = req.full_url
        if "/models" in url:
            return make_mock_http_response(catalogue_data)
        raise ValueError(f"Unexpected url: {url}")

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        models = discover_free_models("sk-or-test", DEFAULT_BASE_URL)
        assert "openai/gpt-4o" not in models
        assert "sneaky/paid-model:free" not in models
        assert "black-forest-labs/flux-schnell:free" not in models
        assert "meta-llama/llama-3.1-8b-instruct:free" in models


# ─────────────────────────────────────────────────────────────────────────────
# Test 9: HTTP 401/403 account errors do not trigger a pointless model sweep
# ─────────────────────────────────────────────────────────────────────────────
def test_account_errors_halt_sweep_immediately(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-invalid-key")
    preset = get_preset("horror")

    catalogue_data = {
        "data": [
            {"id": "model-1:free", "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "model-2:free", "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "model-3:free", "pricing": {"prompt": "0", "completion": "0"}},
        ]
    }

    chat_calls = 0

    def mock_urlopen(req, timeout=None):
        nonlocal chat_calls
        url = req.full_url
        if "/models" in url:
            return make_mock_http_response(catalogue_data)
        elif "/chat/completions" in url:
            chat_calls += 1
            fp = MagicMock()
            fp.read.return_value = b'{"error": {"message": "Invalid API Key", "code": 401}}'
            raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, fp)
        raise ValueError(f"Unexpected url: {url}")

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        with pytest.raises(OpenRouterConfigError):
            call_openrouter(preset, "Write a horror story")

        # Must have halted after 1 call; did NOT sweep all 3 models!
        assert chat_calls == 1


# ─────────────────────────────────────────────────────────────────────────────
# Test 10: Timeouts, 429, 5xx, malformed JSON, and empty responses handled safely
# ─────────────────────────────────────────────────────────────────────────────
def test_transient_and_malformed_errors_handled_safely(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-mock-key-12345")
    preset = get_preset("horror")

    catalogue_data = {
        "data": [
            {"id": "m-timeout:free", "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "m-empty:free", "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "m-malformed:free", "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "m-success:free", "pricing": {"prompt": "0", "completion": "0"}},
        ]
    }

    def mock_urlopen(req, timeout=None):
        url = req.full_url
        if "/models" in url:
            return make_mock_http_response(catalogue_data)
        elif "/chat/completions" in url:
            payload = json.loads(req.data.decode("utf-8"))
            model = payload.get("model")
            if model == "m-timeout:free":
                raise TimeoutError("Connection timed out")
            elif model == "m-empty:free":
                return make_mock_http_response(make_mock_chat_completion_resp("", model=model))
            elif model == "m-malformed:free":
                return make_mock_http_response(make_mock_chat_completion_resp("Not a json at all", model=model))
            elif model == "m-success:free":
                return make_mock_http_response(
                    make_mock_chat_completion_resp(json.dumps(SAMPLE_VALID_PACK), model=model)
                )
        raise ValueError(f"Unexpected url: {url}")

    with patch("urllib.request.urlopen", side_effect=mock_urlopen), patch("time.sleep"):
        res = call_openrouter(preset, "Write a horror story")
        assert res["_model"] == "m-success:free"
        assert res["_provider"] == "openrouter"


# ─────────────────────────────────────────────────────────────────────────────
# Test 11: Model catalogue caching and refresh work
# ─────────────────────────────────────────────────────────────────────────────
def test_catalogue_caching_and_refresh(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-mock-key-12345")

    catalogue_data_1 = {
        "data": [{"id": "meta-llama/llama-3.1-8b-instruct:free", "pricing": {"prompt": "0", "completion": "0"}}]
    }
    catalogue_data_2 = {
        "data": [{"id": "meta-llama/llama-3.3-70b-instruct:free", "pricing": {"prompt": "0", "completion": "0"}}]
    }

    get_models_calls = 0

    def mock_urlopen(req, timeout=None):
        nonlocal get_models_calls
        if "/models" in req.full_url:
            get_models_calls += 1
            data = catalogue_data_1 if get_models_calls == 1 else catalogue_data_2
            return make_mock_http_response(data)
        raise ValueError("Unexpected url")

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        # 1st call: queries models endpoint
        models_1 = discover_free_models("key", DEFAULT_BASE_URL)
        assert models_1 == ["meta-llama/llama-3.1-8b-instruct:free"]
        assert get_models_calls == 1

        # 2nd call: within TTL, returns cached without network request
        models_cached = discover_free_models("key", DEFAULT_BASE_URL)
        assert models_cached == ["meta-llama/llama-3.1-8b-instruct:free"]
        assert get_models_calls == 1

        # 3rd call with force_refresh: makes new HTTP request
        models_refreshed = discover_free_models("key", DEFAULT_BASE_URL, force_refresh=True)
        assert models_refreshed == ["meta-llama/llama-3.3-70b-instruct:free"]
        assert get_models_calls == 2


# ─────────────────────────────────────────────────────────────────────────────
# Test 12: Missing OpenRouter credentials do not break the pipeline
# ─────────────────────────────────────────────────────────────────────────────
def test_missing_openrouter_credentials_handled_gracefully(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    assert not is_openrouter_configured()
    preset = get_preset("horror")
    pack = generate_short_pack(preset)
    assert pack["_provider"] == "deterministic_local_fallback"
    assert len(pack["full_narration"].split()) >= 100


# ─────────────────────────────────────────────────────────────────────────────
# Test 13: Markdown fenced JSON and credential sanitization
# ─────────────────────────────────────────────────────────────────────────────
def test_fenced_json_parsing_and_credential_sanitization():
    # Verify markdown code fences ```json ... ``` are parsed cleanly
    fenced = f"```json\n{json.dumps(SAMPLE_VALID_PACK)}\n```"
    parsed = parse_json_safely(fenced)
    assert parsed["youtube_title"] == SAMPLE_VALID_PACK["youtube_title"]

    # Verify sensitive token sanitization
    secret = "sk-or-v1-secret1234567890abcdef"
    text_with_secret = f"Error calling endpoint with key {secret} and Bearer {secret}"
    sanitized = sanitize_text(text_with_secret, secret=secret)
    assert secret not in sanitized
    assert "[REDACTED]" in sanitized


# ─────────────────────────────────────────────────────────────────────────────
# Test 14: Safe dry-run integration test — OpenRouter generates script in pipeline
# ─────────────────────────────────────────────────────────────────────────────
def test_openrouter_dry_run_pipeline_integration(tmp_path, monkeypatch):
    """Confirm OpenRouter discovers free models and generates valid script/scenes
    when Gemini and Groq are disabled, running through full dry-run orchestrator safely.
    """
    from scripts.run_short import run_pipeline

    monkeypatch.setattr("pipeline.story_history.DATA_DIR", tmp_path)
    monkeypatch.setattr("pipeline.story_history.TOPIC_HISTORY_PATH", tmp_path / "topic_history.json")
    monkeypatch.setattr("pipeline.story_history.UPLOAD_HISTORY_PATH", tmp_path / "upload_history.json")
    monkeypatch.setattr("pipeline.story_history.RUN_STATE_PATH", tmp_path / "run_state.json")

    # Disable Gemini & Groq
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    # Enable OpenRouter
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-mock-integration-key-12345")
    monkeypatch.setenv("OPENROUTER_MODEL", "openrouter/free")

    catalogue_data = {
        "data": [
            {"id": "openrouter/free", "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "meta-llama/llama-3.3-70b-instruct:free", "pricing": {"prompt": "0", "completion": "0"}},
        ]
    }
    chat_resp_data = make_mock_chat_completion_resp(json.dumps(SAMPLE_VALID_PACK), model="openrouter/free")

    def mock_urlopen(req, timeout=None):
        url = req.full_url
        if "/models" in url:
            return make_mock_http_response(catalogue_data)
        elif "/chat/completions" in url:
            return make_mock_http_response(chat_resp_data)
        raise ValueError(f"Unexpected url: {url}")

    mock_upload = MagicMock()
    mock_email = MagicMock()

    with patch("urllib.request.urlopen", side_effect=mock_urlopen), \
         patch("pipeline.youtube_upload.upload_short", mock_upload), \
         patch("scripts.run_short.send_upload_success_email", mock_email), \
         patch("scripts.run_short.synthesize_full", return_value=(45.0, [{"offset_ms": 0, "duration_ms": 45000, "text": "sentence"}])), \
         patch("scripts.run_short.build_srt"), \
         patch("scripts.run_short.render_vertical_short"), \
         patch("scripts.run_short.validate_short_quality") as mock_qg, \
         patch("scripts.run_short.save_scene_image", return_value=("ok", "pollinations")):

        mock_qg.return_value = MagicMock(passed=True, duration=45.0, width=1080, height=1920, errors=[])

        result = run_pipeline(
            channel_id="horror",
            topic_override="a clock that strikes thirteen times",
            dry_run=True,
            upload_enabled=False,
            run_id="test_openrouter_integration",
            allow_procedural_fallback=False,
        )

        assert result["status"] == "success"
        assert result["dry_run"] is True
        assert result["video_id"].startswith("sim_")
        assert mock_upload.call_count == 0
        assert mock_email.call_count == 0


# ─────────────────────────────────────────────────────────────────────────────
# Test 15: OpenRouter failure falls through to local fallback in pipeline
# ─────────────────────────────────────────────────────────────────────────────
def test_openrouter_failure_falls_through_to_local_fallback_in_pipeline(tmp_path, monkeypatch):
    """Confirm that when OpenRouter fails, the pipeline cleanly falls back to deterministic local fallback."""
    from scripts.run_short import run_pipeline

    monkeypatch.setattr("pipeline.story_history.DATA_DIR", tmp_path)
    monkeypatch.setattr("pipeline.story_history.TOPIC_HISTORY_PATH", tmp_path / "topic_history.json")
    monkeypatch.setattr("pipeline.story_history.UPLOAD_HISTORY_PATH", tmp_path / "upload_history.json")
    monkeypatch.setattr("pipeline.story_history.RUN_STATE_PATH", tmp_path / "run_state.json")

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-mock-failing-key")

    mock_upload = MagicMock()
    mock_email = MagicMock()

    with patch("pipeline.openrouter_provider.call_openrouter", side_effect=RuntimeError("All free models failed")), \
         patch("pipeline.youtube_upload.upload_short", mock_upload), \
         patch("scripts.run_short.send_upload_success_email", mock_email), \
         patch("scripts.run_short.synthesize_full", return_value=(45.0, [{"offset_ms": 0, "duration_ms": 45000, "text": "sentence"}])), \
         patch("scripts.run_short.build_srt"), \
         patch("scripts.run_short.render_vertical_short"), \
         patch("scripts.run_short.validate_short_quality") as mock_qg, \
         patch("scripts.run_short.save_scene_image", return_value=("ok", "pollinations")):

        mock_qg.return_value = MagicMock(passed=True, duration=45.0, width=1080, height=1920, errors=[])

        result = run_pipeline(
            channel_id="horror",
            topic_override="an antique mirror that blinks late",
            dry_run=True,
            upload_enabled=False,
            run_id="test_openrouter_fallback",
            allow_procedural_fallback=False,
        )

        assert result["status"] == "success"
        assert result["dry_run"] is True
        assert mock_upload.call_count == 0

