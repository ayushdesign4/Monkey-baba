import base64
import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from PIL import Image

from pipeline.images import (
    DEFAULT_POLLINATIONS_MODEL,
    POLLINATIONS_GENERATIONS_URL,
    VisualQualityPolicyError,
    _pollinations_gpt_image_generate,
    _validate_image_file,
    adapt_to_9_16,
    full_visual_prompt,
    save_scene_image,
    validate_visual_quality_policy,
)


def _make_dummy_image_bytes(w: int = 1024, h: int = 1024, color: tuple = (30, 20, 40)) -> bytes:
    im = Image.new("RGB", (w, h), color=color)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def test_pollinations_endpoint_payload_and_auth_mapping():
    """Verify Pollinations uses POST https://gen.pollinations.ai/v1/images/generations,
    model openai/gpt-image-1-mini, Bearer auth, and size 1024x1024.
    """
    dummy_png = _make_dummy_image_bytes(1024, 1024)
    b64_content = base64.b64encode(dummy_png).decode("utf-8")

    captured_req = {}

    def mock_post(url, json=None, headers=None, **kwargs):
        captured_req["url"] = url
        captured_req["json"] = json
        captured_req["headers"] = headers
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "created": 1720000000,
            "data": [{"b64_json": b64_content}],
            "usage": {"input_tokens": 39, "output_tokens": 1056, "total_tokens": 1095},
        }
        return mock_resp

    with patch.object(httpx.Client, "post", side_effect=mock_post):
        adapted_bytes, model_used, usage = _pollinations_gpt_image_generate(
            "An eerie foggy mirror",
            api_key="sk_test_secret_key_abc123",
            width=720,
            height=1280,
            model=DEFAULT_POLLINATIONS_MODEL,
        )

        assert captured_req["url"] == POLLINATIONS_GENERATIONS_URL
        assert captured_req["headers"]["Authorization"] == "Bearer sk_test_secret_key_abc123"
        assert captured_req["headers"]["Content-Type"] == "application/json"

        assert captured_req["json"]["model"] == "openai/gpt-image-1-mini"
        assert captured_req["json"]["prompt"] == "An eerie foggy mirror"
        assert captured_req["json"]["size"] == "1024x1024"
        assert captured_req["json"]["n"] == 1
        assert captured_req["json"]["response_format"] == "b64_json"

        assert model_used == "openai/gpt-image-1-mini"
        assert usage["input_tokens"] == 39
        assert usage["output_tokens"] == 1056
        assert usage["total_tokens"] == 1095


def test_pollinations_successful_download_and_validation(tmp_path):
    """Verify that returned image (b64 or url) is decoded, adapted to 9:16,
    saved properly, and passes PIL verification.
    """
    dummy_png = _make_dummy_image_bytes(1024, 1024)
    b64_content = base64.b64encode(dummy_png).decode("utf-8")

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "created": 1720000000,
        "data": [{"b64_json": b64_content}],
        "usage": {"total_tokens": 1095},
    }

    with patch.object(httpx.Client, "post", return_value=mock_resp):
        out_img = tmp_path / "scene_01.png"
        status, detail = save_scene_image(
            1,
            "A haunted cabin",
            out_img,
            width=720,
            height=1280,
        )
        # Without key set, it would skip; let's test with key
    
    with patch.object(httpx.Client, "post", return_value=mock_resp), \
         patch.dict("os.environ", {"POLLINATIONS_API_KEY": "sk_test_dummy"}):
        out_img = tmp_path / "scene_02.png"
        status, detail = save_scene_image(
            2,
            "A haunted cabin in the snow",
            out_img,
            width=720,
            height=1280,
        )
        assert status == "ok"
        assert "pollinations" in detail
        assert out_img.is_file()
        _validate_image_file(out_img)

        with Image.open(out_img) as im:
            assert im.size == (720, 1280)


def test_pollinations_permanent_errors_not_retried():
    """Verify HTTP 401, 402, 403, and 400 are raised immediately and NOT repeatedly retried."""
    for code, expected_text in [
        (401, "unauthorized"),
        (402, "payment required"),
        (403, "access denied"),
        (400, "bad request"),
    ]:
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = code
        mock_resp.text = f"Error {code}"

        call_count = 0

        def mock_post(url, **kwargs):
            nonlocal call_count
            call_count += 1
            return mock_resp

        with patch.object(httpx.Client, "post", side_effect=mock_post):
            with pytest.raises(RuntimeError) as exc_info:
                _pollinations_gpt_image_generate(
                    "Test prompt",
                    api_key="sk_invalid_test_key",
                    max_retries=3,
                )

            assert expected_text in str(exc_info.value).lower()
            # Must NOT retry permanent failure
            assert call_count == 1, f"HTTP {code} was retried unexpectedly!"


