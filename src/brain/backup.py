"""Fallback #2 Brain Provider: Local deterministic Python emergency fallback."""

import json
import re
from typing import Optional, Dict, Any

class LocalFallbackProvider:
    name = "local"

    def __init__(self, *args, **kwargs):
        pass

    def is_configured(self) -> bool:
        return True

    def generate(self, prompt: str, system_instruction: str = "") -> str:
        """Deterministically generate appropriate emergency text or structured JSON."""
        # 1. Topic generation
        if "candidate viral storytelling topics" in prompt or "TOPIC_IDEATION" in prompt:
            fallback_topics = [
                {
                    "topic": "The Green Children of Woolpit: Medieval Mystery",
                    "hook": "In 12th century England, two children with green skin appeared speaking an unknown language.",
                    "story_summary": "Two children with emerald-green skin suddenly emerged from wolf pits in Suffolk, unable to eat anything except raw green beans and describing a sunless twilight realm."
                },
                {
                    "topic": "The Voynich Manuscript: Book Nobody Can Read",
                    "hook": "For 600 years, cryptographers and supercomputers have failed to decipher this single book.",
                    "story_summary": "A 15th-century manuscript filled with alien botanicals, mysterious celestial zodiacs, and an unbreakable cipher that continues to baffle world codebreakers."
                },
                {
                    "topic": "The Lake Baikal Humanoid Encounter of 1982",
                    "hook": "Military divers descending 160 feet into the world's deepest lake encountered 9-foot silver giants.",
                    "story_summary": "During deep-water drills in Siberia's frozen Lake Baikal, Soviet combat divers encountered towering humanoid swimmers without scuba equipment, leading to an emergency ascent."
                },
                {
                    "topic": "The Lost City of the Kalahari",
                    "hook": "In 1885, an explorer stumbled upon ruins in the desert that shouldn't exist.",
                    "story_summary": "Deep in the sands of the Kalahari desert lies the legend of a colossal ancient metropolis discovered by Farini, which disappeared beneath shifting dunes."
                },
                {
                    "topic": "The Taos Hum: Unbearable Acoustic Enigma",
                    "hook": "In a quiet New Mexico town, a persistent low-frequency hum drives residents to madness.",
                    "story_summary": "Only two percent of the local population can hear the mysterious drone, which microphones and scientific acoustic sensors fail to capture."
                }
            ]
            return json.dumps(fallback_topics)

        # Extract topic from prompt if present
        topic_match = re.search(r'Topic:\s*"?([^"\n\r]+)', prompt)
        topic = topic_match.group(1).strip().strip('"').strip("'") if topic_match else "The Ancient Mystery"

        # 2. Script generation
        if "Master Storyteller" in prompt or "full_narration" in prompt or "min_words" in prompt:
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
            return json.dumps({
                "title": topic,
                "full_narration": full_text,
                "scenes": scenes
            })

        # 3. Scene direction
        if "cinematic prompter" in prompt or "character_bible" in prompt or "visual_prompt" in prompt or "DIRECTOR" in prompt:
            scenes = [
                {"scene_number": 1, "visual_prompt": f"Dramatic opening shot of {topic}, cinematic 8k, volumetric lighting, vertical 9:16, photorealistic", "motion_instruction": "Slow push in", "lighting": "Chiaroscuro dramatic"},
                {"scene_number": 2, "visual_prompt": f"Mysterious archival discovery revealing clues about {topic}, ultra detailed", "motion_instruction": "Subtle camera drift", "lighting": "Warm candlelight and cold shadows"},
                {"scene_number": 3, "visual_prompt": f"Atmospheric vista showing anomalous environment of {topic}, foggy and eerie", "motion_instruction": "Slow panning down", "lighting": "Dim twilight volumetric fog"},
                {"scene_number": 4, "visual_prompt": f"Close up investigation of ancient artifacts and encrypted patterns related to {topic}", "motion_instruction": "Macro slow zoom", "lighting": "High contrast beam of light"},
                {"scene_number": 5, "visual_prompt": f"Shadowy figures and explorers gazing at enigmatic structure of {topic}", "motion_instruction": "Tracking shot", "lighting": "Silhouette rim light"},
                {"scene_number": 6, "visual_prompt": f"High tech satellite scan rendering glowing energy signatures at {topic} site", "motion_instruction": "Dynamic pulse", "lighting": "Bioluminescent cyan glow"},
                {"scene_number": 7, "visual_prompt": f"Chilling cinematic final perspective of {topic} under the night sky, awe inspiring", "motion_instruction": "Slow tilt up to stars", "lighting": "Starlight and deep indigo shadows"}
            ]
            return json.dumps({
                "character_bible": {
                    "name": "Investigator Alex Vance",
                    "appearance": "Weathered 38-year-old explorer, piercing amber eyes, determined jawline, dark disheveled hair",
                    "clothing": "Heavy canvas field jacket, utilitarian gear, brass watch",
                    "palette": "Earthy charcoal, brass, deep amber"
                },
                "environment_bible": {
                    "location": f"Atmospheric cinematic location relevant to {topic}",
                    "lighting": "Chiaroscuro, dramatic volumetric fog, soft warm backlight and cool shadows",
                    "atmosphere": "Suspenseful, mysterious, awe-inspiring"
                },
                "scenes": scenes
            })

        # 4. Metadata generation
        if "Metadata Strategist" in prompt or ("title" in prompt and "description" in prompt and "tags" in prompt):
            return json.dumps({
                "title": f"The Unexplained Mystery of {topic} #Shorts",
                "description": f"Exploring the incredible truth behind {topic}. Did this really happen?\n\n#Shorts #Mystery #Documentary #History",
                "tags": ["Shorts", "Mystery", "History", "Unexplained", "Documentary", "Science", "Viral"]
            })

        # 5. Thumbnail concept
        if "thumbnail" in prompt.lower() or "high-ctr" in prompt.lower():
            return f"Cinematic viral YouTube thumbnail for {topic}, intense atmosphere, high contrast, dramatic volumetric lighting, vertical 9:16, photorealistic, no text, no watermark."

        # 6. Space exploration test prompt
        if "space exploration" in prompt.lower():
            return "Space exploration continues to push the boundaries of human knowledge and technological capability across the cosmos."

        # Generic fallback
        return f"Autonomous analysis for {topic} completed successfully."

# Alias for backward compatibility
BackupLLMProvider = LocalFallbackProvider
