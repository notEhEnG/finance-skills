import contextlib
import io
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

    def test_aliases_to_runnable_core(self):
        cases = {
            "val": "valuation",
            "r40": "brief",
            "rule40": "brief",
            "dcf": "valuation",
            "risk": "redflags",
            "growth": "brief",
            "snap": "brief",
            "analyse": "analyze",
            "rf": "redflags",
        }
        for alias, canonical in cases.items():
            r = router.resolve(alias)
            self.assertEqual(r.command, canonical, f"{alias} → {canonical}")
            self.assertEqual(r.method, "alias")

    def test_framework_tokens_resolve_to_framework_command(self):
        r = router.resolve("semiconductor")
        self.assertEqual(r.command, "framework")
        self.assertEqual(r.framework, "semiconductor")
        r2 = router.resolve("semis")
        self.assertEqual(r2.command, "framework")
        self.assertEqual(r2.framework, "semiconductor")
        r3 = router.resolve("ai-cloud")
        self.assertEqual(r3.command, "framework")
        self.assertEqual(r3.framework, "neocloud")

    def test_fuzzy_typos(self):
        r = router.resolve("vluation")
        self.assertEqual(r.command, "valuation")
        self.assertEqual(r.method, "fuzzy")

    def test_unknown_returns_suggestions_not_crash(self):
        r = router.resolve("zxqw")
        self.assertFalse(r.resolved)
        self.assertEqual(r.method, "unknown")

    def test_ghost_modules_are_not_core(self):
        for ghost in ("dcf", "growth", "risk", "rule40", "rank", "portfolio", "news"):
            self.assertNotIn(ghost, router.CORE_VERBS)
            self.assertNotIn(ghost, router.RUNNABLE)

    def test_every_core_verb_is_runnable(self):
        for name in router.CORE_VERBS:
            self.assertIn(name, router.RUNNABLE, f"Core verb without module: {name}")

    def test_builders_are_loadable(self):
        for name in router.BUILDERS:
            fn = router.load_builder(name)
            self.assertTrue(callable(fn), name)
        self.assertEqual(router.EXPORTABLE, set(router.BUILDERS))
        self.assertEqual(router.WATCHLIST_VERBS, set(router.BUILDERS))


class TestKeywordRouting(unittest.TestCase):
    def test_plain_questions_map_to_runnable_verbs(self):
        cases = {
            "is NBIS a value trap?": "redflags",
            "is NVDA a buy?": "valuation",
            "any red flags in PLTR?": "redflags",
            "how does AMD compare to NVDA": "compare",
            "rule of 40 for CRM": "brief",
            "tell me about SNOW": "company",
            "what's the financial health of CRWV": "health",
            "does AMD have a moat": "moat",
            "growth rate of SNOW": "brief",
            "quick take on NBIS": "brief",
            "what is it worth": "valuation",
        }
        for question, verb in cases.items():
            self.assertEqual(router.route(question).verb, verb, question)

    def test_no_match_defaults_to_brief(self):
        r = router.route("please water the plants")
        self.assertEqual(r.verb, "brief")
        self.assertEqual(r.method, "default")
        self.assertEqual(r.verb, "brief")

    def test_leading_question_word_does_not_hijack(self):
        # "what color..." has no finance keyword → default brief, not a fuzzy verb.
        r = router.route("what color is the sky")
        self.assertEqual(r.method, "default")
        self.assertEqual(r.verb, "brief")

    def test_explicit_verb_token_still_routes(self):
        r = router.route("valuation NBIS")
        self.assertEqual(r.verb, "valuation")
        self.assertEqual(r.method, "verb")

    def test_every_keyword_verb_is_known(self):
        for verb in router.KEYWORDS:
            self.assertIn(verb, router.VERBS, f"KEYWORDS verb not in VERBS: {verb}")

    def test_route_is_deterministic(self):
        verbs = {router.route("is it cheap or a value trap").verb for _ in range(20)}
        self.assertEqual(len(verbs), 1)


class TestTickerExtraction(unittest.TestCase):
    def test_explicit_symbol_in_question(self):
        self.assertEqual(router.extract_tickers("Do you think NBIS is a buy?"), ["NBIS"])

    def test_dollar_prefixed(self):
        self.assertEqual(router.extract_tickers("is $nvda overvalued"), ["NVDA"])

    def test_company_name_maps(self):
        self.assertIn("NVDA", router.extract_tickers("is nvidia a good buy?"))

    def test_ignores_jargon_words(self):
        self.assertEqual(router.extract_tickers("what is the AI GPU DCF story"), [])

    def test_multiple_tickers_first_seen_order(self):
        self.assertEqual(router.extract_tickers("compare AMD and NVDA"), ["AMD", "NVDA"])

    def test_class_share_symbols(self):
        self.assertEqual(router.extract_tickers("is BRK.B cheap"), ["BRK.B"])


class TestHelpAndRegistry(unittest.TestCase):
    def test_help_lists_only_canonical(self):
        text = router.format_help()
        self.assertIn("brief", text)
        self.assertIn("Core", text)
        for cmds in router.HELP_GROUPS.values():
            for c in cmds:
                self.assertIn(c, router.CANONICAL, f"help lists unknown: {c}")

    def test_top_verbs_are_runnable_core(self):
        for verb in router.TOP_VERBS:
            self.assertIn(verb, router.CORE_VERBS)
            self.assertIn(verb, router.RUNNABLE)


class TestDispatch(unittest.TestCase):
    def test_dispatch_brief_fixture(self):
        code = router.main(["brief", "NBIS", "--fixture", "--json"])
        self.assertEqual(code, 0)

    def test_bare_ticker_defaults_to_brief(self):
        code = router.main(["NBIS", "--fixture", "--json"])
        self.assertEqual(code, 0)

    def test_framework_token_dispatches(self):
        code = router.main(["semiconductor", "CRWV", "--fixture"])
        self.assertEqual(code, 0)

    def test_fuzzy_verb_typo_with_ticker_dispatches_the_verb(self):
        # `valuatoin NBIS` must run valuation ON NBIS, not eat the typo as a
        # ticker and drop the real one (regression: the fuzzy-verb branch was dead).
        with contextlib.redirect_stdout(io.StringIO()):
            code = router.main(["valuatoin", "NBIS", "--fixture", "--json"])
        self.assertEqual(code, 0)

    def test_lone_fuzzy_token_falls_back_to_brief(self):
        # No trailing ticker → treat as a (bad) ticker → brief → unavailable.
        with contextlib.redirect_stdout(io.StringIO()):
            code = router.main(["valuatoin", "--fixture"])
        self.assertEqual(code, 1)


class TestRouteDefault(unittest.TestCase):
    def test_apply_default_false_signals_no_match(self):
        r = router.route("please water the plants", apply_default=False)
        self.assertEqual(r.method, "none")   # caller can detect "nothing matched"
        self.assertEqual(r.verb, "brief")    # …but verb is never a dead name


if __name__ == "__main__":
    unittest.main()
