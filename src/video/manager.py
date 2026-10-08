"""Video Provider Manager orchestrating Primary (Agnes) and Video Fallback."""

from pathlib import Path
from typing import Dict, Any, List, Tuple
from src.video.agnes import AgnesVideoProvider
from src.video.fallback import FallbackVideoProvider
from src.utils.logging import log, log_warn, log_success
from src.utils.retry import retry_with_backoff

class VideoManager:
    def __init__(self):
        self.primary = AgnesVideoProvider()
        self.fallback = FallbackVideoProvider()
        self.last_provider_used = None
        self.fallback_used = False

    def generate_scene_clips(self, scenes: List[Dict[str, Any]], run_dir: Path) -> Tuple[List[Path], str, bool]:
        """
        Generate MP4 clip for each scene.
        Guarantees all output clips exist, are 9:16, and have audio stripped.
        """
        clips_dir = run_dir / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)

        clip_paths: List[Path] = []
        overall_fallback = False
        provider_name = "agnes"

        for idx, scene in enumerate(scenes, 1):
            scene_num = scene.get("scene_number", idx)
            duration = scene.get("duration_seconds", 6)
            prompt = scene.get("video_prompt", "")
            clip_path = clips_dir / f"scene_{scene_num:03d}.mp4"

            log("VIDEO", f"Generating scene {scene_num}/{len(scenes)} (duration={duration}s)...")

            # Try primary (Agnes)
            generated = False
            if self.primary.is_configured() and not overall_fallback:
                try:
                    retry_with_backoff(
                        lambda: self.primary.generate_clip(prompt, clip_path, duration),
                        stage="VIDEO",
                        max_retries=2
                    )
                    generated = True
                    provider_name = "agnes"
                except Exception as e:
                    log_warn("VIDEO", f"Agnes clip generation failed ({e}). Switching to video fallback...")
                    overall_fallback = True

            # If primary unconfigured or failed, use procedural fallback
            if not generated:
                log("FALLBACK", f"Generating scene {scene_num} via procedural fallback provider...")
                self.fallback.generate_clip(prompt, clip_path, duration)
                overall_fallback = True
                provider_name = "fallback"

            clip_paths.append(clip_path)

        self.last_provider_used = provider_name
        self.fallback_used = overall_fallback
        log_success("VIDEO", f"All {len(clip_paths)} clips generated successfully using provider '{provider_name}'.")
        return clip_paths, provider_name, overall_fallback
