"""Product surface: explain, style, diagnostics, peers, rank, scenarios."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import analyze
import brief
import compare
import diagnostics
import explain
import metrics
import peers
import rank
import style
from data import Fundamentals, load_fixture


class TestExplain(unittest.TestCase):
    def test_why_lines_for_neocloud(self):
        r = analyze.build_report(load_fixture("CRWV"))
        items = explain.why_lines_for_report(r)
        keys = {i["metric"] for i in items}
        self.assertIn("rule40", keys)
        self.assertIn("fcf_margin", keys)
        self.assertIn("capital_intensity_gap", keys)
        text = "\n".join(explain.render_why(items))
        self.assertIn("Why this matters", text)


class TestStyle(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(style.normalize_style("VALUE"), "value")
        self.assertIsNone(style.normalize_style("momentum"))

    def test_brief_style_risk_json(self):
        f = load_fixture("NBIS")
        b = brief.build_brief(f, as_json=True, flags={"--style=risk"})
        self.assertEqual(b["style"], "risk")
        self.assertTrue(b["redflags"] or b["disabled"] is not None)

    def test_all_style_focus_paths(self):
        f = load_fixture("NBIS")
        payload = brief.build_brief(f, as_json=True)
        for name in style.STYLES:
            lines = style.style_focus(name, payload)
            self.assertTrue(lines, name)
            self.assertIn("Emphasis", lines[0])

    def test_brief_explain_flag(self):
        f = load_fixture("CRWV")
        b = brief.build_brief(f, as_json=True, flags={"--explain"})
        self.assertTrue(b["why"])
        text = brief.build_brief(f, as_json=False, flags={"--explain"})
        self.assertIn("Why this matters", text)
        self.assertIn("Disabled analyses", text)
        self.assertIn("Filing verification", text)


class TestDiagnostics(unittest.TestCase):
    def test_dcf_names_missing_shares(self):
        f = Fundamentals(
            ticker="X", available=True, source="fixture",
            revenue=100e6, revenue_prior=90e6,
            ebitda=20e6, free_cash_flow=10e6,
            total_debt=0.0, total_cash=0.0,
            shares_outstanding=None,
        )
        r = analyze.build_report(f)
        self.assertNotIn("dcf", r)
        self.assertIn("shares outstanding is missing", r["dcf_note"])
        disabled = diagnostics.disabled_analyses(f, r)
        dcf = next(d for d in disabled if d["analysis"] == "dcf")
        self.assertIn("shares outstanding", dcf["missing_inputs"])
        text = "\n".join(diagnostics.render_disabled(disabled))
        self.assertIn("Disabled analyses", text)
        self.assertIn("shares outstanding", text)

    def test_dcf_names_non_positive_fcf(self):
        f = load_fixture("CRWV")
        r = analyze.build_report(f)
        self.assertIn("not positive", r["dcf_note"])

    def test_sparse_fundamentals_disable_many(self):
        f = Fundamentals(ticker="SPARSE", available=True, source="fixture")
        r = analyze.build_report(f)
        disabled = diagnostics.disabled_analyses(f, r)
        names = {d["analysis"] for d in disabled}
        self.assertIn("rule40", names)
        self.assertIn("dcf", names)
        self.assertIn("revenue_growth", names)
        lines = diagnostics.render_filing_checklist(diagnostics.filing_checklist())
        self.assertTrue(any("revenue" in ln for ln in lines))

    def test_filing_checklist_present_on_brief(self):
        b = brief.build_brief(load_fixture("NBIS"), as_json=True)
        self.assertTrue(b["filing_checklist"])
        self.assertTrue(b["disabled"])  # neocloud: DCF disabled at least
        names = {c["item"] for c in b["filing_checklist"]}
        self.assertIn("free cash flow", names)
        self.assertIn("total debt", names)


class TestScenarios(unittest.TestCase):
    def test_automatic_dcf_is_disabled_on_positive_fcf(self):
        f = Fundamentals(
            ticker="Y", available=True, source="fixture",
            revenue=300e6, revenue_prior=100e6,
            ebitda=60e6, free_cash_flow=40e6,
            shares_outstanding=10e6, total_cash=0.0, total_debt=0.0,
            price=50.0, market_cap=500e6,
        )
        r = analyze.build_report(f)
        self.assertNotIn("dcf", r)
        self.assertIn("explicit FCF-growth", r["dcf_note"])
        text = analyze.format_report(r)
        self.assertIn("DCF disabled", text)

        import valuation
        vtext = valuation.build_valuation(f, as_json=False, flags={"--explain"})
        self.assertIn("explicit", vtext)
        self.assertIn("Why this matters", vtext)
        vjson = valuation.build_valuation(f, as_json=True, flags={"--explain"})
        self.assertIn("dcf_scenarios", vjson)
        self.assertIsNone(vjson["dcf_scenarios"])

    def test_pure_helper_monotonic_in_growth(self):
        a = metrics.dcf_scenarios(
            1e9, 10.0, 1e8, 0.0,
            discount_rate=10.0, terminal_growth=3.0, years=10, price=20.0,
        )
        self.assertLess(a["growth"]["bear"]["per_share"], a["growth"]["bull"]["per_share"])


class TestPeersAndRank(unittest.TestCase):
    def test_presets_resolve(self):
        r = peers.resolve_preset("ai-infra")
        self.assertIsNotNone(r)
        name, tickers = r
        self.assertEqual(name, "ai-infra")
        self.assertIn("CRWV", tickers)
        self.assertIn("NBIS", tickers)

    def test_rank_fixtures(self):
        reports = [analyze.build_report(load_fixture(t)) for t in ("CRWV", "NBIS")]
        ranking = rank.rank_reports(reports)
        self.assertEqual(ranking["n"], 2)
        self.assertIsNotNone(ranking["best_growth"])
        # NBIS has higher fixture growth
        self.assertEqual(ranking["best_growth"]["ticker"], "NBIS")
        text = "\n".join(rank.render_ranking(ranking))
        self.assertIn("Best growth", text)

    def test_compare_json_includes_ranking(self):
        reports = [analyze.build_report(load_fixture(t)) for t in ("CRWV", "NBIS")]
        out = compare.build_compare(reports, as_json=True)
        self.assertIn("ranking", out)
        self.assertEqual(out["ranking"]["best_growth"]["ticker"], "NBIS")

    def test_compare_list_presets_cli(self):
        code = compare.main(["list-presets"])
        self.assertEqual(code, 0)

    def test_compare_preset_fixture_needs_two_with_data(self):
        # Only CRWV/NBIS have fixtures; ai-infra preset has more — should still
        # compare the two that load under --fixture.
        code = compare.main(["--preset=ai-infra", "--fixture", "--json"])
        self.assertEqual(code, 0)

    def test_screen_includes_ranking(self):
        import screen
        res = screen.screen("growth > 0", ["CRWV", "NBIS"], use_fixture=True)
        self.assertIn("ranking", res)
        self.assertGreaterEqual(res["ranking"]["n"], 2)
        text = screen._render(res)
        self.assertIn("Ranking summary", text)

    def test_peers_aliases(self):
        self.assertIsNotNone(peers.resolve_preset("neocloud"))
        self.assertIsNotNone(peers.resolve_preset("faang"))
        self.assertIsNone(peers.resolve_preset("not-a-real-preset"))


if __name__ == "__main__":
    unittest.main()
