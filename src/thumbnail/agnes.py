"""Primary Thumbnail Provider: Agnes Image API."""

import json
import urllib.request
from pathlib import Path
from typing import Optional
from src.config import AGNES_API_KEY, AGNES_BASE_URL
from src.utils.logging import log

class AgnesImageProvider:
    name = "agnes"

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or AGNES_API_KEY
        self.base_url = (base_url or AGNES_BASE_URL).rstrip("/")

    def is_configured(self) -> bool:
        return bool(self.api_key and len(self.api_key) > 4)

    def generate_image(self, prompt: str, output_path: Path) -> Path:
        """Generate 9:16 vertical thumbnail image via Agnes."""
        if not self.is_configured():
            raise ValueError("AGNES_API_KEY is not configured.")

        url = f"{self.base_url}/images/generations"
        payload = {
            "prompt": prompt,
            "size": "1080x1920",
            "model": "agnes-image-2.1-flash"
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": "Monkey-Baba/1.0"
            },
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=40) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        image_url = data.get("data", [{}])[0].get("url") or data.get("image_url")
        if not image_url:
            raise RuntimeError(f"Agnes image generation missing URL: {data}")

        dl_req = urllib.request.Request(image_url, headers={"User-Agent": "Monkey-Baba/1.0"})
        with urllib.request.urlopen(dl_req, timeout=30) as d_resp, open(output_path, "wb") as f:
            f.write(d_resp.read())

        return output_path
