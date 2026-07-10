import contextlib
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import health
from data import Fundamentals, load_fixture


def _exit_code(argv):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return health.main(argv)


class TestHealth(unittest.TestCase):
    def test_rows_present(self):
        r = health.build_health(load_fixture("NBIS"), as_json=True)
        metrics = {row["metric"] for row in r["rows"]}
        for expected in ("FCF margin", "Cash runway", "Share dilution (YoY)",
                         "Altman Z-Score", "Piotroski F-Score"):
            self.assertIn(expected, metrics)

    def test_runway_computed_when_burning(self):
        rows = {row["metric"]: row for row in
                health.build_health(load_fixture("NBIS"), as_json=True)["rows"]}
        self.assertIn("yr", rows["Cash runway"]["value"])

    def test_runway_na_when_self_funding(self):
        f = Fundamentals(
            ticker="FCF+", available=True, source="fixture",
            revenue=1_000_000_000, revenue_prior=800_000_000,
            gross_profit=700_000_000, ebitda=300_000_000,
            free_cash_flow=200_000_000, capex=40_000_000,
            total_debt=100_000_000, total_cash=400_000_000,
            shares_outstanding=100_000_000, shares_prior=100_000_000,
            market_cap=8_000_000_000,
        )
        rows = {row["metric"]: row for row in health.build_health(f, as_json=True)["rows"]}
        self.assertEqual(rows["Cash runway"]["value"], "n/a")
        self.assertIn("self-funding", rows["Cash runway"]["read"])

    def test_composite_scores_flagged_not_faked(self):
        rows = {row["metric"]: row for row in
                health.build_health(load_fixture("NBIS"), as_json=True)["rows"]}
        self.assertEqual(rows["Altman Z-Score"]["value"], "needs line items")

    def test_exit_code_signals_availability(self):
        self.assertEqual(_exit_code(["NBIS", "--fixture"]), 0)
        self.assertEqual(_exit_code(["ZZZZ", "--fixture"]), 1)


if __name__ == "__main__":
    unittest.main()
