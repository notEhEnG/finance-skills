import contextlib
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import company
from data import Fundamentals, load_fixture


def _exit_code(argv):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return company.main(argv)

# The nine sequential stages the walkthrough must always present, in order.
EXPECTED_ORDER = [
    "Business Model", "Competitive Advantage", "Revenue Drivers", "Margins",
    "Financial Health", "Growth", "Valuation", "Risks", "Final Verdict",
]


class TestCompany(unittest.TestCase):
    def test_all_sections_present_in_order(self):
        r = company.build_company(load_fixture("CRWV"), as_json=True)
        headings = [s["heading"] for s in r["sections"]]
        self.assertEqual(headings, EXPECTED_ORDER)

    def test_neocloud_verdict_leads_with_backlog_runway(self):
        r = company.build_company(load_fixture("CRWV"), as_json=True)
        verdict = " ".join(r["sections"][-1]["lines"]).lower()
        self.assertIn("neocloud", verdict)
        self.assertIn("runway", verdict)
        self.assertIn("not a recommendation", verdict)

    def test_text_report_has_flow_arrows_and_footer(self):
        text = company.build_company(load_fixture("CRWV"), as_json=False)
        self.assertIn("▼", text)                       # sequential flow rendered
        self.assertIn("SAMPLE DATA", text)             # fixture labelled non-live
        self.assertIn("Not investment advice", text)

    def test_missing_net_debt_is_flagged_not_guessed(self):
        # Debt known, cash missing → net_debt None → Financial Health must say n/a.
        f = Fundamentals(
            ticker="X", available=True, source="fixture",
            revenue=200_000_000, revenue_prior=100_000_000,
            gross_profit=120_000_000, ebitda=40_000_000, free_cash_flow=10_000_000,
            total_debt=50_000_000, total_cash=None, shares_outstanding=10_000_000,
        )
        r = company.build_company(f, as_json=True)
        health = " ".join({s["heading"]: s["lines"] for s in r["sections"]}["Financial Health"])
        self.assertIn("n/a", health.lower())

    def test_unavailable_data_is_graceful(self):
        f = Fundamentals(ticker="ZZZZ", available=False, error="network down")
        text = company.build_company(f, as_json=False)
        self.assertIn("unavailable", text.lower())

    def test_exit_code_signals_availability(self):
        self.assertEqual(_exit_code(["CRWV", "--fixture"]), 0)   # fixture exists
        self.assertEqual(_exit_code(["ZZZZ", "--fixture"]), 1)   # no fixture → unavailable


if __name__ == "__main__":
    unittest.main()
