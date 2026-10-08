"""Script generation and automated repair engine."""

from typing import Dict, Any, Tuple
from src.brain.manager import BrainManager
from src.script.validator import ScriptValidator, count_words
from src.config import MIN_SCRIPT_WORDS, MIN_SCENES, MAX_SCENES
from src.utils.logging import log, log_warn, log_success

SCRIPT_PROMPT_TEMPLATE = """
You are the Master Storyteller for Monkey-Baba YouTube Shorts.
Topic: "{topic}"
Context: "{story_summary}"

Generate a gripping, fast-paced vertical Short script that meets these STRICT constraints:
1. LANGUAGE: English only.
2. SPOKEN WORD COUNT: MUST BE AT LEAST 115 WORDS (minimum {min_words} words). Speakable in 40-55 seconds.
3. SCENES: Exactly 6 to 8 visual scenes.
4. NARRATION: Only words meant to be spoken aloud by TTS narrator. NO bracketed directions, sound effects, or camera cues in narration text.
5. STRUCTURE:
   - Scene 1: Instant irresistible hook (First 3 seconds).
   - Scenes 2-5: Rapid escalation, mystery deepening, concrete vivid details.
   - Scene 6-7: Climax / revelation.
   - Scene 8: Chilling payoff or final question that forces re-watching.

OUTPUT FORMAT (Respond with STRICT raw JSON only):
{{
  "title": "Working Hook Title",
  "full_narration": "Full combined narration here...",
  "scenes": [
    {{
      "scene_number": 1,
      "narration": "Narration for scene 1...",
      "duration_seconds": 6
    }}
  ]
}}
"""

class ScriptGenerator:
    def __init__(self, brain: BrainManager):
        self.brain = brain
        self.validator = ScriptValidator()

    def generate_script(self, topic_record: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
        """Generate and validate a script, running repair iterations if needed."""
        topic = topic_record.get("topic", "")
        summary = topic_record.get("story_summary", "")

        log("SCRIPT", f"Generating script for '{topic}' (target >= {MIN_SCRIPT_WORDS} words)...")

        prompt = SCRIPT_PROMPT_TEMPLATE.format(
            topic=topic,
            story_summary=summary,
            min_words=MIN_SCRIPT_WORDS
        )

        try:
            for attempt in range(1, 4):
                parsed, provider, fallback_used = self.brain.generate_json(
                    prompt,
                    system_instruction="You are an award-winning YouTube Shorts narrative director. Adhere strictly to word count requirements."
                )

                is_valid, reason = self.validator.validate(parsed)
                if is_valid:
                    log_success("SCRIPT", f"Script validated successfully! ({parsed['word_count']} words, {len(parsed['scenes'])} scenes)")
                    return parsed, fallback_used

                log_warn("SCRIPT", f"Script validation failed on attempt {attempt}: {reason}. Initiating repair...")
                prompt = (
                    f"The previous script failed validation: {reason}\n"
                    f"Please regenerate the script for topic '{topic}'. "
                    f"CRITICAL: The spoken text MUST be longer than {MIN_SCRIPT_WORDS + 15} words and have exactly 6 to 8 scenes."
                )
        except Exception as e:
            log_warn("SCRIPT", f"Brain script generation failed ({e}). Using guaranteed compliant emergency script.")

        emergency_script = self._build_emergency_script(topic, summary)
        return emergency_script, True

    def _build_emergency_script(self, topic: str, summary: str) -> Dict[str, Any]:
        """Guaranteed compliant fallback script exceeding 100 words with 7 scenes."""
        scenes = [
            {"scene_number": 1, "duration_seconds": 6, "narration": f"What if history's greatest mystery was kept hidden right beneath our feet? This is the shocking truth about {topic}."},
            {"scene_number": 2, "duration_seconds": 6, "narration": "It all started when strange anomalies were first reported in remote territory, leaving seasoned researchers completely baffled."},
            {"scene_number": 3, "duration_seconds": 7, "narration": "Eyewitnesses described phenomena that defied every known law of modern physics, yet official documents immediately vanished into classified archives."},
            {"scene_number": 4, "duration_seconds": 7, "narration": "Deep analysis revealed encrypted patterns and structures that simply should not have existed for thousands of years."},
            {"scene_number": 5, "duration_seconds": 7, "narration": "Every expedition sent to uncover the core anomaly either returned empty handed or refused to speak about what they witnessed in the dark."},
            {"scene_number": 6, "duration_seconds": 7, "narration": "Modern satellite scans now confirm that an unidentified energetic signature continues to emanate from the exact epicenter."},
            {"scene_number": 7, "duration_seconds": 7, "narration": "The evidence cannot be ignored any longer. If this discovery is true, everything we believe about our world changes forever. What do you think happened?"}
        ]
        full_text = " ".join([s["narration"] for s in scenes])
        return {
            "title": topic,
            "full_narration": full_text,
            "word_count": count_words(full_text),
            "scenes": scenes
        }
