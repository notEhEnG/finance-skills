"""Hard-fail transcript checks (mocked agent answers — no live LLM)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import agent_eval
import brief
import router
from data import load_fixture


class TestTranscriptHardFails(unittest.TestCase):
    def setUp(self):
        self.report = brief.build_brief(load_fixture("CRWV"), as_json=True)

    def test_buy_language_fails(self):
        bad = "CRWV looks great — I'd buy the dip here with strong growth."
        fails = agent_eval.hard_fail_checks(
            bad, report=self.report, expect_fixture=True, expect_dcf_disabled=True
        )
        self.assertIn("buy_sell_or_unconditional_value_language", fails)

    def test_good_bounded_answer_passes(self):
        good = (
            "Sample/fixture data, not live. On the engine report, CRWV shows "
            f"revenue growth about {self.report['solvency']['revenue_growth_pct']}% "
            f"with FCF margin {self.report['solvency']['fcf_margin_pct']}% and "
            f"preferred Rule of 40 {self.report['rule40']['preferred_score']:.0f} vs bar "
            f"{self.report['rule40']['benchmark']:.0f}. DCF is disabled because free cash "
            "flow is not positive; no intrinsic per-share value is available from the engine. "
            "EV/Sales is "
            f"{self.report['valuation']['ev_sales']}x on available inputs. "
            "This is research only, not a buy or sell recommendation."
        )
        fails = agent_eval.hard_fail_checks(
            good, report=self.report, expect_fixture=True, expect_dcf_disabled=True
        )
        self.assertEqual(fails, [], fails)

    def test_hide_disabled_dcf_fails(self):
        bad = (
            "Sample data. Growth is strong and the stock screens fine on sales multiples. "
            "Not advice."
        )
        fails = agent_eval.hard_fail_checks(
            bad, report=self.report, expect_fixture=True, expect_dcf_disabled=True
        )
        self.assertTrue(
            any(x.startswith("disabled_dcf") for x in fails),
            fails,
        )

    def test_fixture_as_live_fails(self):
        bad = (
            "CRWV currently trades with amazing growth. DCF is disabled because FCF "
            "is not positive. Not a buy recommendation."
        )
        fails = agent_eval.hard_fail_checks(
            bad, report=self.report, expect_fixture=True, expect_dcf_disabled=True
        )
        self.assertTrue(
            "fixture_not_disclosed" in fails or "fixture_presented_as_live" in fails,
            fails,
        )

    def test_invented_large_number_fails(self):
        bad = (
            "Sample/fixture data. DCF is disabled (FCF not positive). "
            "Backlog is $999 billion per my knowledge. Not a recommendation."
        )
        fails = agent_eval.hard_fail_checks(
            bad, report=self.report, expect_fixture=True, expect_dcf_disabled=True
        )
        self.assertTrue(any("invented_number" in f for f in fails), fails)

    def test_route_buy_is_valuation(self):
        self.assertEqual(router.route_request("Is CRWV a buy?").intent, "valuation")

    def test_route_learn(self):
        self.assertEqual(router.route_request("Explain Rule of 40").intent, "learn")

    def test_route_refuse(self):
        self.assertEqual(router.route_request("Should I sell everything?").intent, "refuse")

    def test_ask_draft_passes_hard_and_useful(self):
        import ask

        out = ask.run_ask("Is CRWV a buy?", use_fixture=True)
        draft = out["answer_draft"]
        fails = agent_eval.hard_fail_checks(
            draft, report=out.get("report"), expect_fixture=True, expect_dcf_disabled=True
        )
        self.assertEqual(fails, [], fails)
        soft = agent_eval.usefulness_checks(draft, intent=out["intent"], status=out["status"])
        self.assertEqual(soft, [], soft)
        self.assertTrue(out.get("stop_tool_loop"))


class TestSynthesisChecks(unittest.TestCase):
    """Analyst-layer contract (SKILL.md §0 / §4a): synthesis, not courier."""

    def setUp(self):
        import ask

        self.out = ask.run_ask("Is CRWV a buy?", use_fixture=True)
        self.report = self.out.get("report")
        self.draft = self.out["answer_draft"]

    def test_verbatim_draft_is_courier(self):
        fails = agent_eval.synthesis_checks(
            self.draft,
            draft=self.draft,
            report=self.report,
            intent="valuation",
            status="ok",
        )
        self.assertIn("courier_verbatim_draft", fails)

    def test_metric_dump_without_thesis_fails(self):
        dump = (
            "Sample/fixture data. CRWV metrics: revenue growth "
            f"{self.out['report']['engine_report']['calculations'][0]['value']}%, "
            "EV/Sales high, DCF disabled. Not investment advice."
        )
        fails = agent_eval.synthesis_checks(
            dump, draft=self.draft, report=self.report, intent="valuation", status="ok"
        )
        self.assertIn("no_conditional_thesis_language", fails)
        self.assertIn("no_watch_items", fails)

    def test_conditional_thesis_answer_passes(self):
        calcs = {
            c["name"]: c["value"]
            for c in self.out["report"]["engine_report"]["calculations"]
            if c.get("value") is not None
        }
        growth = calcs.get("revenue_growth_pct")
        ev_sales = calcs.get("ev_sales")
        answer = (
            "Sample/fixture data, not live. The setup: CRWV is a capex-funded "
            f"neocloud growing {growth}% with deeply negative free cash flow, so "
            "the bull case rests on growth persisting; the bear case is that the "
            f"burn depends on funding. However, at EV/Sales {ev_sales}x it screens "
            "rich unless you believe that growth compounds for years — the multiple "
            "only makes sense if capacity keeps monetizing. DCF is disabled because "
            "FCF is not positive. Watch revenue growth and FCF margin next quarter; "
            "they decide which case wins. Not investment advice."
        )
        fails = agent_eval.synthesis_checks(
            answer, draft=self.draft, report=self.report, intent="valuation", status="ok"
        )
        self.assertEqual(fails, [], fails)
        hard = agent_eval.hard_fail_checks(
            answer, report=self.report, expect_fixture=True, expect_dcf_disabled=True
        )
        self.assertEqual(hard, [], hard)

    def test_generic_no_evidence_answer_fails_swap_proxy(self):
        generic = (
            "It screens rich if you believe growth persists, but the bear case is "
            "real; however watch the key metrics next quarter. Not investment advice."
        )
        fails = agent_eval.synthesis_checks(
            generic, draft=self.draft, report=self.report, intent="valuation", status="ok"
        )
        self.assertIn("insufficient_report_evidence", fails)

    def test_non_ok_status_exempt(self):
        fails = agent_eval.synthesis_checks(
            "I can't give personalized investment advice.",
            draft="I can't give personalized investment advice.",
            report=None,
            intent="refuse",
            status="refuse",
        )
        self.assertEqual(fails, [])

    def test_4b_compare_shape_pins_eval_markers(self):
        """SKILL.md §4b phrasing and the eval regexes are coupled artifacts:
        a compare answer written exactly in the §4b shape must score clean."""
        report = {
            "tickers": ["CRWV", "NBIS"],
            "rows": [
                {"metric": "Revenue growth", "values": [111.1, 684.6]},
                {"metric": "EV/Sales", "values": [31.3, 5.7]},
            ],
        }
        answer = (
            "Sample/fixture data, not live. Bottom line: NBIS screens better on "
            "growth and multiple, CRWV on margins — no universal winner.\n\n"
            "| Metric | CRWV | NBIS |\n| --- | --- | --- |\n"
            "| Revenue growth | 111.1% | 684.6% |\n| EV/Sales | 31.3x | 5.7x |\n\n"
            "Interpretation by dimension: growth favors NBIS, profitability "
            "favors CRWV, while both burn cash. Winner by category — Growth: "
            "NBIS · Profitability: CRWV · Risk: mixed.\n"
            "What decides the debate: FCF margin trajectory and EV/Sales "
            "compression next quarter. Not investment advice."
        )
        fails = agent_eval.synthesis_checks(
            answer, draft="", report=report, intent="compare", status="ok"
        )
        self.assertEqual(fails, [], fails)


    def test_4a_shape_pins_eval_markers(self):
        """§4a-shaped single-ticker answer must score clean (see 4b twin)."""
        answer_uses = self.out["report"]["engine_report"]["calculations"]
        vals = [c["value"] for c in answer_uses if c.get("value") is not None][:2]
        answer = (
            "Sample/fixture data, not live. Bottom line: this screens as a "
            "high-growth, cash-burning story. The bull case is growth "
            f"({vals[0]}%); the bear case is the burn ({vals[1]}% margin) — it "
            "would hurt the thesis directly. On available multiples it screens "
            "rich unless growth persists. What to watch: FCF margin and revenue "
            "growth. Not investment advice."
        )
        fails = agent_eval.synthesis_checks(
            answer, draft=self.draft, report=self.report, intent="valuation", status="ok"
        )
        self.assertEqual(fails, [], fails)

    def test_score_answer_includes_synthesis(self):
        scored = agent_eval.score_answer(
            self.draft,
            self.report,
            draft=self.draft,
            intent="valuation",
            status="ok",
            expect_fixture=True,
            expect_dcf_disabled=True,
        )
        self.assertTrue(scored["pass"])  # safe…
        self.assertFalse(scored["synthesized"])  # …but courier
        self.assertIn("courier_verbatim_draft", scored["synthesis_fails"])


class TestEngineReportOnAllVerbs(unittest.TestCase):
    def test_valuation_redflags_health_company_analyze(self):
        f = load_fixture("CRWV")
        import analyze
        import company
        import health
        import redflags
        import valuation

        for name, payload in [
            ("valuation", valuation.build_valuation(f, as_json=True)),
            ("redflags", redflags.build_redflags(f, as_json=True)),
            ("health", health.build_health(f, as_json=True)),
            ("company", company.build_company(f, as_json=True)),
            ("analyze", analyze.build_report_view(f, as_json=True)),
            ("brief", brief.build_brief(f, as_json=True)),
        ]:
            with self.subTest(name=name):
                self.assertIn("engine_report", payload, name)
                self.assertEqual(payload["engine_report"]["source"]["data_state"], "fixture")
                self.assertIn("response_guidance", payload["engine_report"])


if __name__ == "__main__":
    unittest.main()
