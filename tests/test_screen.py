import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import analyze
import screen
from data import load_fixture


def _report(ticker):
    return analyze.build_report(load_fixture(ticker), as_json=True)


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
