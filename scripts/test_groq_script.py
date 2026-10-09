"""Test script for Groq text and structured JSON generation."""

import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import time
import urllib.request
import re

from src.script.validator import ScriptValidator
from src.script.generator import SCRIPT_PROMPT_TEMPLATE

def test_model(model_name: str):
    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        print("GROQ_API_KEY is missing!")
        return False

    prompt = SCRIPT_PROMPT_TEMPLATE.format(
        topic="The Lost Amber Room",
        story_summary="Tsar treasure looted during World War II and lost.",
        min_words=100
    )

    print(f"\n--- Testing {model_name} on Groq ---")
    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "You are an award-winning YouTube Shorts narrative director. Respond ONLY with valid, unescaped raw JSON."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 4096
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "User-Agent": "Monkey-Baba/1.0"
        },
        method="POST"
    )

    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"].strip()
            elapsed = time.time() - t0

            if "```" in content:
                m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
                content = m.group(1).strip() if m else content

            parsed = json.loads(content)
            is_valid, msg = ScriptValidator.validate(parsed)
            w_count = parsed.get("word_count", 0)
            scenes = parsed.get("scenes", [])
            title = parsed.get("title", "")

            print(f"RESULT: PASS")
            print(f"MODEL: {model_name}")
            print(f"LATENCY: {elapsed:.2f}s")
            print(f"TITLE: {title}")
            print(f"VALID_SCRIPT: {is_valid} ({msg})")
            print(f"WORD_COUNT: {w_count}")
            print(f"SCENE_COUNT: {len(scenes)}")
            return is_valid
    except Exception as e:
        err = str(e)
        if key:
            err = err.replace(key, "[REDACTED]")
        print(f"RESULT: FAIL ({err})")
        return False

if __name__ == "__main__":
    for m in ["openai/gpt-oss-120b", "qwen/qwen3.8-27b"]:
        success = test_model(m)
        if success:
            print(f"SELECTED_MODEL: {m}")
            break
        time.sleep(2)
