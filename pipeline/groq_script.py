"""Groq (OpenAI-compatible) — generate Short script + image prompts as JSON.

Supports two modes:
  • Single-language preset (legacy): returns full_narration, youtube_title, etc.
  • Multi-variant preset (bilingual): returns image_prompts once + variants[lang] = {title, desc, narration}.
"""
from __future__ import annotations

import json
import os
from typing import Any

from groq import Groq

from pipeline.channel_presets import ChannelPreset
from pipeline.story_history import history_prompt_block

GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")


# ── Language-specific word-count guidance ──────────────────────────────
LANG_WORD_TARGETS = {
    "en": (
        120,
        155,
        "120-155 English words for variants.en.full_narration (~40-50 sec); "
        "add transitions, examples, and a closing takeaway — NOT a bullet list",
    ),
    "hi": (
        135,
        170,
        "135-170 Devanagari Hindi words — aim ~150 (~55-70 sec); full sentences, not headlines",
    ),
}

# Bilingual presets override per variant; these are fallbacks only.
DEFAULT_MIN_WORDS = {"hi": 80, "en": 80}


def _lang_label(lang: str) -> str:
    return {"en": "English", "hi": "Hindi (Devanagari script)"}.get(lang, lang)


FALLBACK_HORROR_STORIES = [
    {
        "youtube_title": "The Whispering Radiator in Room 404 #Shorts",
        "youtube_description": "A college student discovers an antique radiator tapping back in the dead of night. What lies beneath the wall? #HorrorShorts #ScaryStories #Shorts",
        "full_narration": (
            "Every winter night at three in the morning, the old iron radiator in room four hundred and four "
            "began to clank in rhythmic bursts. At first, the college freshman thought it was just trapped air "
            "inside the rusted heating pipes. But when he tapped back three times with his room key, the radiator "
            "paused for five seconds and tapped back four distinct beats. He leaned his ear against the metal grate "
            "and froze. A breathless voice whispered his exact childhood nickname, a name nobody in this city "
            "had ever known. Terrified, he unscrewed the maintenance vent beneath the pipe. Tucked inside the "
            "darkness sat an antique tape recorder with fresh batteries, humming softly in the silence. But when he "
            "pressed rewind, the recording wasn't coming from the machine. It was coming from inside the wall."
        ),
        "image_prompts": [
            "Dimly lit college dorm room at 3 AM with an antique iron radiator casting long eerie shadows on wooden floor, 9:16 vertical composition",
            "A nervous college student in a dark room tapping three times on a rusted radiator pipe with a metal key",
            "Extreme cinematic close-up of a student leaning his ear against a dark cast iron radiator grate with wide fearful eyes",
            "Student crouching on the floor with a flashlight, unscrewing a dusty ventilation panel beneath the radiator",
            "Inside the dark brick wall cavity, an antique tape recorder with glowing red indicator sitting among ancient scratches",
            "Terrified young man dropping his flashlight as the walls appear to vibrate with unseen mechanical whispers",
        ],
    },
    {
        "youtube_title": "The Antique Mirror That Blinks Late #Shorts",
        "youtube_description": "She found an ornate mirror in a thrift shop, but her reflection wouldn't move when she moved. #HorrorShorts #ScaryStories #Shorts",
        "full_narration": (
            "In the corner of a dusty antique shop, Maya noticed a tall gilded mirror with an ornate mahogany frame. "
            "When she smiled, her reflection smiled back normally. But when she blinked, her reflection stared back "
            "with wide, unblinking eyes for three full seconds before finally mirroring her blink. Shivering, she reached "
            "out her hand and touched the cold glass. Her reflection didn't move its arm at all. Instead, the figure "
            "in the glass pressed both hands against the inner surface, leaving pale condensation prints that fogged "
            "from the inside out. Maya stepped backward, but the glass cracked in a single spiderweb fracture right "
            "where her forehead had been. On the wooden backing behind the mirror, carved deeply into the mahogany, "
            "was a frantic message dated seventy years ago: do not look away, or it climbs through."
        ),
        "image_prompts": [
            "Dusty antique shop filled with eerie forgotten relics, illuminated by cold moonlight streaming through tall windows, 9:16 vertical",
            "Young woman standing before a tall ornate gilded mirror in the dim shop, looking closely at her reflection",
            "Subtle uncanny close-up of the mirror where the reflection remains unblinking while the woman blinks, chilling tension",
            "The woman trembling as she touches the mirror surface while her reflection presses hands against the glass from inside",
            "Pale handprints fogging the inner glass of the antique mirror from the inside out in supernatural mist",
            "The mirror glass cracking in a sharp spiderweb fracture as the woman recoils in horror into the shadowed room",
        ],
    },
    {
        "youtube_title": "The Midnight Radio Station That Knows You #Shorts",
        "youtube_description": "Driving through a storm, his car radio tuned to a frequency that narrated his exact moves. #HorrorShorts #ScaryStories #Shorts",
        "full_narration": (
            "Driving alone through a mountain storm past midnight, Liam turned his car stereo to search for weather alerts. "
            "The scan dial clicked through static until it locked onto an unlisted frequency broadcasting a calm, monotone voice. "
            "The announcer wasn't reporting the storm; he was describing what Liam was doing in real time. Turn on your headlights, "
            "Liam. Check your rearview mirror, Liam. Your hands are trembling on the steering wheel. Panicking, Liam smashed "
            "the power button to turn off the radio, but the speaker kept talking without power. The voice whispered that "
            "someone was sitting in the backseat directly behind him, ducked low beneath the headrest. Liam slowly adjusted "
            "his mirror toward the back seat. Two glowing amber eyes reflected in the glass, and a cold hand touched the back of his neck."
        ),
        "image_prompts": [
            "Rain-swept dark mountain highway at midnight viewed from inside a lonely car with headlights cutting through heavy fog, 9:16 vertical",
            "Close-up of a vintage car dashboard stereo dial glowing eerie green on an unlisted frequency in the storm",
            "Driver with trembling hands gripping the steering wheel as lightning illuminates his anxious face",
            "The car radio screen completely powered off and dark while sound waves visibly vibrate the speaker grille",
            "Close-up of the rearview mirror showing the dark backseat where two faint amber eyes reflect in the shadow",
            "A pale shadowy hand emerging from the dark backseat reaching toward the driver's shoulder in the gloom",
        ],
    },
    {
        "youtube_title": "The Ghost Train on Abandoned Track 4 #Shorts",
        "youtube_description": "A subway worker encounters an unlisted train that has not run in forty years. #HorrorShorts #ScaryStories #Shorts",
        "full_narration": (
            "Commuter transit worker Daniel was checking track signals on the abandoned lower platform when the rusty iron rails "
            "began to vibrate violently. A silver passenger train with blacked-out windows ground to a screeching halt along "
            "the platform, though the line had been shut down for over forty years. As the center doors slid open with a mechanical hiss, "
            "warm air smelling of burning copper rushed out. Daniel shone his flashlight into the empty car and spotted rows "
            "of mannequins dressed in nineteen-eighties commuter coats. As he took one cautious step closer, every plastic head "
            "inside the car snapped sideways to stare directly into his beam. The subway doors slammed shut behind him before "
            "he could pull his boot back, and the emergency train horn wailed as it accelerated into the dark tunnel."
        ),
        "image_prompts": [
            "Decaying underground subway platform with rusted tracks and flickering fluorescent lights, 9:16 vertical composition",
            "A vintage silver train with blacked-out windows emerging from a pitch-black tunnel onto the abandoned platform",
            "Flashlight beam illuminating the open doors of the train car smelling of ancient electrical sparks",
            "Rows of faceless mannequin figures dressed in vintage overcoats sitting motionless in the eerie train car",
            "Every mannequin head simultaneously turning toward the camera with hollow painted expressions under flashlight glare",
            "The train doors snapping shut as the subway car hurtles into the abyss of the underground tunnel",
        ],
    },
    {
        "youtube_title": "The Forgotten Book in the University Archive #Shorts",
        "youtube_description": "An archivist finds a hidden room and a journal describing her exact actions in real-time. #HorrorShorts #ScaryStories #Shorts",
        "full_narration": (
            "While cataloging donations in the university library basement, student archivist Elena found a brass key "
            "taped beneath an antique card catalog. The key opened a heavy oak door marked Private Collection that was "
            "absent from every official floor plan. Inside sat a single mahogany reading desk with a bound leather journal "
            "opened to today's date. In fresh black ink, the page recorded Elena's arrival time, the black sweater she wore, "
            "and the trembling sound of her footsteps crossing the rug. Horrified, she turned to the next line, which read: "
            "Elena hears the door lock behind her, but does not yet realize the shadow under the desk is breathing. As the heavy "
            "lock clicked shut across the room, she looked down and saw two pale fingers curling over the edge of the wood."
        ),
        "image_prompts": [
            "Cavernous university basement library with towering wooden shelves and dust motes dancing in dim light, 9:16 vertical",
            "A young woman in a black sweater holding a heavy brass key next to a hidden reinforced oak door",
            "Dusty secret archive room with a single mahogany desk lit by a green banker lamp in the darkness",
            "Close-up of an open leather-bound book with fresh handwritten calligraphy describing the woman's exact clothes",
            "The heavy wooden door in the background clicking shut with iron deadbolts sliding into place",
            "Cinematic low-angle shot beneath the antique mahogany desk showing pale fingers emerging from the deep shadow",
        ],
    },
]