def test_pollinations_transient_rate_limit_and_server_error_retries():
    """Verify HTTP 429 and 503 retry with bounded backoff and succeed on subsequent try."""
    attempts = 0

    def mock_post_transient(url, **kwargs):
        nonlocal attempts
        attempts += 1
        mock_resp = MagicMock(spec=httpx.Response)
        if attempts == 1:
            mock_resp.status_code = 429
            mock_resp.headers = {"Retry-After": "0"}
            return mock_resp
        
        # Second attempt succeeds
        mock_resp.status_code = 200
        dummy_png = _make_dummy_image_bytes(1024, 1024)
        b64_content = base64.b64encode(dummy_png).decode("utf-8")
        mock_resp.json.return_value = {
            "created": 1720000000,
            "data": [{"b64_json": b64_content}],
            "usage": {"total_tokens": 1095},
        }
        return mock_resp

    with patch.object(httpx.Client, "post", side_effect=mock_post_transient), \
         patch("time.sleep"):  # Avoid actual sleeping in tests
        raw_bytes, model_used, _ = _pollinations_gpt_image_generate(
            "Test retry prompt",
            api_key="sk_valid_key",
            max_retries=3,
        )
        assert attempts == 2
        assert model_used == "openai/gpt-image-1-mini"
        assert len(raw_bytes) > 1000


def test_safe_reuse_of_already_generated_valid_images(tmp_path):
    """Verify that if a valid scene image already exists at out_path,
    save_scene_image safely reuses it without making any external API request.
    """
    existing_img = tmp_path / "scene_01.png"
    existing_bytes = _make_dummy_image_bytes(720, 1280)
    existing_img.write_bytes(existing_bytes)

    with patch.object(httpx.Client, "post") as mock_post:
        status, detail = save_scene_image(
            1,
            "A dark hallway",
            existing_img,
            width=720,
            height=1280,
        )

        assert status == "ok"
        assert detail == "cached_existing"
        # Zero HTTP requests should be dispatched!
        assert mock_post.call_count == 0


def test_scene_to_image_prompt_consistency():
    """Verify scene prompts append atmospheric horror lighting and 9:16 vertical cues."""
    base_scene = "A cloaked traveler sees glowing yellow eyes behind an old tree"
    prompt = full_visual_prompt(base_scene)

    assert base_scene in prompt
    assert "9:16 vertical" in prompt
    assert "horror" in prompt
    assert "cinematic" in prompt


def test_adapt_to_9_16_preserves_aspect_ratio_without_distortion():
    """Verify adapt_to_9_16 crops 1024x1024 square to 9:16 without stretching."""
    square_img = Image.new("RGB", (1024, 1024), color=(50, 60, 70))
    adapted = adapt_to_9_16(square_img, target_width=1080, target_height=1920)

    assert adapted.size == (1080, 1920)

    # Test already 9:16 image
    vert_img = Image.new("RGB", (720, 1280), color=(50, 60, 70))
    adapted_vert = adapt_to_9_16(vert_img, target_width=1080, target_height=1920)
    assert adapted_vert.size == (1080, 1920)


def test_no_silent_placeholder_fallback_during_production():
    """Verify that if only procedural fallback images are produced,
    validate_visual_quality_policy blocks production upload unless explicitly allowed.
    """
    manifest_placeholder = {
        1: "pollinations (openai/gpt-image-1-mini)",
        2: "procedural_pil_fallback",
        3: "pollinations (openai/gpt-image-1-mini)",
    }

    with pytest.raises(VisualQualityPolicyError) as exc_info:
        validate_visual_quality_policy(manifest_placeholder, allow_procedural=False)

    assert "Visual Quality Policy Violation" in str(exc_info.value)
    assert "procedural placeholders" in str(exc_info.value).lower()

    # When explicitly allowed, passes
    validate_visual_quality_policy(manifest_placeholder, allow_procedural=True)
