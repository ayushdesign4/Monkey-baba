"""Thumbnail Provider Manager."""

from pathlib import Path
from typing import Dict, Any, Tuple
from src.thumbnail.agnes import AgnesImageProvider
from src.thumbnail.fallback import FallbackThumbnailProvider
from src.brain.manager import BrainManager
from src.utils.logging import log, log_warn, log_success
from src.utils.retry import retry_with_backoff

THUMB_PROMPT_TEMPLATE = """
Topic: "{topic}"
Key hook: "{summary}"

Generate a single master prompt for a VIRAL, high-CTR vertical (9:16) YouTube thumbnail image.
REQUIREMENTS:
- Simple, cinematic composition with high-contrast subject separation
- Emotionally expressive, eerie, or astonishing
- NO text, NO words, NO letters, NO watermarks
- Photorealistic 8k, dramatic lighting, vertical framing 9:16
- Respond with ONLY the raw prompt text string.
"""

class ThumbnailManager:
    def __init__(self, brain: BrainManager):
        self.brain = brain
        self.primary = AgnesImageProvider()
        self.fallback = FallbackThumbnailProvider()
        self.last_provider_used = None
        self.fallback_used = False

    def generate_thumbnail(self, topic_record: Dict[str, Any], run_dir: Path) -> Tuple[Path, str, bool]:
        """Generate high-CTR thumbnail for the Short."""
        output_path = run_dir / "thumb.jpg"
        topic = topic_record.get("topic", "")
        summary = topic_record.get("story_summary", "")

        log("THUMBNAIL", f"Formulating thumbnail concept for '{topic}'...")

        # Formulate concept prompt via Brain
        try:
            prompt_text, _, _ = self.brain.generate_text(
                THUMB_PROMPT_TEMPLATE.format(topic=topic, summary=summary)
            )
            prompt = prompt_text.strip().replace('"', '')
        except Exception:
            prompt = f"Cinematic viral YouTube thumbnail for {topic}, intense atmosphere, high contrast, dramatic volumetric lighting, vertical 9:16, photorealistic, no text, no watermark."

        log("THUMBNAIL", f"Thumbnail prompt: {prompt[:120]}...")

        # 1. Try Agnes
        if self.primary.is_configured():
            try:
                log("THUMBNAIL", "Calling Primary Thumbnail Provider: Agnes...")
                retry_with_backoff(
                    lambda: self.primary.generate_image(prompt, output_path),
                    stage="THUMBNAIL",
                    max_retries=2
                )
                self.last_provider_used = "agnes"
                self.fallback_used = False
                log_success("THUMBNAIL", "Agnes thumbnail generation succeeded.")
                return output_path, "agnes", False
            except Exception as e:
                log_warn("THUMBNAIL", f"Agnes image failed ({e}). Switching to thumbnail fallback...")

        # 2. Fallback
        log("FALLBACK", "Generating thumbnail via fallback provider...")
        self.fallback.generate_image(prompt, output_path)
        self.last_provider_used = "fallback"
        self.fallback_used = True
        log_success("THUMBNAIL", "Fallback thumbnail created.")
        return output_path, "fallback", True
