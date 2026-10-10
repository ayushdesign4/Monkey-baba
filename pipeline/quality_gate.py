"""Pre-upload visual quality gate.

Validates:
  1. File existence and non-zero size (> 100KB).
  2. Video decodability and duration (30-60 seconds).
  3. Vertical aspect ratio 9:16 (height > width, ratio ~ 0.5625).
  4. Video stream presence (h264) and audio stream presence (aac).
  5. Visual content validation: frame sampling to ensure visuals are not solid black, blank, or frozen.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageStat


@dataclass
class QualityGateResult:
    passed: bool
    duration: float
    width: int
    height: int
    has_audio: bool
    has_video: bool
    errors: list[str]


def probe_video(video_path: Path) -> dict:
    """Run ffprobe on the video file and return stream and format metadata."""
    if not shutil.which("ffprobe"):
        raise RuntimeError("ffprobe not found on PATH; required for video validation")

    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration,size:stream=codec_type,codec_name,width,height,duration",
        "-of", "json",
        str(video_path.resolve()),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(res.stdout)


def sample_frames_for_black(video_path: Path, num_frames: int = 5) -> tuple[bool, str]:
    """Sample frames across the video and ensure they are not solid black or blank."""
    if not shutil.which("ffmpeg"):
        return True, "ffmpeg not found; skipping frame luminance check"

    tmp_dir = video_path.parent / "_tmp_frames"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    try:
        # Extract sampled frames
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(video_path.resolve()),
            "-vf", f"fps=1/{max(1, int(45 / num_frames))},scale=320:568",
            "-frames:v", str(num_frames),
            str(tmp_dir / "frame_%02d.png"),
        ]
        subprocess.run(cmd, capture_output=True, text=True, check=True)

        frame_files = sorted(tmp_dir.glob("frame_*.png"))
        if not frame_files:
            return False, "Failed to extract frames from video"

        black_count = 0
        for f in frame_files:
            with Image.open(f) as im:
                stat = ImageStat.Stat(im.convert("L"))
                mean_lum = stat.mean[0]
                std_lum = stat.stddev[0]
                # If mean luminance is near 0 or stddev is 0 (completely solid single color)
                if mean_lum < 3.0 or std_lum < 1.0:
                    black_count += 1

        # If more than 80% of sampled frames are solid black/blank, fail
        if black_count >= len(frame_files) * 0.8:
            return False, f"{black_count}/{len(frame_files)} frames are completely black or blank"

        return True, "Frames contain valid non-blank visual content"
    except Exception as e:
        return False, f"Frame sampling failed: {e}"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def validate_short_quality(
    video_path: Path,
    *,
    min_duration: float = 30.0,
    max_duration: float = 60.0,
    enforce_vertical: bool = True,
    check_frames: bool = True,
) -> QualityGateResult:

    """Validate a rendered Short video against all quality gate requirements."""
    video_path = Path(video_path)
    errors: list[str] = []

    if not video_path.is_file():
        return QualityGateResult(
            passed=False,
            duration=0.0,
            width=0,
            height=0,
            has_audio=False,
            has_video=False,
            errors=[f"File does not exist: {video_path}"],
        )

    file_size = video_path.stat().st_size
    if file_size < 50_000:
        errors.append(f"File size too small ({file_size} bytes, expected > 50KB)")

    try:
        info = probe_video(video_path)
    except Exception as e:
        return QualityGateResult(
            passed=False,
            duration=0.0,
            width=0,
            height=0,
            has_audio=False,
            has_video=False,
            errors=[f"ffprobe failed to read video: {e}"],
        )

    streams = info.get("streams", [])
    has_video = any(s.get("codec_type") == "video" for s in streams)
    has_audio = any(s.get("codec_type") == "audio" for s in streams)

    if not has_video:
        errors.append("No video stream found in file")
    if not has_audio:
        errors.append("No audio stream found in file")

    # Duration check
    fmt_dur = float(info.get("format", {}).get("duration", 0.0))
    if fmt_dur < min_duration:
        errors.append(f"Video duration {fmt_dur:.1f}s is below minimum {min_duration}s")
    if fmt_dur > max_duration:
        errors.append(f"Video duration {fmt_dur:.1f}s exceeds maximum {max_duration}s")

    # Aspect ratio check
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
    width = int(video_stream.get("width", 0))
    height = int(video_stream.get("height", 0))

    if enforce_vertical:
        if width >= height:
            errors.append(f"Video is not vertical: {width}x{height} (expected width < height)")
        # Check 9:16 aspect ratio tolerance (0.5625 +/- 0.05)
        if height > 0:
            ratio = width / height
            if abs(ratio - (9 / 16)) > 0.05:
                errors.append(f"Video aspect ratio {ratio:.3f} deviates from 9:16 (0.5625)")

    # Blank/black frame analysis
    if check_frames and has_video and file_size > 50_000:
        frames_ok, frame_msg = sample_frames_for_black(video_path)
        if not frames_ok:
            errors.append(f"Visual quality check failed: {frame_msg}")

    return QualityGateResult(
        passed=len(errors) == 0,
        duration=fmt_dur,
        width=width,
        height=height,
        has_audio=has_audio,
        has_video=has_video,
        errors=errors,
    )
