"""Scene structure and prompt validator."""

from typing import Dict, Any, List, Tuple
from src.config import MIN_SCENES, MAX_SCENES

class SceneValidator:
    @staticmethod
    def validate(scenes_data: Dict[str, Any]) -> Tuple[bool, str]:
        scenes = scenes_data.get("scenes", [])
        if not (MIN_SCENES <= len(scenes) <= MAX_SCENES):
            return False, f"Expected {MIN_SCENES}–{MAX_SCENES} scenes, got {len(scenes)}."

        for idx, scene in enumerate(scenes, 1):
            if not scene.get("video_prompt"):
                return False, f"Scene {idx} missing 'video_prompt'."
            if not scene.get("narration"):
                return False, f"Scene {idx} missing 'narration'."
            if scene.get("duration_seconds", 0) <= 0:
                scene["duration_seconds"] = 6

        return True, "Valid"
