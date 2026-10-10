"""Multi-provider image generation: DeAPI -> Hugging Face (HF_TOKEN) -> Pollinations -> Procedural PIL fallback.

All outputs are vertical 9:16 (default 720x1280 or 1080x1920) formatted for YouTube Shorts.
"""
from __future__ import annotations

import io
import math
import os
import random
import time
import urllib.parse
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFilter

DEAPI_SUBMIT_URL = "https://api.deapi.ai/api/v1/client/txt2img"
DEAPI_POLL_URL = "https://api.deapi.ai/api/v1/client/request-status"

DEFAULT_HF_MODEL = os.environ.get("HF_IMAGE_MODEL", "black-forest-labs/FLUX.1-schnell")

STYLE_SUFFIX = (
    ", dark eerie cinematic horror photography, atmospheric volumetric fog, haunting lighting, "
    "dramatic shadows, photorealistic, 8k, sharp focus, sinister mood, professional cinematic framing, "
    "9:16 vertical composition, no text, no captions, no watermark, no logos"
)

DEFAULT_NEGATIVE = (
    "bright cheerful sunny daylight, smiling faces, cartoon, anime, illustration, "
    "blurry, low quality, watermark, logo, text, title, signature, ugly, distorted anatomy, "
    "graphic gore, extreme blood, mutilation"
)


def full_visual_prompt(scene: str, style_suffix: str | None = None) -> str:
    """Combine the scene description with a channel-specific style suffix."""
    return f"{scene.strip()}{(style_suffix or STYLE_SUFFIX)}"


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
    model: str = DEFAULT_HF_MODEL,
) -> bytes:
    """Generate image via Hugging Face Inference API / Router."""
    # Try the Hugging Face router first, then direct api-inference endpoint
    endpoints = [
        f"https://router.huggingface.co/hf-inference/models/{model}",
        f"https://api-inference.huggingface.co/models/{model}",
    ]
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

    last_err = ""
    with httpx.Client(timeout=45.0) as client:
        for url in endpoints:
            try:
                resp = client.post(url, json=payload, headers=headers)
                if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image/"):
                    return resp.content
                if resp.status_code == 503 and "estimated_time" in resp.text:
                    time.sleep(10.0)
                    resp = client.post(url, json=payload, headers=headers)
                    if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image/"):
                        return resp.content
                last_err = f"HTTP {resp.status_code}: {resp.text[:120]}"
            except Exception as e:
                last_err = str(e)

    raise RuntimeError(f"HuggingFace inference failed: {last_err}")


def _pollinations_generate(
    prompt: str,
    *,
    width: int,
    height: int,
) -> bytes:
    """Keyless zero-cost image generation via Pollinations AI."""
    safe_prompt = urllib.parse.quote(prompt[:400])
    seed = random.randint(1, 999999)
    url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width={width}&height={height}&seed={seed}&nologo=true&enhance=false"

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        if not resp.headers.get("content-type", "").startswith("image/") and len(resp.content) < 1000:
            raise RuntimeError(f"Pollinations returned invalid content type: {resp.headers.get('content-type')}")
        return resp.content


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

    # Palette selection based on scene index
    palettes = [
        ((12, 16, 28), (28, 38, 54), (180, 200, 220)),   # Cold moonlit blue
        ((24, 14, 14), (52, 28, 28), (220, 160, 140)),   # Amber rust horror
        ((14, 22, 18), (26, 48, 38), (140, 210, 170)),   # Eerie toxic green
        ((18, 12, 24), (42, 26, 56), (190, 150, 220)),   # Ghostly violet
        ((20, 20, 20), (45, 45, 48), (210, 210, 210)),   # Dense fog monochrome
        ((25, 15, 10), (60, 32, 20), (230, 170, 120)),   # Candlelight gloom
    ]
    base_col, mid_col, light_col = palettes[(scene_index - 1) % len(palettes)]

    # Draw vertical gradient background
    for y in range(height):
        ratio = y / float(height)
        r = int(base_col[0] * (1 - ratio) + mid_col[0] * ratio)
        g = int(base_col[1] * (1 - ratio) + mid_col[1] * ratio)
        b = int(base_col[2] * (1 - ratio) + mid_col[2] * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    # Add atmospheric volumetric fog layers
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

    # Add silhouette structures (corridor arches, doorways, or trees)
    draw = ImageDraw.Draw(img)
    wall_color = (max(0, base_col[0] - 5), max(0, base_col[1] - 5), max(0, base_col[2] - 5))
    draw.polygon([(0, 0), (int(width * 0.22), 0), (int(width * 0.15), height), (0, height)], fill=wall_color)
    draw.polygon([(width, 0), (int(width * 0.78), 0), (int(width * 0.85), height), (width, height)], fill=wall_color)

    # Floor horizon
    floor_y = int(height * 0.72)
    draw.polygon(
        [(0, height), (width, height), (int(width * 0.85), floor_y), (int(width * 0.15), floor_y)],
        fill=(8, 10, 14),
    )

    # Distant mysterious aperture / doorway light in center
    door_w = int(width * 0.26)
    door_h = int(height * 0.28)
    door_x = (width - door_w) // 2
    door_y = floor_y - door_h
    for i in range(door_w // 2):
        glow_alpha = int(120 * (1 - (i / (door_w / 2))))
        draw.rectangle(
            [door_x + i, door_y + i // 2, door_x + door_w - i, floor_y],
            outline=(min(255, light_col[0] + 20), min(255, light_col[1] + 20), min(255, light_col[2] + 20)),
        )

    # Vignette shadow around edges
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
    DeAPI -> Hugging Face (HF_TOKEN) -> Pollinations (free keyless) -> Local PIL fallback.
    Returns (status, detail).
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Try DeAPI if configured
    deapi_key = os.environ.get("DEAPI_TOKEN", "").strip()
    if deapi_key:
        try:
            model = os.environ.get("DEAPI_MODEL", "Flux_2_Klein_4B_BF16")
            img_bytes = _deapi_generate(prompt, api_key=deapi_key, width=width, height=height, model=model)
            out_path.write_bytes(img_bytes)
            _validate_image_file(out_path)
            return "ok", "deapi"
        except Exception as e:
            print(f"[WARN] DeAPI failed for scene {index}: {e}")

    # 2. Try Hugging Face if configured
    hf_token = os.environ.get("HF_TOKEN", "").strip()
    if hf_token:
        try:
            img_bytes = _hf_generate(prompt, api_key=hf_token, width=width, height=height)
            out_path.write_bytes(img_bytes)
            _validate_image_file(out_path)
            return "ok", "huggingface"
        except Exception as e:
            print(f"[WARN] HuggingFace failed for scene {index}: {e}")

    # 3. Try Pollinations (free keyless AI generator)
    try:
        img_bytes = _pollinations_generate(prompt, width=width, height=height)
        out_path.write_bytes(img_bytes)
        _validate_image_file(out_path)
        return "ok", "pollinations"
    except Exception as e:
        print(f"[WARN] Pollinations failed for scene {index}: {e}")

    # 4. Deterministic local PIL procedural fallback
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
