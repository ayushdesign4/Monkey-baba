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

    topic_keywords = extract_keywords(topic)
    title_keywords = extract_keywords(title)
    script_keywords = extract_keywords(script)

    all_scenes_text = " ".join(scene_prompts)
    scenes_keywords = extract_keywords(all_scenes_text)

    # 1. Topic keywords MUST be reflected in either the title, script, or scene prompts
    if topic_keywords:
        combined_content = title_keywords.union(script_keywords).union(scenes_keywords)
        matched = topic_keywords.intersection(combined_content)
        if len(matched) < min_keyword_matches:
            raise StoryConsistencyError(
                f"Story mismatch detected! Topic keywords {topic_keywords} do not match script/title/scenes. "
                f"Topic: '{topic}' vs Title: '{title}'. Matched keywords: {matched}"
            )

    # 2. Title keywords MUST be reflected in the script
    if title_keywords:
        title_in_script = title_keywords.intersection(script_keywords)
        if not title_in_script:
            raise StoryConsistencyError(
                f"Title mismatch detected! Title keywords {title_keywords} have no overlap with script narration. "
                f"Title: '{title}'"
            )

    # 3. Scene prompts MUST reflect script elements
    if script_keywords and scenes_keywords:
        script_in_scenes = script_keywords.intersection(scenes_keywords)
        if len(script_in_scenes) < 2:
            raise StoryConsistencyError(
                f"Scene prompts divergence! Scene prompts have insufficient overlap with narration. "
                f"Matched keywords: {script_in_scenes}"
            )
