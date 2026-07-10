import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import analyze
import screen
from data import load_fixture


def _report(ticker):
    return analyze.build_report(load_fixture(ticker))


class TestEvaluate(unittest.TestCase):
    def test_simple_comparison(self):
        self.assertTrue(screen.evaluate("gross_margin > 50", _report("CRWV")))
        self.assertFalse(screen.evaluate("gross_margin > 50", _report("NBIS")))

    def test_field_with_digits(self):
        # rule40 field name contains digits — must parse.
        self.assertTrue(screen.evaluate("rule40 < 0", _report("CRWV")))

    def test_and_requires_all(self):
        self.assertFalse(screen.evaluate("gross_margin > 50 and fcf_margin > 0", _report("CRWV")))

    def test_or_requires_any(self):
        self.assertTrue(screen.evaluate("gross_margin > 90 or growth > 100", _report("CRWV")))

    def test_missing_field_fails_closed(self):
        # net_debt is None on this record -> the clause is False, never a silent pass.
        rep = _report("CRWV")
        rep["derived"]["net_debt"] = None
        self.assertFalse(screen.evaluate("net_debt < 0", rep))

    def test_unknown_field_raises(self):
        with self.assertRaises(screen.RuleError):
            screen.evaluate("bogus > 5", _report("CRWV"))

    def test_malformed_clause_raises(self):
        with self.assertRaises(screen.RuleError):
            screen.evaluate("gross_margin !! 5", _report("CRWV"))

    def test_empty_rule_raises(self):
        with self.assertRaises(screen.RuleError):
            screen.evaluate("   ", _report("CRWV"))

    def test_code_injection_is_rejected_not_evaluated(self):
        # The rule language is a parser, not eval — hostile input must raise
        # RuleError (bad field/clause), never execute.
        hostile = [
            "__import__('os').system('echo pwned')",
            "growth > 0 or __import__('os')",
            "1; import os",
            "eval('2+2') > 0",
            "growth.__class__ > 0",
            "() or True",
            "growth > 0 and (drop table)",
        ]
        rep = _report("CRWV")
        for rule in hostile:
            with self.assertRaises(screen.RuleError, msg=f"should reject: {rule!r}"):
                screen.evaluate(rule, rep)

    def test_value_must_be_numeric(self):
        # Comparing a field to a non-number is a parse error, not a crash.
        with self.assertRaises(screen.RuleError):
            screen.evaluate("growth > abc", _report("CRWV"))

    def test_only_whitelisted_fields_are_reachable(self):
        # Every field referenced in a rule must be in the FIELDS whitelist.
        for name in ("os", "system", "import", "class", "globals"):
            with self.assertRaises(screen.RuleError):
                screen.evaluate(f"{name} > 0", _report("CRWV"))


class TestScreen(unittest.TestCase):
    def test_screen_over_fixtures(self):
        res = screen.screen("gross_margin > 50", ["CRWV", "NBIS"], use_fixture=True)
        matched = {m["ticker"] for m in res["matches"]}
        self.assertEqual(matched, {"CRWV"})

    def test_no_data_ticker_marked(self):
        res = screen.screen("gross_margin > 0", ["ZZZZ"], use_fixture=True)
        self.assertIsNone(res["results"][0]["passes"])


if __name__ == "__main__":
    unittest.main()
