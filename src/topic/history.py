"""Topic history management and semantic similarity duplicate protection."""

import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple
from src.config import TOPICS_FILE
from src.utils.files import read_json, write_json
from src.utils.logging import log

def _tokenize(text: str) -> set:
    """Extract normalized alphanumeric words for token matching."""
    words = re.findall(r"\b[a-zA-Z0-9]{3,}\b", text.lower())
    stopwords = {"the", "and", "that", "this", "with", "from", "for", "have", "what", "where", "when", "into"}
    return {w for w in words if w not in stopwords}

def calculate_similarity(text1: str, text2: str) -> float:
    """Calculate word token overlap (Jaccard similarity)."""
    tokens1 = _tokenize(text1)
    tokens2 = _tokenize(text2)
    if not tokens1 or not tokens2:
        return 0.0
    intersection = tokens1.intersection(tokens2)
    union = tokens1.union(tokens2)
    return len(intersection) / len(union)

class TopicHistory:
    def __init__(self, topics_path: Path = TOPICS_FILE):
        self.path = topics_path
        self._load()

    def _load(self):
        self.topics: List[Dict[str, Any]] = read_json(self.path, default=[])

    def save(self):
        write_json(self.path, self.topics)

    def is_duplicate(self, candidate_topic: str, candidate_summary: str = "", threshold: float = 0.35) -> Tuple[bool, str]:
        """Check if candidate topic is too similar to any historical topic."""
        clean_candidate = candidate_topic.strip().lower()

        for item in self.topics:
            existing_topic = item.get("topic", "").strip().lower()
            existing_summary = item.get("story_summary", "")

            # Exact match check
            if clean_candidate == existing_topic:
                return True, f"Exact match with '{item.get('topic')}'"

            # Title similarity
            title_sim = calculate_similarity(candidate_topic, existing_topic)
            if title_sim >= threshold:
                return True, f"Title similarity {title_sim:.2f} >= {threshold} with '{item.get('topic')}'"

            # Story summary similarity
            if candidate_summary and existing_summary:
                summary_sim = calculate_similarity(candidate_summary, existing_summary)
                if summary_sim >= 0.45:
                    return True, f"Summary similarity {summary_sim:.2f} with '{item.get('topic')}'"

        return False, ""

    def add_topic(self, topic: str, story_summary: str, topic_id: str = None) -> Dict[str, Any]:
        """Record and persist a new topic."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if not topic_id:
            topic_id = f"topic-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"

        record = {
            "topic_id": topic_id,
            "topic": topic,
            "story_summary": story_summary,
            "date": today,
            "video_id": None,
            "status": "selected"
        }
        self.topics.append(record)
        self.save()
        log("TOPIC", f"Persisted topic record: {topic_id} ('{topic}')")
        return record

    def update_status(self, topic_id: str, status: str, video_id: str = None):
        """Update topic upload status."""
        for item in self.topics:
            if item.get("topic_id") == topic_id:
                item["status"] = status
                if video_id:
                    item["video_id"] = video_id
                self.save()
                break
