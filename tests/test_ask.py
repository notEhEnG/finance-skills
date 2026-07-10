"""One-shot ask → answer_draft (agents should stop scripting after this)."""

import json
import sys
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import agent_eval
import ask
import answer_draft


class TestAskFixture(unittest.TestCase):
    def test_nbis_buy_produces_useful_draft(self):
        out = ask.run_ask("is nbis a buy?", use_fixture=True)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["intent"], "valuation")
        self.assertEqual(out["tickers"], ["NBIS"])
        self.assertTrue(out["stop_tool_loop"])
        self.assertEqual(out["next_action"], "respond_with_answer_draft")
        draft = out["answer_draft"]
        self.assertIn("Sample/fixture", draft)
        self.assertIn("DCF", draft)
        self.assertIn("EV", draft)
        self.assertIn("not investment advice", draft.lower())
        self.assertNotRegex(draft.lower(), r"\bi('d| would) buy\b")
        hard = agent_eval.hard_fail_checks(
            draft, report=out.get("report"), expect_fixture=True, expect_dcf_disabled=True
        )
        self.assertEqual(hard, [], hard)
        soft = agent_eval.usefulness_checks(draft, intent="valuation", status="ok")
        self.assertEqual(soft, [], soft)

    def test_learn_rule_of_40(self):
        out = ask.run_ask("Explain Rule of 40", use_fixture=False)
        self.assertEqual(out["status"], "learn")
        self.assertEqual(out["intent"], "learn")
        self.assertEqual(out["tickers"], [])
        self.assertIn("Rule of 40", out["answer_draft"])
        self.assertTrue(out["stop_tool_loop"])

    def test_refuse_portfolio(self):
        out = ask.run_ask("Should I sell everything?")
        self.assertEqual(out["status"], "refuse")
        self.assertIn("personalized", out["answer_draft"].lower())

    def test_clarify_without_ticker(self):
        out = ask.run_ask("is it a buy?")
        self.assertEqual(out["status"], "clarify")
        self.assertTrue(out["needs_clarification"] if "needs_clarification" in out else True)
        self.assertIn("ticker", out["answer_draft"].lower())

    def test_brief_crwv(self):
        out = ask.run_ask("quick take on CRWV", use_fixture=True)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["intent"], "brief")
        self.assertIn("CRWV", out["tickers"])
        soft = agent_eval.usefulness_checks(
            out["answer_draft"], intent="brief", status="ok"
        )
        self.assertEqual(soft, [], soft)

    def test_json_cli(self):
        buf = StringIO()
        with mock.patch("sys.stdout", buf):
            code = ask.main(["is nbis a buy?", "--fixture", "--json"])
        self.assertEqual(code, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["tickers"], ["NBIS"])
        self.assertIn("answer_draft", data)

    def test_text_cli_prints_draft_only(self):
        buf = StringIO()
        with mock.patch("sys.stdout", buf):
            code = ask.main(["is nbis a buy?", "--fixture"])
        self.assertEqual(code, 0)
        text = buf.getvalue()
        self.assertIn("Sample/fixture", text)
        self.assertNotIn('"schema_version"', text)

    def test_doctor_runs(self):
        info = ask.doctor()
        self.assertTrue(info["sample_ask_ok"])
        self.assertIn("hints", info)


class TestAnswerDraftHelpers(unittest.TestCase):
    def test_concept_mapping(self):
        self.assertEqual(answer_draft.concept_key_from_query("what is free cash flow"), "fcf")
        self.assertEqual(answer_draft.concept_key_from_query("Explain Rule of 40"), "rule40")

    def test_usefulness_flags_empty_hedge(self):
        bad = "Not investment advice. Verify filings."
        fails = agent_eval.usefulness_checks(bad, intent="valuation", status="ok")
        self.assertTrue(fails)


if __name__ == "__main__":
    unittest.main()
