import contextlib
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import valuation
from data import Fundamentals, load_fixture


def _exit_code(argv):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return valuation.main(argv)


class TestValuation(unittest.TestCase):
    def test_table_rows_present(self):
        r = valuation.build_valuation(load_fixture("CRWV"), as_json=True)
        metrics = {row["metric"] for row in r["rows"]}
        for expected in ("Price", "Enterprise value", "EV / Sales", "EV / EBITDA",
                         "DCF / share", "Rule of 40"):
            self.assertIn(expected, metrics)

    def test_dcf_skipped_when_fcf_negative(self):
        rows = {row["metric"]: row for row in
                valuation.build_valuation(load_fixture("CRWV"), as_json=True)["rows"]}
        self.assertEqual(rows["DCF / share"]["value"], "n/a")
        self.assertIn("FCF negative", rows["DCF / share"]["read"])

    def test_ev_ebitda_distortion_flagged(self):
        # EBITDA > revenue (margin >100%) must be flagged, and EV/Sales preferred.
        f = Fundamentals(
            ticker="X", available=True, source="fixture",
            revenue=500_000_000, revenue_prior=100_000_000,
            gross_profit=350_000_000, ebitda=520_000_000,   # 104% EBITDA margin
            free_cash_flow=-100_000_000, capex=200_000_000,
            total_debt=100_000_000, total_cash=50_000_000,
            shares_outstanding=100_000_000, market_cap=10_000_000_000,
        )
        rows = {row["metric"]: row for row in valuation.build_valuation(f, as_json=True)["rows"]}
        self.assertIn("distorted", rows["EV / EBITDA"]["read"])

    def test_text_render_is_a_table_with_footer(self):
        text = valuation.build_valuation(load_fixture("CRWV"), as_json=False)
        self.assertIn("Metric", text)
        self.assertIn("Read", text)
        self.assertIn("Verdict:", text)
        self.assertIn("Not investment advice", text)

    def test_exit_code_signals_availability(self):
        self.assertEqual(_exit_code(["CRWV", "--fixture"]), 0)
        self.assertEqual(_exit_code(["ZZZZ", "--fixture"]), 1)


if __name__ == "__main__":
    unittest.main()
