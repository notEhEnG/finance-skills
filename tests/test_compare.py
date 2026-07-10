import contextlib
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import analyze
import compare
from data import load_fixture


def _reports(*tickers):
    return [analyze.build_report(load_fixture(t)) for t in tickers]


def _exit_code(argv):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return compare.main(argv)


class TestCompare(unittest.TestCase):
    def test_json_has_a_value_per_ticker_per_row(self):
        r = compare.build_compare(_reports("CRWV", "NBIS"), as_json=True)
        self.assertEqual(r["tickers"], ["CRWV", "NBIS"])
        for row in r["rows"]:
            self.assertEqual(set(row["values"]), {"CRWV", "NBIS"})

    def test_numbers_match_the_engine(self):
        # A compare cell must equal the ticker's own engine number (no divergence).
        rep = analyze.build_report(load_fixture("CRWV"))
        r = compare.build_compare([rep, analyze.build_report(load_fixture("NBIS"))],
                                  as_json=True)
        growth_row = next(row for row in r["rows"] if row["metric"] == "Revenue growth")
        self.assertIn(f"{rep['derived']['revenue_growth_pct']:.1f}", growth_row["values"]["CRWV"])

    def test_text_render_aligns_and_has_footer(self):
        text = compare.build_compare(_reports("CRWV", "NBIS"), as_json=False)
        self.assertIn("CRWV", text)
        self.assertIn("NBIS", text)
        self.assertIn("Not investment advice", text)

    def test_needs_two_tickers(self):
        self.assertEqual(_exit_code(["CRWV", "--fixture"]), 2)

    def test_one_unavailable_still_compares_the_rest(self):
        self.assertEqual(_exit_code(["CRWV", "NBIS", "ZZZZ", "--fixture"]), 0)


if __name__ == "__main__":
    unittest.main()