def generate_local_fallback(
    preset: ChannelPreset,
    *,
    topic_hint: str | None = None,
) -> dict[str, Any]:
    """Deterministic, keyless local emergency fallback generator.
    Guarantees >=100 words script, 6 scenes in 9:16, title, description.
    """
    import hashlib

    # Pick a deterministic story index using hash of topic_hint or time
    seed = (topic_hint or preset.get("id") or "horror").strip().lower()
    idx = int(hashlib.sha256(seed.encode()).hexdigest(), 16) % len(FALLBACK_HORROR_STORIES)
    story = FALLBACK_HORROR_STORIES[idx].copy()

    # If the preset has variants (e.g. multi-variant), build variants structure
    variants = preset.get("variants") or []
    if variants:
        v_dict = {}
        for v in variants:
            lang = v["lang"]
            v_dict[lang] = {
                "youtube_title": story["youtube_title"],
                "youtube_description": story["youtube_description"],
                "full_narration": story["full_narration"],
            }
        return {
            "image_prompts": story["image_prompts"],
            "variants": v_dict,
        }

    return story


def generate_short_pack(
    preset: ChannelPreset,
    *,
    topic_hint: str | None = None,
    channel_id: str | None = None,
) -> dict[str, Any]:
    topic_hint = (topic_hint or os.environ.get("SHORT_TOPIC", "")).strip()

    user = (
        f"Channel style: {preset['label']}.\n"
        f"Create ONE YouTube Short.\n"
    )
    if topic_hint:
        user += f"Topic idea from creator: {topic_hint}\n"

    if channel_id:
        anti_repeat = history_prompt_block(channel_id)
        if anti_repeat:
            user += anti_repeat

    n = preset["segment_count"]
    variants = preset.get("variants") or []

    # Priority: Groq LLM -> deterministic local emergency fallback
    if os.environ.get("GROQ_API_KEY", "").strip():
        try:
            if variants:
                return _generate_multivariant(preset, user, n, variants)
            return _generate_single(preset, user, n)
        except Exception as exc:
            print(f"[WARN] Groq generation failed ({type(exc).__name__}: {exc}). Switching to deterministic local fallback.")
    else:
        print("[INFO] GROQ_API_KEY not set. Using deterministic local Python emergency fallback.")

    return generate_local_fallback(preset, topic_hint=topic_hint)




