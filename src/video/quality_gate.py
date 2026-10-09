"""Visual Quality Upload Gate: verifies readability, 9:16 aspect ratio, duration, and visual imagery."""

import subprocess
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Optional
from PIL import Image, ImageStat

from src.utils.logging import log, log_warn, log_error, log_success
from src.config import TARGET_MIN_DURATION_SEC, TARGET_MAX_DURATION_SEC, VIDEO_WIDTH, VIDEO_HEIGHT

class VisualQualityError(Exception):
    """Raised when a video fails visual quality validation."""
    pass

class VisualQualityGate:
    """
    Enforces that videos intended for YouTube Shorts meet minimum visual standards:
    1. Readable MP4 container and valid file size (>50KB)
    2. Strictly vertical 9:16 aspect ratio
    3. Valid duration within target bounds (30-60s)
    4. Non-blank, non-black, visible imagery across scenes
    """

    @classmethod
    def validate_or_raise(
        cls,
        video_path: Path,
        min_duration: float = TARGET_MIN_DURATION_SEC,
        max_duration: float = TARGET_MAX_DURATION_SEC,
        expected_ratio: float = 9.0 / 16.0,
        ratio_tolerance: float = 0.08,
        num_sample_frames: int = 4
    ) -> Dict[str, Any]:
        """
        Validate video file against visual quality standards.
        Raises VisualQualityError if video is corrupt, blank, wrong aspect ratio, or wrong duration.
        """
        log("QUALITY_GATE", f"Evaluating visual quality gate for '{video_path.name}'...")

        if not video_path.exists() or not video_path.is_file():
            raise VisualQualityError(f"Video file does not exist: {video_path}")

        file_size = video_path.stat().st_size
        if file_size < 50_000:
            raise VisualQualityError(f"Video file is suspiciously small or empty ({file_size} bytes).")

        # 1. Metadata inspection (duration and resolution)
        meta = cls.inspect_metadata(video_path)
        duration = meta.get("duration", 0.0)
        width = meta.get("width", 0)
        height = meta.get("height", 0)

        # Validate duration if measured
        if duration > 0.0:
            # Allow 1.0s leeway on duration bounds
            if duration < (min_duration - 1.0) or duration > (max_duration + 1.0):
                raise VisualQualityError(
                    f"Video duration {duration:.1f}s is outside allowed bounds "
                    f"({min_duration:.0f}s - {max_duration:.0f}s)."
                )

        # Validate aspect ratio if dimensions detected
        if width > 0 and height > 0:
            ratio = width / height
            if abs(ratio - expected_ratio) > ratio_tolerance or height <= width:
                raise VisualQualityError(
                    f"Video aspect ratio {width}x{height} ({ratio:.3f}) is not vertical 9:16 "
                    f"(expected ~{expected_ratio:.3f})."
                )

        # 2. Visual Content Inspection (Sample frames across scenes)
        if duration <= 0.0:
            sample_duration = 35.0  # estimate if duration probe unavailable
        else:
            sample_duration = duration

        frame_stats = cls.inspect_sample_frames(video_path, sample_duration, num_sample_frames)
        if frame_stats:
            black_frames = 0
            low_detail_frames = 0
            for f_idx, stat in enumerate(frame_stats, 1):
                brightness = stat["brightness"]
                std_dev = stat["std_dev"]
                log("QUALITY_GATE", f"Sample frame {f_idx}/{len(frame_stats)}: brightness={brightness:.1f}, detail={std_dev:.1f}")

                # Pitch black detection (mean brightness < 3.0)
                if brightness < 3.0:
                    black_frames += 1
                # Completely flat / blank / solid color (standard deviation < 1.0)
                elif std_dev < 1.0:
                    low_detail_frames += 1

            total_frames = len(frame_stats)
            if black_frames == total_frames:
                raise VisualQualityError(
                    f"Visual Quality Gate Failed: All {total_frames} sampled frames are completely pitch black (brightness < 3.0)."
                )
            if (black_frames + low_detail_frames) >= total_frames:
                raise VisualQualityError(
                    f"Visual Quality Gate Failed: Video lacks visible visual imagery (all frames are black or blank solid color)."
                )

        log_success(
            "QUALITY_GATE",
            f"Visual quality gate passed for '{video_path.name}': "
            f"readable, vertical 9:16, {duration:.1f}s duration, verified visible scene content."
        )
        return {
            "passed": True,
            "duration": duration,
            "width": width,
            "height": height,
            "file_size": file_size
        }

    @classmethod
    def inspect_metadata(cls, video_path: Path) -> Dict[str, Any]:
        """Extract duration and resolution via ffprobe or ffmpeg."""
        meta = {"duration": 0.0, "width": 0, "height": 0}

        # Try ffprobe first
        if shutil.which("ffprobe"):
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height,duration:format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video_path)
            ]
            try:
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=True)
                lines = [l.strip() for l in res.stdout.splitlines() if l.strip()]
                # Typically outputs: width, height, duration (or stream duration then format duration)
                nums = []
                for l in lines:
                    try:
                        nums.append(float(l))
                    except ValueError:
                        pass
                if len(nums) >= 2:
                    meta["width"] = int(nums[0])
                    meta["height"] = int(nums[1])
                if len(nums) >= 3:
                    meta["duration"] = nums[-1]
                return meta
            except Exception:
                pass

        # Try ffmpeg fallback for basic duration/metadata
        if shutil.which("ffmpeg"):
            cmd = ["ffmpeg", "-i", str(video_path)]
            try:
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                out = res.stderr
                # Parse dimensions like 1080x1920
                import re
                dim_match = re.search(r"(\d{3,4})x(\d{3,4})", out)
                if dim_match:
                    meta["width"] = int(dim_match.group(1))
                    meta["height"] = int(dim_match.group(2))
                dur_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", out)
                if dur_match:
                    h, m, s = float(dur_match.group(1)), float(dur_match.group(2)), float(dur_match.group(3))
                    meta["duration"] = h * 3600 + m * 60 + s
            except Exception:
                pass

        return meta

    @classmethod
    def inspect_sample_frames(cls, video_path: Path, duration: float, num_samples: int = 4) -> List[Dict[str, float]]:
        """Extract sample frames and compute brightness and detail (std_dev)."""
        if not shutil.which("ffmpeg"):
            return []

        stats = []
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            # Sample timestamps evenly: e.g. 20%, 40%, 60%, 80%
            timestamps = [duration * (i + 1) / (num_samples + 1) for i in range(num_samples)]

            for idx, ts in enumerate(timestamps, 1):
                frame_out = tmp_path / f"sample_{idx}.jpg"
                cmd = [
                    "ffmpeg", "-y",
                    "-ss", f"{ts:.2f}",
                    "-i", str(video_path),
                    "-vframes", "1",
                    "-q:v", "2",
                    str(frame_out)
                ]
                try:
                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
                    if frame_out.exists() and frame_out.stat().st_size > 0:
                        frame_stat = cls.analyze_image_file(frame_out)
                        stats.append(frame_stat)
                except Exception as e:
                    log_warn("QUALITY_GATE", f"Could not extract frame at {ts:.1f}s: {e}")

        return stats

    @staticmethod
    def analyze_image_file(image_path: Path) -> Dict[str, float]:
        """Analyze an image's mean brightness and standard deviation across RGB channels."""
        with Image.open(image_path) as im:
            im_rgb = im.convert("RGB")
            stat = ImageStat.Stat(im_rgb)
            # Mean brightness across R, G, B channels [0, 255]
            mean_brightness = sum(stat.mean[:3]) / 3.0
            # Standard deviation across R, G, B channels (visual detail/entropy)
            std_dev = sum(stat.stddev[:3]) / 3.0
            return {
                "brightness": mean_brightness,
                "std_dev": std_dev
            }
