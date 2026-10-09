"""Primary Video Provider: Agnes API."""

import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional
from src.config import AGNES_API_KEY, AGNES_BASE_URL
from src.utils.logging import log, log_warn, log_error

class AgnesVideoProvider:
    name = "agnes"

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or AGNES_API_KEY
        self.base_url = (base_url or AGNES_BASE_URL).rstrip("/")

    def is_configured(self) -> bool:
        return bool(self.api_key and len(self.api_key) > 4)

    def generate_clip(self, prompt: str, output_path: Path, duration_seconds: int = 6) -> Path:
        """
        Request video generation from Agnes API.
        Submits prompt, polls until ready, and saves MP4 to output_path.
        """
        if not self.is_configured():
            raise ValueError("AGNES_API_KEY is not configured.")

        url = f"{self.base_url}/videos"
        # Official Agnes API requires 'seconds' (string in range 4-12, default 5 or 6)
        valid_seconds = str(max(4, min(12, int(duration_seconds))))
        payload = {
            "model": "agnes-video-2.5",
            "prompt": prompt,
            "seconds": valid_seconds,
            "aspect_ratio": "9:16"
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

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="ignore")
            if self.api_key and self.api_key in err:
                err = err.replace(self.api_key, "[REDACTED]")
            clean_err = err.strip()[:200]
            if e.code == 400:
                raise ValueError(f"Agnes HTTP 400 Bad Request: {clean_err}")
            raise RuntimeError(f"Agnes HTTP {e.code}: {clean_err}")
        except ValueError:
            raise
        except Exception as e:
            err_msg = str(e)
            if self.api_key and self.api_key in err_msg:
                err_msg = err_msg.replace(self.api_key, "[REDACTED]")
            raise RuntimeError(f"Agnes submission failed: {err_msg[:200]}")

        task_id = data.get("video_id") or data.get("id") or data.get("task_id")
        video_url = data.get("video_url") or data.get("url")

        # If already synchronous
        if video_url:
            self._download(video_url, output_path)
            return output_path

        if not task_id:
            raise RuntimeError(f"Agnes API did not return video_url or task_id: {data}")

        # Polling loop
        poll_url = f"{self.base_url}/agnesapi?video_id={task_id}"
        max_wait = 180
        start_time = time.time()

        while time.time() - start_time < max_wait:
            time.sleep(5)
            poll_req = urllib.request.Request(
                poll_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "User-Agent": "Monkey-Baba/1.0"
                }
            )
            try:
                with urllib.request.urlopen(poll_req, timeout=20) as p_resp:
                    status_data = json.loads(p_resp.read().decode("utf-8"))
                    status = str(status_data.get("status", "")).lower()
                    if status in ("succeeded", "completed", "done", "success"):
                        dl_url = status_data.get("video_url") or status_data.get("url") or status_data.get("output", {}).get("url")
                        if not dl_url:
                            raise RuntimeError(f"Completed task missing download URL: {status_data}")
                        self._download(dl_url, output_path)
                        return output_path
                    elif status in ("failed", "error"):
                        raise RuntimeError(f"Agnes task failed: {status_data.get('error')}")
            except Exception as e:
                log_warn("VIDEO", f"Polling Agnes task {task_id}: {e}")

        raise TimeoutError(f"Agnes video generation timed out after {max_wait}s.")

    def _download(self, url: str, target: Path):
        req = urllib.request.Request(url, headers={"User-Agent": "Monkey-Baba/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp, open(target, "wb") as f:
            f.write(resp.read())
