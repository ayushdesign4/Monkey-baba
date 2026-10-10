"""Multi-provider image generation: Pollinations (openai/gpt-image-1-mini) -> Hugging Face -> DeAPI -> Procedural PIL fallback.

All outputs are vertical 9:16 (default 720x1280 or 1080x1920) formatted for YouTube Shorts.
"""
from __future__ import annotations

import base64
import io
import math
import os
import random
import time
import urllib.parse
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageDraw, ImageFilter

POLLINATIONS_GENERATIONS_URL = "https://gen.pollinations.ai/v1/images/generations"
DEFAULT_POLLINATIONS_MODEL = os.environ.get("POLLINATIONS_MODEL", "openai/gpt-image-1-mini")

DEAPI_SUBMIT_URL = "https://api.deapi.ai/api/v1/client/txt2img"
DEAPI_POLL_URL = "https://api.deapi.ai/api/v1/client/request-status"

DEFAULT_HF_MODEL = os.environ.get("HF_IMAGE_MODEL", "black-forest-labs/FLUX.1-schnell")

HF_CANDIDATE_MODELS = [
    os.environ.get("HF_IMAGE_MODEL", "black-forest-labs/FLUX.1-schnell"),
    "black-forest-labs/FLUX.1-schnell",
    "stabilityai/stable-diffusion-xl-base-1.0",
    "runwayml/stable-diffusion-v1-5",
]

STYLE_SUFFIX = (
    ", dark eerie cinematic horror photography, atmospheric volumetric fog, haunting lighting, "
    "dramatic shadows, photorealistic, 8k, sharp focus, sinister mood, centered composition, "
    "9:16 vertical composition, professional cinematic framing, no text, no captions, no watermark, no logos"
)

DEFAULT_NEGATIVE = (
    "bright cheerful sunny daylight, smiling faces, cartoon, anime, illustration, "
    "blurry, low quality, watermark, logo, text, title, signature, ugly, distorted anatomy, "
    "graphic gore, extreme blood, mutilation"
)


class VisualQualityPolicyError(RuntimeError):
    """Raised when visual assets fail the visual quality policy (e.g. only procedural placeholders generated)."""
    pass


def model_candidates() -> list[str]:
    """Return ordered list of supported visual models for logging and diagnosis."""
    return [DEFAULT_POLLINATIONS_MODEL] + [m for m in HF_CANDIDATE_MODELS if m]


def full_visual_prompt(
    scene: str,
    style_suffix: str | None = None,
    *,
    story_context: str | None = None,
) -> str:
    """Combine the scene description with a channel-specific style suffix and context."""
    base = scene.strip()
    if story_context and story_context.strip() and story_context.strip().lower() not in base.lower():
        base = f"{story_context.strip()}: {base}"
    suffix = style_suffix if style_suffix is not None else STYLE_SUFFIX
    return f"{base}{suffix}"


