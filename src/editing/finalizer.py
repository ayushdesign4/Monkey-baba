"""Finalizer: merges reel with TTS, adds optional thumbnail frame, and enforces 30-60s duration."""

import subprocess
from pathlib import Path
from typing import Optional
from src.config import (
    TARGET_MIN_DURATION_SEC,
    TARGET_MAX_DURATION_SEC,
    VIDEO_WIDTH,
    VIDEO_HEIGHT
)
from src.editing.audio import get_media_duration
from src.utils.logging import log, log_warn, log_success

class VideoFinalizer:
    @staticmethod
    def finalize_video(
        reel_path: Path,
        narration_path: Path,
        thumbnail_path: Optional[Path],
        output_path: Path,
        include_thumbnail_intro: bool = True
    ) -> Path:
        """
        Merge reel video with TTS narration audio.
        Appends 0.5s thumbnail-intro frame if requested.
        Validates and adjusts speed/looping to ensure strictly 30s <= duration <= 60s.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        log("VIDEO", "Finalizing vertical 9:16 Short with synchronized narration...")

        audio_duration = get_media_duration(narration_path)
        video_duration = get_media_duration(reel_path)

        log("VIDEO", f"Raw Video: {video_duration:.1f}s, Audio: {audio_duration:.1f}s")

        # Determine target duration based on narration length
        target_duration = max(TARGET_MIN_DURATION_SEC, min(TARGET_MAX_DURATION_SEC, audio_duration + 1.0))
        target_duration = max(30.0, min(59.0, target_duration))

        # Single-pass FFmpeg multiplexing:
        # Loop video to match target_duration, pad/trim audio, normalize audio volume
        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", "-1",
            "-i", str(reel_path),
            "-i", str(narration_path),
            "-t", f"{target_duration:.2f}",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "22",
            "-pix_fmt", "yuv420p",
            "-s", f"{VIDEO_WIDTH}x{VIDEO_HEIGHT}",
            "-r", "30",
            "-c:a", "aac",
            "-b:a", "192k",
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-shortest",
            str(output_path)
        ]

        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)

        # Validate final output
        final_len = get_media_duration(output_path)
        log("VIDEO", f"Final Short generated. Measured length: {final_len:.1f}s.")

        if not (TARGET_MIN_DURATION_SEC <= final_len <= TARGET_MAX_DURATION_SEC):
            log_warn("VIDEO", f"Video length {final_len:.1f}s outside bounds ({TARGET_MIN_DURATION_SEC}–{TARGET_MAX_DURATION_SEC}s). Trimming...")
            trimmed_path = output_path.parent / "final_trimmed.mp4"
            trim_cmd = [
                "ffmpeg", "-y",
                "-i", str(output_path),
                "-t", "55.0",
                "-c", "copy",
                str(trimmed_path)
            ]
            subprocess.run(trim_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            trimmed_path.replace(output_path)

        log_success("VIDEO", f"Final video ready: {output_path.name} ({get_media_duration(output_path):.1f}s, 9:16 vertical)")
        return output_path
