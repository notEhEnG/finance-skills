import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import router


class TestResolve(unittest.TestCase):
    def test_exact_verbs(self):
        for verb in router.TOP_VERBS:
            r = router.resolve(verb)
            self.assertEqual(r.command, verb)
            self.assertEqual(r.method, "exact")

    def test_aliases(self):
        cases = {
            "val": "valuation", "valn": "valuation", "comp": "compare",
            "semis": "semiconductor", "mgmt": "management", "r40": "rule40",
            "rf": "redflags", "opp": "opportunities", "neocloud": "ai-cloud",
            "analyse": "analyze",
        }
        for alias, canonical in cases.items():
            r = router.resolve(alias)
            self.assertEqual(r.command, canonical, f"{alias} should map to {canonical}")
            self.assertEqual(r.method, "alias")

    def test_fuzzy_typos(self):
        r = router.resolve("vluation")
        self.assertEqual(r.command, "valuation")
        self.assertEqual(r.method, "fuzzy")

    def test_fuzzy_canonicalizes_alias_hit(self):
        # A typo close to an alias key ("sems" ~ "semis") still resolves to canonical.
        r = router.resolve("sems")
        self.assertEqual(r.command, "semiconductor")

    def test_case_and_whitespace_insensitive(self):
        r = router.resolve("  VALUATION  ")
        self.assertEqual(r.command, "valuation")

    def test_unknown_returns_suggestions_not_crash(self):
        r = router.resolve("zxqw")
        self.assertFalse(r.resolved)
        self.assertEqual(r.method, "unknown")
        self.assertIsInstance(r.suggestions, list)

    def test_empty_is_unknown(self):
        self.assertFalse(router.resolve("   ").resolved)


class TestHelp(unittest.TestCase):
    def test_help_groups_by_question(self):
        text = router.format_help()
        self.assertIn("Is it cheap?", text)
        self.assertIn("valuation", text)
        # Every command shown in help must be a real canonical command.
        for cmds in router.HELP_GROUPS.values():
            for c in cmds:
                self.assertIn(c, router.CANONICAL, f"help lists unknown command: {c}")

    def test_top_verbs_are_canonical(self):
        for verb in router.TOP_VERBS:
            self.assertIn(verb, router.CANONICAL)


if __name__ == "__main__":
    unittest.main()