def adapt_to_9_16(
    im: Image.Image,
    target_width: int = 1080,
    target_height: int = 1920,
) -> Image.Image:
    """Crop and resize an image (e.g. 1024x1024 square) into exact 9:16 composition
    without geometric stretching or subject distortion.
    """
    w, h = im.size
    target_ratio = target_width / target_height  # 9/16 = 0.5625
    current_ratio = w / h

    # If already matches target aspect ratio within 1% tolerance
    if abs(current_ratio - target_ratio) < 0.01:
        return im.resize((target_width, target_height), Image.Resampling.LANCZOS)

    if current_ratio > target_ratio:
        # Image is wider than 9:16 (e.g. 1:1 square or 16:9 landscape)
        # Take center crop of width = int(h * target_ratio), full height
        crop_w = int(h * target_ratio)
        left = max(0, (w - crop_w) // 2)
        right = left + crop_w
        cropped = im.crop((left, 0, right, h))
    else:
        # Image is taller than 9:16
        # Take crop of height = int(w / target_ratio), full width
        crop_h = int(w / target_ratio)
        # Slightly bias towards top-center (40/60) to avoid cutting off faces/focal subjects
        top = max(0, int((h - crop_h) * 0.4))
        bottom = top + crop_h
        cropped = im.crop((0, top, w, bottom))

    return cropped.resize((target_width, target_height), Image.Resampling.LANCZOS)


def _pollinations_gpt_image_generate(
    prompt: str,
    *,
    api_key: str,
    width: int = 720,
    height: int = 1280,
    model: str = DEFAULT_POLLINATIONS_MODEL,
    max_retries: int = 3,
) -> tuple[bytes, str, dict[str, Any]]:
    """Generate image via Pollinations.ai authenticated OpenAI-compatible API
    (POST https://gen.pollinations.ai/v1/images/generations) using openai/gpt-image-1-mini.

    Returns: (adapted_png_bytes, model_name, usage_dict)
    """
    if not api_key:
        raise ValueError("POLLINATIONS_API_KEY is required for authenticated image generation")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "model": model,
        "prompt": prompt,
        "size": "1024x1024",
        "n": 1,
        "response_format": "b64_json",
    }

    last_error: Exception | None = None
    with httpx.Client(timeout=45.0) as client:
        for attempt in range(max_retries):
            try:
                resp = client.post(POLLINATIONS_GENERATIONS_URL, json=payload, headers=headers)

                # Permanent non-retryable errors
                if resp.status_code == 401:
                    raise RuntimeError(
                        "Pollinations API unauthorized (HTTP 401). Check POLLINATIONS_API_KEY at https://enter.pollinations.ai/keys"
                    )
                if resp.status_code == 402:
                    raise RuntimeError(
                        "Pollinations payment required / quota exhausted (HTTP 402). Check credits at https://enter.pollinations.ai/pollen"
                    )
                if resp.status_code == 403:
                    raise RuntimeError(
                        f"Pollinations access denied (HTTP 403). Permissions or model not allowed for key: {resp.text[:120]}"
                    )
                if resp.status_code == 400:
                    raise RuntimeError(f"Pollinations bad request (HTTP 400): {resp.text[:180]}")

                # Rate limiting with bounded backoff
                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    wait_time = float(retry_after) if retry_after and retry_after.isdigit() else 2.0 ** (attempt + 1)
                    if attempt < max_retries - 1:
                        time.sleep(min(wait_time, 15.0))
                        continue
                    raise RuntimeError(f"Pollinations rate limit exceeded (HTTP 429) after {max_retries} attempts")

                # Server errors: retry with backoff
                if resp.status_code in (500, 502, 503, 504):
                    if attempt < max_retries - 1:
                        time.sleep(2.0 ** (attempt + 1))
                        continue
                    raise RuntimeError(
                        f"Pollinations server error (HTTP {resp.status_code}) after {max_retries} attempts: {resp.text[:120]}"
                    )

                resp.raise_for_status()
                data = resp.json()

                items = data.get("data", [])
                if not items:
                    raise RuntimeError(f"Pollinations returned empty data array: {data}")

                item = items[0]
                raw_bytes: bytes | None = None
                if item.get("b64_json"):
                    raw_bytes = base64.b64decode(item["b64_json"])
                elif item.get("url"):
                    img_resp = client.get(item["url"], timeout=30.0)
                    img_resp.raise_for_status()
                    raw_bytes = img_resp.content

                if not raw_bytes or len(raw_bytes) < 1000:
                    raise RuntimeError(
                        f"Pollinations returned invalid or empty image content ({len(raw_bytes) if raw_bytes else 0} bytes)"
                    )

                usage = data.get("usage", {})
                if usage:
                    in_tok = usage.get("input_tokens")
                    out_tok = usage.get("output_tokens")
                    tot_tok = usage.get("total_tokens")
                    print(f"   [Pollinations Usage] Tokens: input={in_tok}, output={out_tok}, total={tot_tok}")

                # Adapt square 1024x1024 output to requested 9:16 composition
                with Image.open(io.BytesIO(raw_bytes)) as pil_img:
                    pil_img = pil_img.convert("RGB")
                    adapted = adapt_to_9_16(pil_img, target_width=width, target_height=height)
                    buf = io.BytesIO()
                    adapted.save(buf, format="PNG")
                    return buf.getvalue(), model, usage

            except (httpx.TimeoutException, httpx.NetworkError) as net_err:
                last_error = net_err
                if attempt < max_retries - 1:
                    time.sleep(2.0 ** (attempt + 1))
                    continue
                raise RuntimeError(f"Pollinations network error after {max_retries} attempts: {net_err}") from net_err

    if last_error:
        raise last_error
    raise RuntimeError("Pollinations generation failed unexpectedly")


