"""Fallback Video Provider: High-fidelity procedural 9:16 vertical video generator via FFmpeg."""

import subprocess
import hashlib
from pathlib import Path
from src.config import VIDEO_WIDTH, VIDEO_HEIGHT

class FallbackVideoProvider:
    name = "fallback_procedural"

    def is_configured(self) -> bool:
        return True

    def generate_clip(self, prompt: str, output_path: Path, duration_seconds: int = 6) -> Path:
        """
        Generate a 9:16 vertical silent animated clip with dynamic lighting gradients and motion.
        Uses fast GPU/CPU compatible FFmpeg filtergraphs.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        h = int(hashlib.md5(prompt.encode("utf-8")).hexdigest()[:8], 16)
        colors = ["0x111625", "0x1e152a", "0x0f2427", "0x2c1810", "0x141e30"]
        c1 = colors[h % len(colors)]
        c2 = colors[(h + 1) % len(colors)]

        # Fast and cinematic vertical motion canvas
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c={c1}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:d={duration_seconds}",
            "-vf", (
                f"drawbox=y=ih*0.2:h=ih*0.6:w=iw:c={c2}@0.4:t=fill,"
                f"boxblur=luma_radius=80:luma_power=3,"
                f"noise=alls=8:allf=t+u,"
                f"zoompan=z='min(zoom+0.001,1.06)':d=125:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={VIDEO_WIDTH}x{VIDEO_HEIGHT}"
            ),
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            "-r", "24",
            "-t", str(duration_seconds),
            "-an",  # Audio strictly muted!
            str(output_path)
        ]

        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
            return output_path
        except subprocess.CalledProcessError:
            # Emergency minimalist vertical background
            simple_cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", f"color=c={c1}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:d={duration_seconds}",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-pix_fmt", "yuv420p",
                "-r", "24",
                "-t", str(duration_seconds),
                "-an",
                str(output_path)
            ]
            subprocess.run(simple_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            return output_path
