"""P2: canonical EngineReport envelope + projection consistency."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import analyze
import brief
import report_schema
from data import Fundamentals, load_fixture


class TestEngineReportEnvelope(unittest.TestCase):
    def test_fixture_brief_has_schema(self):
        f = load_fixture("CRWV")
        payload = brief.build_brief(f, as_json=True)
        self.assertEqual(payload["schema_version"], report_schema.SCHEMA_VERSION)
        eng = payload["engine_report"]
        self.assertEqual(eng["source"]["data_state"], "fixture")
        self.assertIn("fixture_sample_data_not_live", eng["response_guidance"]["mandatory_caveats"])
        self.assertIn("label_fixture_as_live", eng["response_guidance"]["prohibited_claims"])
        # DCF disabled on CRWV fixture
        names = {d["analysis"] for d in eng["disabled_analyses"]}
        self.assertIn("dcf", names)
        self.assertIn("intrinsic_value_per_share_claim", eng["response_guidance"]["prohibited_claims"])

    def test_invalid_ticker_unavailable(self):
        f = Fundamentals(ticker="ZZZZ", available=False, error="no data")
        rep = analyze.build_report(f)
        env = report_schema.envelope_from_build_report(rep)
        self.assertEqual(env["source"]["data_state"], "unavailable")
        self.assertTrue(env["errors"])
        self.assertEqual(env["company"]["status"], "unavailable")

    def test_disabled_dcf_metric_status(self):
        f = load_fixture("NBIS")
        rep = analyze.build_report(f)
        env = report_schema.envelope_from_build_report(rep)
        dcf_metrics = [c for c in env["calculations"] if c["name"] == "dcf_per_share"]
        self.assertTrue(dcf_metrics)
        self.assertEqual(dcf_metrics[0]["status"], "disabled")
        self.assertIsNone(dcf_metrics[0]["value"])

    def test_positive_fcf_enables_dcf_calculation(self):
        f = Fundamentals(
            ticker="Y", available=True, source="yfinance",
            revenue=300e6, revenue_prior=100e6,
            ebitda=60e6, free_cash_flow=40e6,
            shares_outstanding=10e6, total_cash=0.0, total_debt=0.0,
            price=50.0, market_cap=500e6, name="Y Co",
        )
        rep = analyze.build_report(f)
        self.assertIn("dcf", rep)
        env = report_schema.envelope_from_build_report(rep)
        dcf_m = next(c for c in env["calculations"] if c["name"] == "dcf_per_share")
        self.assertEqual(dcf_m["status"], "live")
        self.assertIsNotNone(dcf_m["value"])

    def test_projection_shares_legacy_derived(self):
        f = load_fixture("CRWV")
        legacy = analyze.build_report(f)
        b = brief.build_brief(f, as_json=True)
        self.assertEqual(b["solvency"]["revenue_growth_pct"], legacy["derived"]["revenue_growth_pct"])
        self.assertEqual(b["valuation"]["ev_sales"], legacy["derived"]["ev_sales"])

    def test_json_schema_file_exists(self):
        path = Path(__file__).resolve().parent.parent / "docs" / "engine-report.schema.json"
        self.assertTrue(path.is_file())
        schema = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("schema_version", schema["required"])

    def test_never_encode_missing_net_debt_as_zero(self):
        f = Fundamentals(
            ticker="X", available=True, source="fixture",
            revenue=100e6, revenue_prior=90e6,
            ebitda=20e6, free_cash_flow=10e6,
            shares_outstanding=10e6, total_debt=1e6, total_cash=None,
        )
        rep = analyze.build_report(f)
        self.assertIsNone(rep["derived"]["net_debt"])
        env = report_schema.envelope_from_build_report(rep)
        nd = next(c for c in env["calculations"] if c["name"] == "net_debt")
        self.assertEqual(nd["status"], "unavailable")
        self.assertIsNone(nd["value"])


class TestAgentPolicyDocs(unittest.TestCase):
    def test_skill_and_policy_exist(self):
        root = Path(__file__).resolve().parent.parent
        skill = (root / "SKILL.md").read_text(encoding="utf-8")
        policy = (root / "docs" / "agent-policy.md").read_text(encoding="utf-8")
        for needle in (
            "MUST invoke",
            "allowed source of numerical",
            "refuse",
            "fixture",
            "buy",
            "untrusted",
            "route --json",
        ):
            self.assertIn(needle.lower(), skill.lower(), needle)
        self.assertIn("Bad answer", policy)
        self.assertIn("Should I sell everything", policy)


if __name__ == "__main__":
    unittest.main()