def _deapi_generate(
    prompt: str,
    *,
    api_key: str,
    width: int,
    height: int,
    model: str,
    max_polls: int = 30,
    poll_interval: float = 3.0,
) -> bytes:
    """Submit image job, poll until done, download result."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payload = {
        "prompt": prompt,
        "model": model,
        "width": width,
        "height": height,
        "steps": 4,
        "seed": random.randint(1, 999999),
    }

    with httpx.Client(timeout=60.0) as client:
        for submit_try in range(5):
            resp = client.post(DEAPI_SUBMIT_URL, json=payload, headers=headers)
            if resp.status_code == 429:
                wait = 15 * (submit_try + 1)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            break
        else:
            raise RuntimeError("DeAPI: 429 on submit after 5 retries")

        data = resp.json()
        request_id = data.get("data", {}).get("request_id")
        if not request_id:
            raise RuntimeError(f"No request_id in DeAPI response: {data}")

        poll_headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        }

        for attempt in range(1, max_polls + 1):
            time.sleep(poll_interval)
            poll_resp = client.get(
                f"{DEAPI_POLL_URL}/{request_id}",
                headers=poll_headers,
                timeout=30.0,
            )
            poll_resp.raise_for_status()
            poll_data = poll_resp.json()
            status = poll_data.get("data", {}).get("status", "")

            if status in ("completed", "success", "done"):
                image_url = poll_data["data"].get("result_url")
                if not image_url:
                    raise RuntimeError(f"Completed but no result_url: {poll_data}")
                img_resp = client.get(image_url, timeout=60.0)
                img_resp.raise_for_status()
                return img_resp.content

            if status in ("failed", "error"):
                raise RuntimeError(f"DeAPI image failed: {poll_data}")

        raise RuntimeError(f"DeAPI timed out after {max_polls} polls for {request_id}")


def _hf_generate(
    prompt: str,
    *,
    api_key: str,
    width: int,
    height: int,
    model: str | None = None,
) -> tuple[bytes, str]:
    """Generate image via Hugging Face Serverless Router API."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "inputs": prompt,
        "parameters": {
            "width": width,
            "height": height,
        },
    }

    models_to_try = [model] if model else HF_CANDIDATE_MODELS
    seen: set[str] = set()
    unique_models: list[str] = []
    for m in models_to_try:
        if m and m not in seen:
            seen.add(m)
            unique_models.append(m)

    last_err = ""
    with httpx.Client(timeout=45.0) as client:
        for m_name in unique_models:
            url = f"https://router.huggingface.co/hf-inference/models/{m_name}"
            try:
                resp = client.post(url, json=payload, headers=headers)
                if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image/"):
                    return resp.content, m_name
                if resp.status_code == 503 and "estimated_time" in resp.text:
                    time.sleep(8.0)
                    resp = client.post(url, json=payload, headers=headers)
                    if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image/"):
                        return resp.content, m_name
                last_err = f"Model '{m_name}' HTTP {resp.status_code}: {resp.text[:100]}"
            except Exception as e:
                safe_err = str(e).replace(api_key, "[REDACTED]")
                last_err = f"Model '{m_name}' error: {safe_err}"

    raise RuntimeError(f"Hugging Face inference failed across models. Last error: {last_err}")


def _pollinations_generate(
    prompt: str,
    *,
    width: int,
    height: int,
) -> bytes:
    """Legacy Pollinations generator. Maintained for backwards compatibility."""
    safe_prompt = urllib.parse.quote(prompt[:400])
    seed = random.randint(1, 999999)
    url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width={width}&height={height}&seed={seed}&nologo=true&enhance=false"

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        resp = client.get(url)
        if resp.status_code == 402:
            raise RuntimeError("Pollinations returned HTTP 402 Payment Required (free quota exhausted/payment required)")
        if resp.status_code != 200:
            raise RuntimeError(f"Pollinations returned HTTP {resp.status_code}")
        if not resp.headers.get("content-type", "").startswith("image/") and len(resp.content) < 1000:
            raise RuntimeError(f"Pollinations returned invalid content type: {resp.headers.get('content-type')}")
        return resp.content


