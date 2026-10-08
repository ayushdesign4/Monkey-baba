"""Audio inspection and duration measurement."""

import subprocess
import json
from pathlib import Path

def get_media_duration(file_path: Path) -> float:
    """Extract exact duration in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(file_path)
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True, text=True)
        return float(res.stdout.strip())
    except Exception:
        return 0.0