# ─────────────────────────────────────────────────────────────────────────
# Single-language path (backward compat for ghost_stories, school_story, etc.)
# ─────────────────────────────────────────────────────────────────────────
def _generate_single(preset: ChannelPreset, user: str, n: int) -> dict[str, Any]:
    language = (preset.get("language") or "en").lower()
    lo, hi, blurb = LANG_WORD_TARGETS.get(language, LANG_WORD_TARGETS["en"])

    if language == "hi":
        narration_rule = (
            '"full_narration": "COMPLETE narration as ONE continuous paragraph in Devanagari Hindi. '
            f'This is what the voice will read aloud. MUST be {blurb}. '
            'Natural spoken Hindi — no segment markers, no numbering, no English transliteration."'
        )
        strict_extra = (
            "- LANGUAGE: full_narration, youtube_title, and youtube_description MUST be in Devanagari Hindi.\n"
            "- image_prompts MUST be in ENGLISH (the image model does not understand Hindi).\n"
            f"- WORD COUNT: full_narration MUST contain {lo}-{hi} Hindi words.\n"
        )
    else:
        narration_rule = (
            '"full_narration": "COMPLETE story/script as one continuous paragraph. This is what the voice will read. '
            f'Must be {blurb}. Natural narration — no segment breaks, no numbering."'
        )
        strict_extra = f"- full_narration is ONE continuous paragraph, {lo}-{hi} English words.\n"

    user += f"""
Return ONLY valid JSON with this shape:
{{
  "youtube_title": "short catchy title, under 90 chars, no hashtags",
  "youtube_description": "2-3 sentences plus optional #Shorts at end",
  {narration_rule},
  "image_prompts": [
    "visual description for image 1: setting, subject, action. No style words. No text in image.",
    "visual description for image 2...",
    "..."
  ]
}}

STRICT RULES:
{strict_extra}- "image_prompts" array MUST have exactly {n} entries.
- Each image_prompt matches a different moment/beat in order.
- Image prompts are just visuals — no narration text, no style words, no quotes.
- The narration must flow naturally as one spoken piece (no "segment 1", "segment 2" etc).
"""

    max_attempts = 3
    last_err = ""
    for attempt in range(max_attempts):
        extra = ""
        if attempt > 0:
            extra = (
                f"\n\nCRITICAL: Previous attempt failed validation: {last_err}.\n"
                "Please rewrite the narration to be longer and more detailed. "
                f"Aim for {lo}-{hi} words. Add more descriptive sentences to each beat.\n"
            )

        temp = 0.85 if attempt < 2 else 0.45
        data = _call_groq(preset, user + extra, temperature=temp)

        try:
            narration = data.get("full_narration", "").strip()
            if not narration:
                raise ValueError("Missing full_narration")

            prompts = data.get("image_prompts")
            if not isinstance(prompts, list) or len(prompts) != n:
                raise ValueError(f"Expected {n} image_prompts, got {len(prompts or [])}")
            for i, p in enumerate(prompts):
                if not isinstance(p, str) or not p.strip():
                    raise ValueError(f"image_prompt {i} is empty")

            word_count = len(narration.split())
            min_words = preset.get("min_words", DEFAULT_MIN_WORDS.get(language, 80))
            if word_count < min_words:
                raise ValueError(
                    f"Narration too short ({word_count} words, expected ≥ {min_words} for {language})"
                )

            return data
        except ValueError as e:
            last_err = str(e)
            if attempt == max_attempts - 1:
                raise

    # Fallback (should be unreachable due to raise above)
    return data


