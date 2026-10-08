"""Automatic topic ideation, selection, and history duplicate verification."""

from datetime import datetime
from typing import Dict, Any, Tuple
from src.topic.history import TopicHistory
from src.brain.manager import BrainManager
from src.utils.logging import log, log_warn, log_success

TOPIC_IDEATION_PROMPT = """
You are the Lead Creative Director for Monkey-Baba, an elite viral YouTube Shorts channel.
Generate 5 candidate viral storytelling topics for YouTube Shorts.

Focus on:
1. High-CTR hooks (unsolved historical mysteries, forbidden archaeology, unexplained anomalies, terrifying science).
2. Deep human curiosity and suspense.
3. Visual richness suitable for cinematic video generation.

Respond with a JSON array of 5 objects:
[
  {
    "topic": "Compelling Title",
    "hook": "Opening hook sentence",
    "story_summary": "2-3 sentence plot summary"
  }
]
"""

FALLBACK_TOPICS = [
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
    }
]

class TopicGenerator:
    def __init__(self, brain: BrainManager, history: TopicHistory = None):
        self.brain = brain
        self.history = history or TopicHistory()

    def generate_and_select_topic(self, forced_topic: str = None) -> Tuple[Dict[str, Any], bool]:
        """
        Generate candidate topics, screen for duplicates, select, and persist.
        Returns: (selected_topic_record, was_fallback_used)
        """
        if forced_topic:
            log("TOPIC", f"Using user-specified topic: '{forced_topic}'")
            record = self.history.add_topic(
                topic=forced_topic,
                story_summary="Manually requested topic for execution."
            )
            return record, False

        log("TOPIC", "Generating fresh viral topic candidates via Brain...")

        candidates = []
        fallback_used = False

        try:
            parsed, provider, fallback_used = self.brain.generate_json(
                TOPIC_IDEATION_PROMPT,
                system_instruction="You are an expert short-form viral storytelling producer."
            )
            if isinstance(parsed, list):
                candidates = parsed
            elif isinstance(parsed, dict) and "candidates" in parsed:
                candidates = parsed["candidates"]
        except Exception as e:
            log_warn("TOPIC", f"Brain topic generation failed ({e}). Using curated fallback reservoir.")
            candidates = FALLBACK_TOPICS
            fallback_used = True

        # Duplicate screening loop
        selected = None
        for candidate in candidates:
            topic_title = candidate.get("topic", "")
            summary = candidate.get("story_summary", "")

            is_dup, reason = self.history.is_duplicate(topic_title, summary)
            if is_dup:
                log_warn("TOPIC", f"Rejecting candidate '{topic_title}': {reason}")
                continue
            
            selected = candidate
            break

        if not selected:
            log_warn("TOPIC", "All candidates matched duplicates! Generating unique timestamped topic.")
            selected = {
                "topic": f"Unsolved Paradox of Time: Case {datetime.utcnow().strftime('%Y%m%d%H%M')}",
                "story_summary": "A deep dive into quantum timeline anomalies and strange historical records."
            }

        topic_record = self.history.add_topic(
            topic=selected.get("topic"),
            story_summary=selected.get("story_summary", selected.get("hook", ""))
        )
        log_success("TOPIC", f"Selected Topic: '{topic_record['topic']}'")
        return topic_record, fallback_used
