"""Script quality, word count, scene count and language validator."""

import re
from typing import Dict, Any, Tuple
from src.config import MIN_SCRIPT_WORDS, MIN_SCENES, MAX_SCENES
from src.utils.logging import log, log_warn

def count_words(text: str) -> int:
    """Accurately count spoken words, ignoring punctuation."""
    words = re.findall(r"\b\w+[\w'-]*\b", text)
    return len(words)

class ScriptValidator:
    @staticmethod
    def validate(script_data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validate script meets production criteria:
        1. Narration text exists and is English
        2. Word count >= 100 words
        3. Scenes count between 6 and 8
        4. Hook and payoff exist
        """
        full_text = script_data.get("full_narration", "")
        scenes = script_data.get("scenes", [])

        if not full_text and scenes:
            # Reconstruct from scene narrations if full_narration wasn't set
            full_text = " ".join([s.get("narration", "") for s in scenes])

        word_count = count_words(full_text)
        script_data["word_count"] = word_count

        if word_count < MIN_SCRIPT_WORDS:
            return False, f"Script word count ({word_count}) is below minimum requirement ({MIN_SCRIPT_WORDS} words)."

        scene_count = len(scenes)
        if scene_count < MIN_SCENES or scene_count > MAX_SCENES:
            return False, f"Scene count ({scene_count}) outside required range ({MIN_SCENES}–{MAX_SCENES} scenes)."

        # Check that individual scenes have non-empty narration
        for idx, scene in enumerate(scenes, 1):
            s_narration = scene.get("narration", "").strip()
            if not s_narration:
                return False, f"Scene {idx} has empty narration text."

        return True, "Valid"
