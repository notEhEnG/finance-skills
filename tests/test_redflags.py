import contextlib
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import redflags
from data import Fundamentals, load_fixture


def _exit_code(argv):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return redflags.main(argv)


class TestRedflags(unittest.TestCase):
    def test_neocloud_trips_burn_and_leverage(self):
        r = redflags.build_redflags(load_fixture("CRWV"), as_json=True)
        flags = {x["flag"] for x in r["flags"]}
        self.assertIn("Cash burn", flags)
        self.assertIn("Elevated leverage", flags)
        self.assertGreaterEqual(r["flag_count"], 3)

    def test_clean_company_has_no_flags(self):
        f = Fundamentals(
            ticker="CLEAN", available=True, source="fixture",
            revenue=1_000_000_000, revenue_prior=800_000_000,
            gross_profit=800_000_000, ebitda=300_000_000,
            free_cash_flow=250_000_000, capex=50_000_000,
            total_debt=100_000_000, total_cash=500_000_000,
            shares_outstanding=100_000_000, shares_prior=100_000_000,
            market_cap=8_000_000_000,
        )
        r = redflags.build_redflags(f, as_json=True)
        self.assertEqual(r["flag_count"], 0)

    def test_missing_net_debt_is_flagged_not_ignored(self):
        f = Fundamentals(
            ticker="NODEBT", available=True, source="fixture",
            revenue=1_000_000_000, revenue_prior=900_000_000,
            gross_profit=700_000_000, ebitda=300_000_000,
            free_cash_flow=200_000_000, capex=40_000_000,
            total_debt=None, total_cash=None,  # net debt unknown
            shares_outstanding=100_000_000, shares_prior=100_000_000,
            market_cap=8_000_000_000,
        )
        flags = {x["flag"] for x in redflags.build_redflags(f, as_json=True)["flags"]}
        self.assertIn("Net debt unknown", flags)

    def test_text_render_has_footer(self):
        text = redflags.build_redflags(load_fixture("CRWV"), as_json=False)
        self.assertIn("red flags", text)
        self.assertIn("Not investment advice", text)

    def test_exit_code_signals_availability(self):
        self.assertEqual(_exit_code(["CRWV", "--fixture"]), 0)
        self.assertEqual(_exit_code(["ZZZZ", "--fixture"]), 1)


if __name__ == "__main__":
    unittest.main()
