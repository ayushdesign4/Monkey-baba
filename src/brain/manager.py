"""Brain Provider Orchestrator with retries, structured JSON extraction, and fallbacks."""

import json
import re
from typing import Dict, Any, Tuple, Optional
from src.brain.gemini import GeminiProvider
from src.brain.groq import GroqProvider
from src.brain.backup import BackupLLMProvider
from src.utils.logging import log, log_warn, log_error
from src.utils.retry import retry_with_backoff

class BrainManager:
    def __init__(self):
        self.primary = GeminiProvider()
        self.fallback_1 = GroqProvider()
        self.fallback_2 = BackupLLMProvider()
        
        self.last_provider_used = None
        self.fallback_used = False

    def generate_text(self, prompt: str, system_instruction: str = "") -> Tuple[str, str, bool]:
        """
        Generate text using Primary (Gemini) -> Fallback #1 (Groq) -> Fallback #2 (Backup).
        Returns: (text, provider_name, fallback_used)
        """
        # 1. Primary: Gemini
        if self.primary.is_configured():
            try:
                log("BRAIN", "Calling Primary Brain Provider: Gemini...")
                res = retry_with_backoff(
                    lambda: self.primary.generate(prompt, system_instruction),
                    stage="BRAIN",
                    max_retries=2
                )
                self.last_provider_used = "gemini"
                self.fallback_used = False
                return res, "gemini", False
            except Exception as e:
                log_warn("BRAIN", f"Gemini failed ({e}). Switching to Fallback #1 (Groq)...")
        else:
            log_warn("BRAIN", "Gemini not configured or missing key. Skipping to fallback.")

        # 2. Fallback #1: Groq
        if self.fallback_1.is_configured():
            try:
                log("FALLBACK", "Calling Fallback #1 Brain Provider: Groq...")
                res = retry_with_backoff(
                    lambda: self.fallback_1.generate(prompt, system_instruction),
                    stage="BRAIN",
                    max_retries=2
                )
                self.last_provider_used = "groq"
                self.fallback_used = True
                return res, "groq", True
            except Exception as e:
                log_warn("BRAIN", f"Groq failed ({e}). Switching to Fallback #2 (Backup LLM)...")
        else:
            log_warn("BRAIN", "Groq not configured. Skipping to Fallback #2.")

        # 3. Fallback #2: Backup LLM
        if self.fallback_2.is_configured():
            try:
                log("FALLBACK", "Calling Fallback #2 Brain Provider: Backup LLM...")
                res = retry_with_backoff(
                    lambda: self.fallback_2.generate(prompt, system_instruction),
                    stage="BRAIN",
                    max_retries=2
                )
                self.last_provider_used = "backup"
                self.fallback_used = True
                return res, "backup", True
            except Exception as e:
                log_error("BRAIN", f"All brain providers failed: {e}")
                raise RuntimeError(f"All Brain LLM providers failed. Last error: {e}")

        raise RuntimeError("No configured Brain providers available. Check GEMINI_API_KEY or GROQ_API_KEY.")

    def generate_json(self, prompt: str, system_instruction: str = "") -> Tuple[Dict[str, Any], str, bool]:
        """Generate structured JSON response, with markdown strip and validation."""
        sys_prompt = (
            system_instruction + "\nCRITICAL: Respond ONLY with valid, unescaped raw JSON. "
            "Do NOT include markdown formatting like ```json ... ``` or conversational preamble."
        ).strip()

        raw_text, provider, fallback_used = self.generate_text(prompt, sys_prompt)

        # Clean markdown code blocks if model wrapped output
        cleaned = raw_text.strip()
        if "```" in cleaned:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
            if match:
                cleaned = match.group(1).strip()
            else:
                cleaned = cleaned.replace("```json", "").replace("```", "").strip()

        try:
            parsed = json.loads(cleaned)
            return parsed, provider, fallback_used
        except json.JSONDecodeError as e:
            # Fallback regex extraction of outer JSON object or array
            match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", cleaned)
            if match:
                try:
                    parsed = json.loads(match.group(1))
                    return parsed, provider, fallback_used
                except Exception:
                    pass
            log_error("BRAIN", f"Malformed JSON from {provider}: {raw_text[:200]}")
            raise RuntimeError(f"Brain provider ({provider}) returned invalid JSON: {e}")
