"""Fallback Thumbnail Provider: Procedural cinematic vertical 1080x1920 poster via FFmpeg."""

import subprocess
import hashlib
from pathlib import Path
from src.config import VIDEO_WIDTH, VIDEO_HEIGHT

class FallbackThumbnailProvider:
    name = "fallback_procedural"

    def is_configured(self) -> bool:
        return True

    def generate_image(self, prompt: str, output_path: Path) -> Path:
        """Create a high-contrast cinematic vertical poster image fast."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        h = int(hashlib.md5(prompt.encode("utf-8")).hexdigest()[:8], 16)
        colors = ["0x0d131f", "0x1f0d19", "0x0a1b1a", "0x241208"]
        c1 = colors[h % len(colors)]
        c2 = colors[(h + 1) % len(colors)]

        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c={c1}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:d=1",
            "-vf", f"drawbox=y=ih*0.3:h=ih*0.4:w=iw:c={c2}@0.6:t=fill,boxblur=luma_radius=100:luma_power=2",
            "-frames:v", "1",
            str(output_path)
        ]

        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return output_path
