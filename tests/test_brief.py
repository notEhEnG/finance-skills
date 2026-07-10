"""brief — default answer-shaped stack over the shared engine."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import brief
import data


class TestBrief(unittest.TestCase):
    def test_neocloud_fixture_json_spine(self):
        f = data.load_fixture("NBIS")
        b = brief.build_brief(f, as_json=True)
        self.assertEqual(b["ticker"], "NBIS")
        self.assertEqual(b["source"], "fixture")
        self.assertEqual(b["regime"], "ai_neocloud")
        self.assertIsNotNone(b["rule40"])
        self.assertIn("preferred_score", b["rule40"])
        self.assertIn("capital_intensity_gap", b["rule40"])
        self.assertIn("ev_sales", b["valuation"])
        self.assertIn("net_debt", b["solvency"])
        self.assertIsInstance(b["redflags"], list)
        self.assertIsInstance(b["gaps"], list)
        self.assertIn("disclaimer", b)
        # Negative FCF → DCF gap guided, not invented
        gap_fields = {g["field"] for g in b["gaps"]}
        self.assertIn("dcf", gap_fields)
        self.assertIn("backlog_rpo", gap_fields)

    def test_crwv_fixture_text_renders(self):
        f = data.load_fixture("CRWV")
        text = brief.build_brief(f, as_json=False)
        self.assertIsInstance(text, str)
        self.assertIn("brief", text.lower())
        self.assertIn("Rule of 40", text)
        self.assertIn("Valuation", text)
        self.assertIn("SAMPLE DATA", text)

    def test_unavailable_is_graceful(self):
        f = data.Fundamentals(ticker="ZZZZ", available=False, error="no data")
        b = brief.build_brief(f, as_json=True)
        self.assertFalse(b.get("available", True))
        text = brief.build_brief(f, as_json=False)
        self.assertIsInstance(text, str)
        self.assertIn("unavailable", text.lower())

    def test_flags_are_severity_sorted(self):
        f = data.load_fixture("NBIS")
        b = brief.build_brief(f, as_json=True)
        # First flag should be high-severity when any HIGH exists.
        if b["redflags"]:
            ranks = {"⛔": 0, "⚠": 1, "•": 2}
            severities = [ranks.get(fl["severity"], 9) for fl in b["redflags"]]
            self.assertEqual(severities, sorted(severities))

    def test_same_engine_as_analyze(self):
        # Preferred Rule 40 must match analyze.build_report — one engine.
        import analyze
        f = data.load_fixture("NBIS")
        report = analyze.build_report(f, as_json=True)
        b = brief.build_brief(f, as_json=True)
        self.assertEqual(
            b["rule40"]["preferred_score"],
            report["rule40"]["preferred_score"],
        )
        self.assertEqual(b["solvency"]["net_debt"], report["derived"]["net_debt"])

    def test_cli_fixture(self):
        code = brief.main(["NBIS", "--fixture", "--json"])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
