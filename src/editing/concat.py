"""Concatenate silent clips into a continuous reel."""

import subprocess
from pathlib import Path
from typing import List
from src.utils.logging import log

def concatenate_clips(clip_paths: List[Path], output_path: Path) -> Path:
    """Concatenate multiple silent MP4 clips into a single reel.mp4."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Build concat file list
    list_file = output_path.parent / "concat_list.txt"
    with open(list_file, "w", encoding="utf-8") as f:
        for p in clip_paths:
            f.write(f"file '{p.resolve()}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_file),
        "-c:v", "copy",  # Direct stream copy for instant concatenation!
        "-an",
        str(output_path)
    ]

    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
    except subprocess.CalledProcessError:
        # Fallback to re-encoding if clips had heterogeneous properties
        fallback_cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_file),
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            "-r", "24",
            "-an",
            str(output_path)
        ]
        subprocess.run(fallback_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    return output_path