def validate_visual_quality_policy(
    scene_manifest: dict[int, str],
    *,
    allow_procedural: bool = False,
) -> None:
    """Enforce visual quality policy. Blocks public upload if AI visuals failed
    and only procedural placeholders were generated, unless explicitly permitted.
    """
    procedural_scenes = [
        idx for idx, provider in scene_manifest.items() if "procedural" in provider.lower()
    ]
    if procedural_scenes and not allow_procedural:
        raise VisualQualityPolicyError(
            f"Visual Quality Policy Violation: Procedural placeholders were used for scenes {procedural_scenes} "
            "because AI visual generation failed. Public upload is blocked to prevent uploading placeholder videos. "
            "To permit procedural visual placeholders, set ALLOW_PROCEDURAL_FALLBACK=true or pass --allow-procedural-fallback."
        )


def _procedural_fallback_generate(
    prompt: str,
    *,
    width: int,
    height: int,
    scene_index: int = 1,
) -> bytes:
    """Deterministic local PIL fallback generator for atmospheric 9:16 horror visuals.
    Ensures non-black, non-blank frames with rich color gradients, fog, and cinematic textures.
    """
    img = Image.new("RGB", (width, height), color=(10, 12, 18))
    draw = ImageDraw.Draw(img)

    palettes = [
        ((12, 16, 28), (28, 38, 54), (180, 200, 220)),   # Cold moonlit blue
        ((24, 14, 14), (52, 28, 28), (220, 160, 140)),   # Amber rust horror
        ((14, 22, 18), (26, 48, 38), (140, 210, 170)),   # Eerie toxic green
        ((18, 12, 24), (42, 26, 56), (190, 150, 220)),   # Ghostly violet
        ((20, 20, 20), (45, 45, 48), (210, 210, 210)),   # Dense fog monochrome
        ((25, 15, 10), (60, 32, 20), (230, 170, 120)),   # Candlelight gloom
    ]
    base_col, mid_col, light_col = palettes[(scene_index - 1) % len(palettes)]

    for y in range(height):
        ratio = y / float(height)
        r = int(base_col[0] * (1 - ratio) + mid_col[0] * ratio)
        g = int(base_col[1] * (1 - ratio) + mid_col[1] * ratio)
        b = int(base_col[2] * (1 - ratio) + mid_col[2] * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    fog_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    fog_draw = ImageDraw.Draw(fog_layer)
    for _ in range(12):
        cx = random.randint(0, width)
        cy = random.randint(int(height * 0.3), height)
        rx = random.randint(int(width * 0.3), int(width * 0.8))
        ry = random.randint(int(height * 0.1), int(height * 0.25))
        alpha = random.randint(15, 40)
        fog_draw.ellipse(
            [cx - rx, cy - ry, cx + rx, cy + ry],
            fill=(light_col[0], light_col[1], light_col[2], alpha),
        )
    fog_layer = fog_layer.filter(ImageFilter.GaussianBlur(radius=30))
    img.paste(fog_layer, (0, 0), fog_layer)

    draw = ImageDraw.Draw(img)
    wall_color = (max(0, base_col[0] - 5), max(0, base_col[1] - 5), max(0, base_col[2] - 5))
    draw.polygon([(0, 0), (int(width * 0.22), 0), (int(width * 0.15), height), (0, height)], fill=wall_color)
    draw.polygon([(width, 0), (int(width * 0.78), 0), (int(width * 0.85), height), (width, height)], fill=wall_color)

    floor_y = int(height * 0.72)
    draw.polygon(
        [(0, height), (width, height), (int(width * 0.85), floor_y), (int(width * 0.15), floor_y)],
        fill=(8, 10, 14),
    )

    door_w = int(width * 0.26)
    door_h = int(height * 0.28)
    door_x = (width - door_w) // 2
    door_y = floor_y - door_h
    for i in range(door_w // 2):
        draw.rectangle(
            [door_x + i, door_y + i // 2, door_x + door_w - i, floor_y],
            outline=(min(255, light_col[0] + 20), min(255, light_col[1] + 20), min(255, light_col[2] + 20)),
        )

    vignette = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    v_draw = ImageDraw.Draw(vignette)
    for d in range(60):
        v_alpha = int(180 * ((60 - d) / 60))
        v_draw.rectangle([d, d, width - d, height - d], outline=(0, 0, 0, v_alpha))
    vignette = vignette.filter(ImageFilter.GaussianBlur(radius=20))
    img.paste(vignette, (0, 0), vignette)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def save_scene_image(
    index: int,
    prompt: str,
    out_path: Path,
    *,
    width: int = 720,
    height: int = 1280,
    negative: str = DEFAULT_NEGATIVE,
) -> tuple[str, str]:
    """Generate and save one image using provider hierarchy:
    1. Cache reuse (if out_path is already valid, avoid redundant requests & cost)
    2. Pollinations Authenticated API (openai/gpt-image-1-mini) [PREFERRED]
    3. Hugging Face Serverless Router (HF_TOKEN)
    4. DeAPI (DEAPI_TOKEN)
    5. Procedural PIL Fallback (blocked during production upload by Visual Quality Policy)

    Returns (status, detail).
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Cache reuse: avoid redundant requests when valid image already exists on disk
    if out_path.is_file() and out_path.stat().st_size >= 1000:
        try:
            _validate_image_file(out_path)
            print(f"   [CACHE] Reusing existing valid image for scene {index}: {out_path.name}")
            return "ok", "cached_existing"
        except Exception:
            pass

    # 2. Preferred: Pollinations Authenticated API (openai/gpt-image-1-mini)
    pollinations_key = (
        os.environ.get("POLLINATIONS_API_KEY", "").strip()
        or os.environ.get("POLLINATIONS_TOKEN", "").strip()
        or os.environ.get("POLLINATION_API_KEY", "").strip()
    )
    if pollinations_key:
        try:
            model = os.environ.get("POLLINATIONS_MODEL", DEFAULT_POLLINATIONS_MODEL)
            img_bytes, used_model, _usage = _pollinations_gpt_image_generate(
                prompt,
                api_key=pollinations_key,
                width=width,
                height=height,
                model=model,
            )
            out_path.write_bytes(img_bytes)
            _validate_image_file(out_path)
            return "ok", f"pollinations ({used_model})"
        except Exception as e:
            safe_e = str(e).replace(pollinations_key, "[REDACTED]")
            print(f"[WARN] Pollinations GPT Image failed for scene {index}: {safe_e}")

    # 3. Hugging Face Serverless Router API
    hf_token = os.environ.get("HF_TOKEN", "").strip()
    if hf_token:
        try:
            raw_bytes, hf_model = _hf_generate(prompt, api_key=hf_token, width=width, height=height)
            with Image.open(io.BytesIO(raw_bytes)) as pil_img:
                pil_img = pil_img.convert("RGB")
                adapted = adapt_to_9_16(pil_img, target_width=width, target_height=height)
                buf = io.BytesIO()
                adapted.save(buf, format="PNG")
                out_path.write_bytes(buf.getvalue())
            _validate_image_file(out_path)
            return "ok", f"huggingface ({hf_model})"
        except Exception as e:
            safe_e = str(e).replace(hf_token, "[REDACTED]")
            print(f"[WARN] HuggingFace failed for scene {index}: {safe_e}")

    # 4. DeAPI if configured
    deapi_key = os.environ.get("DEAPI_TOKEN", "").strip()
    if deapi_key:
        try:
            model = os.environ.get("DEAPI_MODEL", "Flux_2_Klein_4B_BF16")
            raw_bytes = _deapi_generate(prompt, api_key=deapi_key, width=width, height=height, model=model)
            with Image.open(io.BytesIO(raw_bytes)) as pil_img:
                pil_img = pil_img.convert("RGB")
                adapted = adapt_to_9_16(pil_img, target_width=width, target_height=height)
                buf = io.BytesIO()
                adapted.save(buf, format="PNG")
                out_path.write_bytes(buf.getvalue())
            _validate_image_file(out_path)
            return "ok", f"deapi ({model})"
        except Exception as e:
            safe_e = str(e).replace(deapi_key, "[REDACTED]")
            print(f"[WARN] DeAPI failed for scene {index}: {safe_e}")

    # 5. Deterministic local PIL procedural fallback
    try:
        img_bytes = _procedural_fallback_generate(prompt, width=width, height=height, scene_index=index)
        out_path.write_bytes(img_bytes)
        _validate_image_file(out_path)
        return "ok", "procedural_pil_fallback"
    except Exception as e:
        return "fail", f"All image generators failed including local fallback: {e}"


def _validate_image_file(file_path: Path) -> None:
    """Validate file exists, has content, and can be read by PIL."""
    if not file_path.is_file() or file_path.stat().st_size < 500:
        raise ValueError(f"Generated image {file_path} is corrupt or too small")
    with Image.open(file_path) as im:
        im.verify()
