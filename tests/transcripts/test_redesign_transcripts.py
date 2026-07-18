"""Deterministic transcript matrix required by the redesign evaluation plan."""

import sys
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import evidence
import state
import workflows
from data import Fundamentals, load_fixture


def report(ticker="CRWV"):
    fundamentals = load_fixture(ticker)
    assert fundamentals is not None
    return evidence.build_evidence_report(fundamentals)


class TestRedesignTranscriptMatrix(unittest.TestCase):
    def test_company_profile_matrix(self):
        base = report()
        cases = {
            "profitable_mature": {"growth": 8, "fcf": 18, "sector": "Consumer"},
            "hypergrowth_unprofitable": {"growth": 80, "fcf": -20, "sector": "Technology"},
            "capital_intensive_cloud": {"growth": 60, "fcf": -40, "sector": "Technology"},
            "semiconductor": {"growth": 25, "fcf": 22, "sector": "Semiconductors"},
            "cyclical_industrial": {"growth": -10, "fcf": 4, "sector": "Industrials"},
            "bank_or_insurer": {"growth": 5, "fcf": None, "sector": "Financial Services"},
        }
        for name, values in cases.items():
            candidate = deepcopy(base)
            candidate["ticker"] = name.upper()[:12]
            candidate["derived"]["revenue_growth_pct"]["value"] = values["growth"]
            candidate["derived"]["fcf_margin_pct"]["value"] = values["fcf"]
            candidate["company"]["sector"] = values["sector"]
            with self.subTest(case=name):
                result = workflows.screen(candidate)
                self.assertEqual(result["workflow"], "screen")
                self.assertIn("conditional_conclusion", result)
                self.assertIn("limitations", result)

    def test_data_failure_matrix(self):
        missing_debt = report()
        missing_debt["observations"]["total_debt"]["status"] = "missing"
        missing_debt["observations"]["total_debt"]["value"] = None

        currency_mismatch = report()
        currency_mismatch["warnings"].append("currency mismatch")
        currency_mismatch["derived"]["net_debt"]["currency_alignment"] = "mismatched"

        provider_outage = evidence.build_evidence_report(
            Fundamentals(ticker="OUT", available=False, error="provider outage")
        )
        fixture_only = report()

        cases = {
            "missing_debt": workflows.audit(missing_debt),
            "mismatched_currency": workflows.audit(currency_mismatch),
            "provider_outage": workflows.screen(provider_outage),
            "fixture_only": workflows.screen(fixture_only),
        }
        self.assertTrue(cases["missing_debt"]["high_severity_findings"])
        self.assertTrue(cases["mismatched_currency"]["high_severity_findings"])
        self.assertEqual(cases["provider_outage"]["status"], "provider_error")
        self.assertIn("fixture", cases["fixture_only"]["limitations"][0])

    def test_tracked_company_improving_and_breaking(self):
        previous = report()
        previous["derived"]["revenue_growth_pct"]["value"] = 20
        previous["derived"]["fcf_margin_pct"]["value"] = 5
        previous["derived"]["share_dilution_pct"]["value"] = 1

        improving = deepcopy(previous)
        improving["derived"]["revenue_growth_pct"]["value"] = 30
        improving["derived"]["fcf_margin_pct"]["value"] = 12

        breaking = deepcopy(previous)
        breaking["derived"]["revenue_growth_pct"]["value"] = 0
        breaking["derived"]["fcf_margin_pct"]["value"] = -15
        breaking["derived"]["share_dilution_pct"]["value"] = 8

        improving_diff = state.diff_reports(previous, improving)
        breaking_diff = state.diff_reports(previous, breaking)
        self.assertEqual(improving_diff["thesis_effect"], "STRENGTHENED")
        self.assertIn(breaking_diff["thesis_effect"], {"WEAKENED", "BROKEN"})


if __name__ == "__main__":
    unittest.main()
