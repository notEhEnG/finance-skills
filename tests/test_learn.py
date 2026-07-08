import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import learn


class TestLearn(unittest.TestCase):
    def test_direct_concept(self):
        text = learn.explain("dcf")
        self.assertIn("Discounted cash flow", text)
        self.assertIn("Common trap", text)

    def test_aliases_and_fuzzy(self):
        self.assertEqual(learn.resolve("r40"), "rule40")
        self.assertEqual(learn.resolve("porter"), "five-forces")
        self.assertEqual(learn.resolve("magic"), "magic-number")
        self.assertEqual(learn.resolve("discountd-cash-flow"), "dcf")  # typo → fuzzy

    def test_unknown_returns_none(self):
        self.assertIsNone(learn.resolve("zxqw"))
        self.assertIsNone(learn.explain("zxqw"))

    def test_uncomputable_kpis_still_have_a_lesson(self):
        # The skill can't compute these, but must still be able to teach them.
        for concept in ("magic-number", "cac-payback", "nrr"):
            self.assertIsNotNone(learn.explain(concept))

    def test_every_alias_points_at_a_real_concept(self):
        for target in learn.ALIASES.values():
            self.assertIn(target, learn.CONCEPTS)


if __name__ == "__main__":
    unittest.main()
