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


if __name__ == "__main__":
    unittest.main()
