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
        r = analyze.build_report(f)
        self.assertTrue(r["available"] if "available" in r else True)
        self.assertIn("rule40", r)
        self.assertEqual(r["rule40"]["regime"], "ai_neocloud")
        # EBITDA score is flattering (~167); negative FCF margin must block a green pass.
        self.assertGreater(r["rule40"]["score_ebitda"], 150)
        self.assertFalse(r["rule40"]["passes"])
        # Negative FCF => DCF is skipped, not fabricated.
        self.assertNotIn("dcf", r)
        self.assertIn("dcf_note", r)

    def test_text_report_has_safety_footer(self):
        f = load_fixture("CRWV")
        text = analyze.format_report(analyze.build_report(f))
        self.assertIn("Not investment advice", text)
        self.assertIn("SAMPLE DATA", text)  # fixture must be labelled non-live

    def test_unavailable_data_is_graceful(self):
        f = Fundamentals(ticker="ZZZZ", available=False, error="network down")
        text = analyze.format_report(analyze.build_report(f))
        self.assertIn("unavailable", text.lower())
        self.assertIn("Claude Code", text)

    def test_rule40_skipped_when_a_margin_is_missing(self):
        # Only EBITDA is derivable (no FCF); the engine must NOT impute FCF=EBITDA,
        # which would fabricate a zero EBITDA-to-FCF gap.
        f = Fundamentals(
            ticker="X", available=True, source="fixture",
            revenue=200_000_000, revenue_prior=100_000_000,
            ebitda=100_000_000, free_cash_flow=None,
            shares_outstanding=10_000_000,
        )
        r = analyze.build_report(f)
        self.assertNotIn("rule40", r)
        self.assertIn("rule40_note", r)
        self.assertIn("FCF margin", r["rule40_note"])
        # And the skip is surfaced in the text report, not swallowed.
        self.assertIn("Rule of 40 skipped", analyze.format_report(analyze.build_report(f)))

    def test_positive_fcf_does_not_enable_automatic_dcf(self):
        # Revenue growth must not silently become ten years of FCF growth.
        f = Fundamentals(
            ticker="Y", available=True, source="fixture",
            revenue=300_000_000, revenue_prior=100_000_000,   # +200% YoY
            ebitda=60_000_000, free_cash_flow=40_000_000,
            shares_outstanding=10_000_000, total_cash=0.0, total_debt=0.0,
        )
        r = analyze.build_report(f)
        self.assertNotIn("dcf", r)
        self.assertIn("explicit FCF-growth", r["dcf_note"])

    def test_zero_revenue_growth_still_does_not_imply_fcf_growth(self):
        f = Fundamentals(
            ticker="Z", available=True, source="fixture",
            revenue=100_000_000, revenue_prior=100_000_000,   # flat
            ebitda=20_000_000, free_cash_flow=10_000_000,
            shares_outstanding=10_000_000, total_cash=0.0, total_debt=0.0,
        )
        r = analyze.build_report(f)
        self.assertNotIn("dcf", r)
        self.assertIn("explicit FCF-growth", r["dcf_note"])

    def test_dcf_skipped_when_net_debt_unknown(self):
        # Positive FCF but missing cash → fail closed, do not impute net_debt=0.
        f = Fundamentals(
            ticker="ND", available=True, source="fixture",
            revenue=100_000_000, revenue_prior=90_000_000,
            ebitda=20_000_000, free_cash_flow=10_000_000,
            shares_outstanding=10_000_000, total_debt=5_000_000, total_cash=None,
        )
        r = analyze.build_report(f)
        self.assertNotIn("dcf", r)
        self.assertIn("net debt unknown", r["dcf_note"].lower())

    def test_mixed_annual_and_ttm_periods_disable_margin(self):
        f = Fundamentals(
            ticker="MIXED", available=True, source="yfinance",
            revenue=100_000_000, free_cash_flow=10_000_000,
            field_metadata={
                "revenue": {"period_type": "annual"},
                "free_cash_flow": {"period_type": "ttm"},
            },
        )
        r = analyze.build_report(f)
        self.assertIsNone(r["derived"]["fcf_margin_pct"])
        self.assertTrue(any("FCF margin disabled" in w for w in r["warnings"]))

    def test_spot_and_annual_share_counts_disable_dilution_adjustment(self):
        f = Fundamentals(
            ticker="MIXSH", available=True, source="yfinance",
            revenue=100_000_000, revenue_prior=80_000_000,
            ebitda=20_000_000, free_cash_flow=10_000_000,
            shares_outstanding=11_000_000, shares_prior=10_000_000,
            field_metadata={
                "shares_outstanding": {"period_type": "spot"},
                "shares_prior": {"period_type": "annual"},
            },
        )
        r = analyze.build_report(f)
        self.assertIsNone(r["derived"]["share_dilution_pct"])
        self.assertIsNone(r["rule40"]["dilution_adjusted_score"])
        self.assertTrue(any("share dilution disabled" in w for w in r["warnings"]))

    def test_cross_currency_enterprise_value_is_disabled(self):
        f = Fundamentals(
            ticker="FX", available=True, source="yfinance",
            market_cap=500_000_000, total_debt=50_000_000, total_cash=10_000_000,
            revenue=100_000_000, ebitda=20_000_000,
            field_metadata={
                "market_cap": {"currency": "USD"},
                "total_debt": {"currency": "EUR"},
                "total_cash": {"currency": "EUR"},
            },
        )
        r = analyze.build_report(f)
        self.assertIsNone(r["derived"]["enterprise_value"])
        self.assertIsNone(r["derived"]["ev_sales"])
        self.assertTrue(any("enterprise value disabled" in w for w in r["warnings"]))

    def test_non_usd_text_uses_iso_currency_instead_of_dollar_sign(self):
        f = Fundamentals(
            ticker="EURX", available=True, source="fixture", data_state="fixture",
            currency="EUR", price=50.0, market_cap=500_000_000,
            revenue=100_000_000,
        )
        text = analyze.format_report(analyze.build_report(f))
        self.assertIn("Price: EUR 50", text)
        self.assertIn("Market cap: EUR 500.00M", text)
        self.assertNotIn("Price: $50", text)


if __name__ == "__main__":
    unittest.main()
