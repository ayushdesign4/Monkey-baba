"""Test topic duplicate prevention and similarity."""

import unittest
from src.topic.history import calculate_similarity, TopicHistory

class TestTopic(unittest.TestCase):
    def test_similarity(self):
        s1 = "The Mystery of the Lost Roman Legion in China"
        s2 = "Lost Roman Legion Discovered in Ancient China"
        sim = calculate_similarity(s1, s2)
        self.assertGreater(sim, 0.4)

    def test_distinct_topics(self):
        s1 = "The Mystery of the Lost Roman Legion in China"
        s2 = "Deep Sea Creatures of the Mariana Trench"
        sim = calculate_similarity(s1, s2)
        self.assertLess(sim, 0.2)

if __name__ == "__main__":
    unittest.main()