# ─────────────────────────────────────────────────────────────────────────
# Multi-variant path (one Groq call returns every language's narration)
# ─────────────────────────────────────────────────────────────────────────
def _generate_multivariant(
    preset: ChannelPreset, user: str, n: int, variants: list,
) -> dict[str, Any]:
    # Build the per-language requirement lines
    lang_lines = []
    for v in variants:
        lang = v["lang"]
        lo, hi, blurb = LANG_WORD_TARGETS.get(lang, LANG_WORD_TARGETS["en"])
        lang_lines.append(
            f'    "{lang}": {{\n'
            f'      "youtube_title": "catchy title in {_lang_label(lang)} (<90 chars, no hashtags)",\n'
            f'      "youtube_description": "2-3 sentences in {_lang_label(lang)} + optional #Shorts",\n'
            f'      "full_narration": "ONE continuous paragraph in {_lang_label(lang)}. '
            f'{blurb}. Natural spoken narration, no segment markers."\n'
            f'    }}'
        )
    variants_block = ",\n".join(lang_lines)

    word_targets = "\n".join(
        f"  - {_lang_label(v['lang'])}: {LANG_WORD_TARGETS.get(v['lang'], LANG_WORD_TARGETS['en'])[2]}"
        for v in variants
    )
    lang_keys = ", ".join(f'"{v["lang"]}"' for v in variants)

    user += f"""
Return ONLY valid JSON with this shape:
{{
  "image_prompts": [
    "visual description for image 1 — IN ENGLISH ONLY: setting, subject, action. No style words. No text in image.",
    "visual description for image 2 — in English…",
    "..."
  ],
  "variants": {{
{variants_block}
  }}
}}

STRICT RULES:
- "image_prompts" array MUST have exactly {n} entries, ALL in English.
- "variants" object MUST contain keys: {lang_keys}.
- Each variant tells the SAME facts/story but written natively in that language (not literal translation).
- Word-count targets per language:
{word_targets}
- Narrations are continuous spoken paragraphs — no segment numbers, no headings.
- Titles/descriptions: each in its own language.
- BEFORE you output JSON: mentally count words in each full_narration. If English is under 115 words OR Hindi under 100 words, REWRITE that paragraph longer (same facts) until counts are met.
"""

    last_err: str | None = None
    max_attempts = 4
    for attempt in range(max_attempts):
        extra = ""
        if last_err:
            extra = (
                "\n\n=== REGENERATE (previous JSON failed validation) ===\n"
                f"{last_err}\n"
                "Return a NEW complete JSON object that fixes the issue. "
                "Keep the same facts/story and the same image_prompts beats; "
                "expand ONLY the narration(s) that were too short — add 3-5 full sentences each.\n"
            )
        # Later attempts: lower temperature so the model obeys length constraints more reliably.
        temp = 0.85 if attempt < 2 else 0.45
        data = _call_groq(preset, user + extra, temperature=temp)
        try:
            _assert_multivariant_valid(data, variants, n)
            return data
        except ValueError as e:
            last_err = str(e)
            if attempt == max_attempts - 1:
                raise


