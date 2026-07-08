import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import analyze
from data import Fundamentals, load_fixture


class TestAnalyze(unittest.TestCase):
    def test_crwv_fixture_is_neocloud(self):
        f = load_fixture("CRWV")
        self.assertIsNotNone(f)
        r = analyze.build_report(f, as_json=True)
        self.assertTrue(r["available"] if "available" in r else True)
        self.assertIn("rule40", r)
        self.assertEqual(r["rule40"]["regime"], "ai_neocloud")
        # EBITDA score is flattering (~167); it must not "pass" on the capex-adjusted burn.
        self.assertGreater(r["rule40"]["score_ebitda"], 150)
        self.assertFalse(r["rule40"]["passes"])
        # Negative FCF => DCF is skipped, not fabricated.
        self.assertNotIn("dcf", r)
        self.assertIn("dcf_note", r)

    def test_text_report_has_safety_footer(self):
        f = load_fixture("CRWV")
        text = analyze.build_report(f, as_json=False)
        self.assertIn("Not investment advice", text)
        self.assertIn("SAMPLE DATA", text)  # fixture must be labelled non-live

    def test_unavailable_data_is_graceful(self):
        f = Fundamentals(ticker="ZZZZ", available=False, error="network down")
        text = analyze.build_report(f, as_json=False)
        self.assertIn("unavailable", text.lower())
        self.assertIn("Claude Code", text)

    def test_rule40_skipped_when_a_margin_is_missing(self):
        # Only EBITDA is derivable (no FCF); the engine must NOT impute FCF=EBITDA,
        # which would fabricate a zero capital-intensity gap.
        f = Fundamentals(
            ticker="X", available=True, source="fixture",
            revenue=200_000_000, revenue_prior=100_000_000,
            ebitda=100_000_000, free_cash_flow=None,
            shares_outstanding=10_000_000,
        )
        r = analyze.build_report(f, as_json=True)
        self.assertNotIn("rule40", r)
        self.assertIn("rule40_note", r)
        self.assertIn("FCF margin", r["rule40_note"])
        # And the skip is surfaced in the text report, not swallowed.
        self.assertIn("Rule of 40 skipped", analyze.build_report(f, as_json=False))

    def test_dcf_growth_is_capped_and_tagged_heuristic(self):
        # Runaway trailing growth must be capped at 25% and labelled a heuristic.
        f = Fundamentals(
            ticker="Y", available=True, source="fixture",
            revenue=300_000_000, revenue_prior=100_000_000,   # +200% YoY
            ebitda=60_000_000, free_cash_flow=40_000_000,
            shares_outstanding=10_000_000, total_cash=0.0, total_debt=0.0,
        )
        r = analyze.build_report(f, as_json=True)
        self.assertIn("dcf", r)
        self.assertEqual(r["dcf"]["assumptions"]["growth_rate"], 25.0)
        self.assertIn("dcf_basis", r)
        self.assertIn("Heuristic", r["dcf_basis"])

    def test_dcf_zero_growth_not_bumped_to_default(self):
        # 0% growth is a real value, not "missing" — it must not become 8%.
        f = Fundamentals(
            ticker="Z", available=True, source="fixture",
            revenue=100_000_000, revenue_prior=100_000_000,   # flat
            ebitda=20_000_000, free_cash_flow=10_000_000,
            shares_outstanding=10_000_000, total_cash=0.0, total_debt=0.0,
        )
        r = analyze.build_report(f, as_json=True)
        self.assertEqual(r["dcf"]["assumptions"]["growth_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()
