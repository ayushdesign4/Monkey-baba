"""Visual Director: creates Character Bible, Environment Bible, and coherent 9:16 scene prompts."""

from typing import Dict, Any, Tuple
from src.brain.manager import BrainManager
from src.scenes.validator import SceneValidator
from src.utils.logging import log, log_warn, log_success

DIRECTOR_PROMPT = """
You are the Hollywood-caliber Cinematic Director for Monkey-Baba (Vertical YouTube Shorts).
Topic: "{topic}"
Script:
{full_script}

TASK:
1. Define a consistent CHARACTER BIBLE (Name, appearance, face, clothing, palette).
2. Define a consistent ENVIRONMENT BIBLE (Location, atmosphere, architectural style, lighting).
3. Expand the {scene_count} script scenes into detailed visual scene prompts for 9:16 vertical video generation.

STRICT VIDEO PROMPT RULES:
- Every prompt must specify: 9:16 vertical framing, camera movement (slow zoom, pan, tilt, tracking), cinematic volumetric lighting, photorealistic textures.
- Explicitly inject the Character Bible details into every scene with a character.
- Explicitly inject the Environment Bible details into every scene.
- Prompt must end with: "Vertical 9:16, cinematic, photorealistic 8k, hyper-detailed, no text, no watermark, uncompressed."

OUTPUT FORMAT (Respond with STRICT raw JSON only):
{{
  "character_bible": {{
    "name": "...",
    "appearance": "...",
    "clothing": "...",
    "palette": "..."
  }},
  "environment_bible": {{
    "location": "...",
    "lighting": "...",
    "atmosphere": "..."
  }},
  "scenes": [
    {{
      "scene_number": 1,
      "duration_seconds": 6,
      "narration": "...",
      "visual_description": "...",
      "video_prompt": "...",
      "camera": "...",
      "lighting": "...",
      "continuity_notes": "..."
    }}
  ]
}}
"""

class SceneDirector:
    def __init__(self, brain: BrainManager):
        self.brain = brain
        self.validator = SceneValidator()

    def direct_scenes(self, script_data: Dict[str, Any], topic_record: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
        """Generate Character Bible, Environment Bible, and scene-level prompts."""
        topic = topic_record.get("topic", "")
        full_script = script_data.get("full_narration", "")
        base_scenes = script_data.get("scenes", [])
        scene_count = len(base_scenes)

        log("SCENES", f"Directing {scene_count} scenes with Character & Environment consistency...")

        prompt = DIRECTOR_PROMPT.format(
            topic=topic,
            full_script=full_script,
            scene_count=scene_count
        )

        try:
            parsed, provider, fallback_used = self.brain.generate_json(
                prompt,
                system_instruction="You are an expert AI video cinematic prompter specializing in vertical Shorts."
            )
            is_valid, reason = self.validator.validate(parsed)
            if is_valid:
                log_success("SCENES", f"Directed {len(parsed['scenes'])} scenes with consistent bibles.")
                return parsed, fallback_used
            else:
                log_warn("SCENES", f"Scene direction validation warning: {reason}. Merging with base scenes.")
        except Exception as e:
            log_warn("SCENES", f"Brain direction generation failed ({e}). Constructing procedural prompt pipeline.")

        # Procedural fallback direction
        return self._build_procedural_direction(script_data, topic_record), True

    def _build_procedural_direction(self, script_data: Dict[str, Any], topic_record: Dict[str, Any]) -> Dict[str, Any]:
        """Construct guaranteed prompt list with consistent character & environment."""
        topic = topic_record.get("topic", "")
        base_scenes = script_data.get("scenes", [])

        char_bible = {
            "name": "Investigator Alex Vance",
            "appearance": "Weathered 38-year-old explorer, piercing amber eyes, determined jawline, dark disheveled hair",
            "clothing": "Heavy canvas field jacket, utilitarian gear, brass watch",
            "palette": "Earthy charcoal, brass, deep amber"
        }

        env_bible = {
            "location": f"Atmospheric cinematic location relevant to {topic}",
            "lighting": "Chiaroscuro, dramatic volumetric fog, soft warm backlight and cool shadows",
            "atmosphere": "Suspenseful, mysterious, awe-inspiring"
        }

        directed_scenes = []
        for s in base_scenes:
            idx = s.get("scene_number", 1)
            duration = s.get("duration_seconds", 6)
            narration = s.get("narration", "")

            prompt = (
                f"Cinematic vertical shot for {topic}. "
                f"Scene {idx}: {narration}. "
                f"Featuring {char_bible['name']} ({char_bible['appearance']}, wearing {char_bible['clothing']}). "
                f"Setting: {env_bible['location']}, {env_bible['lighting']}, {env_bible['atmosphere']}. "
                f"Smooth slow camera motion, 35mm lens, 9:16 vertical composition, photorealistic, 8k, no text, no watermark."
            )

            directed_scenes.append({
                "scene_number": idx,
                "duration_seconds": duration,
                "narration": narration,
                "visual_description": f"Visual sequence for scene {idx}",
                "video_prompt": prompt,
                "camera": "Slow cinematic tracking",
                "lighting": env_bible["lighting"],
                "continuity_notes": "Preserve Alex Vance clothing and environment lighting tone."
            })

        return {
            "character_bible": char_bible,
            "environment_bible": env_bible,
            "scenes": directed_scenes
        }
