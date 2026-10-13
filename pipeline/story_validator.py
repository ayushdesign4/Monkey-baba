"""Story consistency validation across topic, title, script, and scene prompts.

Ensures that:
1. Every stage of the pipeline describes the same selected story.
2. The title, script narration, and scene prompts are thematically and entity-aligned with the selected topic.
3. Rejects runs where the title/script diverge from the reserved topic.
"""
from __future__ import annotations

import re


class StoryConsistencyError(ValueError):
    """Raised when story components describe conflicting or mismatched premises."""
    pass


# Common stopwords to ignore during keyword extraction
STOPWORDS = {
    "a", "an", "the", "in", "on", "at", "to", "for", "of", "with", "by", "from",
    "up", "about", "into", "over", "after", "is", "are", "was", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "and", "but",
    "or", "as", "if", "when", "than", "because", "while", "where", "how", "all",
    "any", "both", "each", "few", "more", "most", "some", "such", "no", "nor",
    "not", "only", "own", "same", "so", "than", "too", "very", "can", "will",
    "just", "don", "should", "now", "even", "during", "that", "this", "these",
    "those", "what", "which", "who", "whom", "their", "there", "then", "them",
    "your", "yours", "our", "ours", "its", "it", "his", "her", "hers", "my",
    "shorts", "horror", "story", "stories", "scary",
    "ancient", "old", "dark", "deep", "mysterious", "strange", "cold", "unexplained",
    "sudden", "small", "tall", "little", "long", "one", "two", "three", "behind",
    "inside", "outside", "every", "first", "last", "never", "always",
}


def extract_keywords(text: str) -> set[str]:
    """Extract significant lowercase keywords from text."""
    words = re.findall(r"\b[a-zA-Z]{3,}\b", (text or "").lower())
    return {w for w in words if w not in STOPWORDS}


def validate_story_consistency(
    topic: str,
    title: str,
    script: str,
    scene_prompts: list[str],
    *,
    min_keyword_matches: int = 1,
) -> None:
    """Validate that topic, title, script narration, and scene prompts align.
    Raises StoryConsistencyError if a mismatch is detected.
    """
    if not topic.strip():
        raise StoryConsistencyError("Selected topic is empty")
    if not title.strip():
        raise StoryConsistencyError("Story title is empty")
    if not script.strip():
        raise StoryConsistencyError("Story script narration is empty")
    if not scene_prompts:
        raise StoryConsistencyError("Scene prompts list is empty")

    from pipeline.recovery import semantic_premise_match

    # Primary check: Semantic and thematic premise relevance across topic, title, script, and scenes
    is_consistent = semantic_premise_match(topic, title, script, scene_prompts)
    if not is_consistent:
        raise StoryConsistencyError(
            f"Story mismatch detected! Story premise diverges from selected topic '{topic}'. "
            f"Topic: '{topic}' vs Title: '{title}'."
        )
