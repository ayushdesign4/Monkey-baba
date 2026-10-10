import pytest
from unittest.mock import MagicMock, patch
import httpx

from pipeline.images import _pollinations_generate
from pipeline.groq_script import _call_groq, generate_short_pack
from pipeline.channel_presets import get_preset


def test_pollinations_http_402_treated_as_failure():
    # Mock httpx.Client to return HTTP 402 Payment Required
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 402
    mock_resp.text = "Payment Required"

    with patch.object(httpx.Client, "get", return_value=mock_resp):
        with pytest.raises(RuntimeError) as exc_info:
            _pollinations_generate("A dark foggy forest", width=720, height=1280)

        assert "402" in str(exc_info.value)
        assert "Payment Required" in str(exc_info.value)


def test_groq_404_model_fallback(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_mock_key_12345")
    preset = get_preset("horror")

    # Simulate Groq client: first model returns 404 model_not_found, second model succeeds
    call_count = 0
    attempted_models = []

    def mock_create(model, messages, **kwargs):
        nonlocal call_count
        call_count += 1
        attempted_models.append(model)
        if model == "llama-3.3-70b-versatile" or call_count == 1:
            raise RuntimeError("Error code: 404 - {'error': {'message': 'The model `llama-3.3-70b-versatile` does not exist', 'code': 'model_not_found'}}")
        
        # Second model succeeds
        mock_choice = MagicMock()
        mock_choice.message.content = '{"youtube_title": "Test Title #Shorts", "youtube_description": "Test Desc", "full_narration": "A long test narration of over one hundred words.", "image_prompts": ["p1", "p2", "p3", "p4", "p5", "p6"]}'
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        return mock_resp

    with patch("pipeline.groq_script.Groq") as mock_groq_cls:
        mock_instance = MagicMock()
        mock_instance.chat.completions.create.side_effect = mock_create
        mock_groq_cls.return_value = mock_instance

        # Set preferred model to failing model
        monkeypatch.setenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        res = _call_groq(preset, "Write a horror story")

        assert res["_provider"] == "groq"
        assert len(attempted_models) >= 2
        # Proves it tried the first model, caught 404, and tried candidate fallback
        assert attempted_models[0] == "llama-3.3-70b-versatile"
        assert attempted_models[1] in ["llama-3.1-8b-instant", "llama3-70b-8192", "llama3-8b-8192"]


def test_groq_failure_tags_local_fallback(monkeypatch):
    # Proves local emergency fallback is explicitly tagged and never claims Groq succeeded
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    preset = get_preset("horror")

    pack = generate_short_pack(preset, topic_hint="an abandoned asylum")
    assert pack["_provider"] == "deterministic_local_fallback"
    assert pack.get("_provider") != "groq"
