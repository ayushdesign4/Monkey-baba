"""Metadata Generator for YouTube Shorts."""

from typing import Dict, Any, Tuple
from src.brain.manager import BrainManager
from src.utils.logging import log, log_warn, log_success

METADATA_PROMPT = """
You are the Growth & Metadata Strategist for Monkey-Baba YouTube Shorts.
Topic: "{topic}"
Script:
{narration}

Generate optimized YouTube Shorts metadata:
1. TITLE: High CTR, curious, captivating, natural English, under 70 characters. Include #Shorts.
2. DESCRIPTION: 2-3 engaging summary sentences, followed by relevant hashtags (#Shorts #Mystery #Documentary).
3. TAGS: Array of 8-12 search-optimized keywords.

OUTPUT FORMAT (Respond with STRICT raw JSON only):
{{
  "title": "Title Here #Shorts",
  "description": "Description Here...",
  "tags": ["Shorts", "Mystery", "History", "..."]
}}
"""

class MetadataGenerator:
    def __init__(self, brain: BrainManager):
        self.brain = brain

    def generate_metadata(self, topic_record: Dict[str, Any], script_data: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
        """Generate title, description, and tags."""
        topic = topic_record.get("topic", "")
        narration = script_data.get("full_narration", "")

        log("METADATA", f"Generating optimized YouTube metadata for '{topic}'...")

        try:
            parsed, provider, fallback_used = self.brain.generate_json(
                METADATA_PROMPT.format(topic=topic, narration=narration[:1000])
            )
            title = parsed.get("title", f"{topic} #Shorts")
            if "#shorts" not in title.lower():
                title = f"{title} #Shorts"
            parsed["title"] = title
            log_success("METADATA", f"Generated Title: '{title}'")
            return parsed, fallback_used
        except Exception as e:
            log_warn("METADATA", f"Brain metadata generation failed: {e}. Using deterministic format.")
            return {
                "title": f"The Unexplained Mystery of {topic} #Shorts",
                "description": f"{script_data.get('full_narration', '')[:300]}...\n\n#Shorts #Mystery #History #Unknown",
                "tags": ["Shorts", "Mystery", "History", "Unexplained", "Viral"]
            }, True
