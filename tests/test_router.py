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


class TestTickerExtraction(unittest.TestCase):
    def test_explicit_symbol_in_question(self):
        self.assertEqual(router.extract_tickers("Do you think NBIS is a buy?"), ["NBIS"])

    def test_dollar_prefixed(self):
        self.assertEqual(router.extract_tickers("is $nvda overvalued"), ["NVDA"])

    def test_company_name_maps(self):
        self.assertIn("NVDA", router.extract_tickers("is nvidia a good buy?"))

    def test_ignores_jargon_words(self):
        # "AI", "GPU", "DCF" etc. must not be mistaken for tickers.
        self.assertEqual(router.extract_tickers("what is the AI GPU DCF story"), [])

    def test_multiple_tickers_first_seen_order(self):
        self.assertEqual(router.extract_tickers("compare AMD and NVDA"), ["AMD", "NVDA"])

    def test_class_share_symbols(self):
        self.assertEqual(router.extract_tickers("is BRK.B cheap"), ["BRK.B"])
        self.assertEqual(router.extract_tickers("thoughts on $rds.a"), ["RDS.A"])

    def test_dotted_abbreviations_are_not_tickers(self):
        # "U.S." and "U.K." must not be mistaken for class-share symbols.
        self.assertEqual(router.extract_tickers("is the U.S. market a buy"), [])


class TestKeywordRouting(unittest.TestCase):
    def test_plain_questions_map_to_expected_verb(self):
        cases = {
            "is NBIS a value trap?": "risk",
            "is NVDA a buy?": "valuation",
            "any red flags in PLTR?": "redflags",
            "how does AMD compare to NVDA": "compare",
            "rule of 40 for CRM": "rule40",
            "tell me about SNOW": "company",
            "what's the financial health of CRWV": "health",
            "does AMD have a moat": "moat",
            "growth rate of SNOW": "growth",
        }
        for question, verb in cases.items():
            self.assertEqual(router.route(question).verb, verb,
                             f"{question!r} should route to {verb}")

    def test_longest_phrase_wins(self):
        # "is it a buy" (valuation) must beat the bare "buy"/generic signals.
        self.assertEqual(router.route("do you think it is a buy here").verb, "valuation")

    def test_explicit_verb_token_still_routes(self):
        r = router.route("valuation NBIS")
        self.assertEqual(r.verb, "valuation")
        self.assertEqual(r.method, "verb")

    def test_leading_question_word_does_not_hijack(self):
        # A fuzzy match on "what"/"how" must NOT be treated as a verb token.
        self.assertIsNone(router.route("what color is the sky").verb)

    def test_no_trigger_returns_none(self):
        r = router.route("please water the plants")
        self.assertIsNone(r.verb)
        self.assertEqual(r.method, "none")

    def test_every_keyword_verb_is_canonical(self):
        for verb in router.KEYWORDS:
            self.assertIn(verb, router.CANONICAL, f"KEYWORDS references unknown verb: {verb}")

    def test_route_is_deterministic(self):
        verbs = {router.route("is it cheap or a value trap").verb for _ in range(20)}
        self.assertEqual(len(verbs), 1)


class TestDeterminism(unittest.TestCase):
    def test_fuzzy_is_stable_across_calls(self):
        # Sorted pools mean a tie-prone typo resolves identically every time.
        results = {router.resolve("valuaton").command for _ in range(20)}
        self.assertEqual(len(results), 1)


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
