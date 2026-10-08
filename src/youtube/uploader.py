"""YouTube Shorts uploader using Google Data API v3."""

import json
import os
import urllib.request
from pathlib import Path
from typing import Dict, Any, Tuple
from src.youtube.auth import get_access_token
from src.utils.logging import log, log_warn, log_success
from src.utils.files import read_json, write_json
from src.config import UPLOADS_FILE

class YouTubeUploader:
    def __init__(self):
        self.uploads_path = UPLOADS_FILE

    def is_configured(self) -> bool:
        try:
            return bool(get_access_token())
        except Exception:
            return False

    def upload_short(
        self,
        video_path: Path,
        metadata: Dict[str, Any],
        thumbnail_path: Path = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """Upload video to YouTube as a vertical Short."""
        title = metadata.get("title", "Mysterious Discovery #Shorts")
        description = metadata.get("description", "")
        tags = metadata.get("tags", ["Shorts", "Mystery"])

        if not title.endswith("#Shorts") and "#shorts" not in title.lower():
            title = f"{title} #Shorts"

        if dry_run or not self.is_configured():
            log_warn("UPLOAD", "Dry-run mode or YouTube credentials not present. Simulating successful upload.")
            simulated_id = f"sim_{os.urandom(4).hex()}"
            record = {
                "video_id": simulated_id,
                "youtube_url": f"https://youtube.com/shorts/{simulated_id}",
                "title": title,
                "status": "simulated",
                "dry_run": True
            }
            self._save_record(record)
            return record

        log("UPLOAD", f"Initiating YouTube Shorts upload for '{title}'...")
        access_token = get_access_token()
        if not access_token:
            raise RuntimeError("Missing active YouTube access token.")

        # Resumable upload initiation
        init_url = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": "27"  # Education / Documentary
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False
            }
        }

        init_req = urllib.request.Request(
            init_url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": "video/mp4",
                "X-Upload-Content-Length": str(video_path.stat().st_size)
            },
            method="POST"
        )

        with urllib.request.urlopen(init_req, timeout=30) as init_resp:
            upload_url = init_resp.headers.get("Location")

        if not upload_url:
            raise RuntimeError("Failed to obtain YouTube resumable upload URL.")

        # Upload binary stream
        with open(video_path, "rb") as f:
            video_data = f.read()

        upload_req = urllib.request.Request(
            upload_url,
            data=video_data,
            headers={
                "Content-Type": "video/mp4",
                "Content-Length": str(len(video_data))
            },
            method="PUT"
        )

        with urllib.request.urlopen(upload_req, timeout=300) as up_resp:
            result = json.loads(up_resp.read().decode("utf-8"))

        video_id = result.get("id")
        video_url = f"https://youtube.com/shorts/{video_id}"
        log_success("UPLOAD", f"Uploaded successfully! URL: {video_url}")

        record = {
            "video_id": video_id,
            "youtube_url": video_url,
            "title": title,
            "status": "uploaded",
            "dry_run": False
        }
        self._save_record(record)
        return record

    def _save_record(self, record: Dict[str, Any]):
        records = read_json(self.uploads_path, default=[])
        records.append(record)
        write_json(self.uploads_path, records)
