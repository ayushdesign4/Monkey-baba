"""Test script validation and word counting."""

import unittest
from src.script.validator import ScriptValidator, count_words
from src.script.generator import ScriptGenerator
from src.brain.manager import BrainManager

class TestScript(unittest.TestCase):
    def test_word_count(self):
        sample = "This is a test of the emergency broadcast system. It consists of exactly fourteen spoken words."
        self.assertEqual(count_words(sample), 16)

    def test_validation_fails_under_100_words(self):
        script = {
            "full_narration": "Too short for a sixty second short.",
            "scenes": [{"scene_number": i, "narration": "Brief"} for i in range(1, 7)]
        }
        valid, msg = ScriptValidator.validate(script)
        self.assertFalse(valid)

    def test_emergency_script_validity(self):
        gen = ScriptGenerator(BrainManager())
        script = gen._build_emergency_script("Lost Atlantis", "The city drowned.")
        valid, msg = ScriptValidator.validate(script)
        self.assertTrue(valid)
        self.assertGreaterEqual(script["word_count"], 100)
        self.assertEqual(len(script["scenes"]), 7)

if __name__ == "__main__":
    unittest.main()