def _assert_multivariant_valid(data: dict[str, Any], variants: list, n: int) -> None:
    prompts = data.get("image_prompts")
    if not isinstance(prompts, list) or len(prompts) != n:
        raise ValueError(f"Expected {n} image_prompts, got {len(prompts or [])}")
    for i, p in enumerate(prompts):
        if not isinstance(p, str) or not p.strip():
            raise ValueError(f"image_prompt {i} is empty")

    vmap = data.get("variants")
    if not isinstance(vmap, dict):
        raise ValueError("Groq response missing 'variants' object")

    for v in variants:
        lang = v["lang"]
        node = vmap.get(lang)
        if not isinstance(node, dict):
            raise ValueError(f"variants['{lang}'] missing")

        narration = (node.get("full_narration") or "").strip()
        if not narration:
            raise ValueError(f"variants['{lang}'].full_narration empty")

        min_words = v.get("min_words", DEFAULT_MIN_WORDS.get(lang, 80))
        word_count = len(narration.split())
        if word_count < min_words:
            lo, hi, _ = LANG_WORD_TARGETS.get(lang, LANG_WORD_TARGETS["en"])
            raise ValueError(
                f"variants['{lang}'].full_narration too short "
                f"({word_count} words, need ≥{min_words}; ideal range {lo}-{hi})"
            )

        if not (node.get("youtube_title") or "").strip():
            raise ValueError(f"variants['{lang}'].youtube_title empty")


def _call_groq(
    preset: ChannelPreset,
    user: str,
    *,
    temperature: float = 0.85,
) -> dict[str, Any]:
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not configured")

    client = Groq(
        api_key=api_key,
        default_headers={"User-Agent": "Monkey-Baba/1.0"},
    )
    resp = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": preset["groq_system_hint"]},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_tokens=3072,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content
    if not raw:
        raise RuntimeError("Empty Groq response")
    return json.loads(raw)

