"""Mute and strip audio from generated clips (Section 12 requirement)."""

import subprocess
from pathlib import Path
from src.utils.logging import log

def mute_clip(input_path: Path, output_path: Path) -> Path:
    """Strip all audio streams from clip, outputting silent video."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-c:v", "copy",
        "-an",  # Strip audio
        str(output_path)
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
    return output_path
