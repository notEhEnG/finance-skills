import contextlib
import io
import json
import sys
import unittest
import uuid
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import _entry
import detectors
import evidence
import migrations
import providers
import redesign_eval
import router
import skill_loader
import state
import validation
import workflow_cli
import workflows
from context import ContextError
from data import Fundamentals, load_fixture


def fixture_report(ticker="CRWV"):
    fundamentals = load_fixture(ticker)
    assert fundamentals is not None
    return evidence.build_evidence_report(fundamentals)


def state_report(ticker="TEST", growth=20.0, fcf=5.0, dilution=1.0):
    report = fixture_report()
    report["ticker"] = ticker
    report["data_as_of"] = "2026-06-30"
    report["derived"]["revenue_growth_pct"]["value"] = growth
    report["derived"]["fcf_margin_pct"]["value"] = fcf
    report["derived"]["share_dilution_pct"]["value"] = dilution
    return report


class TestEvidenceContract(unittest.TestCase):
    def test_observations_preserve_required_metadata(self):
        report = fixture_report()
        self.assertEqual(report["schema_version"], "2.0")
        self.assertEqual(report["data_mode"], "fixture")
        for observation in report["observations"].values():
            for field in (
                "value",
                "concept",
                "definition",
                "unit",
                "source_type",
                "source_name",
                "confidence",
                "is_estimate",
                "status",
            ):
                self.assertIn(field, observation)

    def test_derived_metrics_have_formula_and_input_paths(self):
        report = fixture_report()
        for metric in report["derived"].values():
            self.assertIn("formula", metric)
            self.assertIn("inputs", metric)
            self.assertIn("period_alignment", metric)
            self.assertIn("currency_alignment", metric)
            self.assertIn("calculation_version", metric)
            self.assertTrue(all(path.startswith("$.observations.") for path in metric["inputs"]))

    def test_unavailable_provider_is_typed_failure(self):
        report = evidence.build_evidence_report(
            Fundamentals(ticker="BAD", available=False, error="provider offline")
        )
        self.assertEqual(report["status"], "provider_error")
        self.assertEqual(report["failure"]["error_code"], "LIVE_DATA_UNAVAILABLE")


class TestDetectorContract(unittest.TestCase):
    EXPECTED_IDS = {
        *(f"FIN-DATA-{number:03d}" for number in range(1, 7)),
        *(f"FIN-CASH-{number:03d}" for number in range(1, 7)),
        *(f"FIN-BS-{number:03d}" for number in range(1, 6)),
        *(f"FIN-EQ-{number:03d}" for number in range(1, 5)),
        *(f"FIN-VAL-{number:03d}" for number in range(1, 6)),
        *(f"FIN-CLASS-{number:03d}" for number in range(1, 4)),
    }

    def test_every_specified_detector_id_is_registered(self):
        self.assertEqual({rule.rule_id for rule in detectors.RULES}, self.EXPECTED_IDS)

    def test_every_detector_returns_structured_result(self):
        results = detectors.evaluate_detectors(fixture_report(), include_clear=True)
        self.assertEqual(len(results), len(detectors.RULES))
        for result in results:
            self.assertIn(result["status"], {"triggered", "clear", "not_evaluated"})
            self.assertIn(result["severity"], {"info", "low", "medium", "high", "critical"})
            self.assertTrue(result["remediation"])
            self.assertNotIn("fraud", result["explanation"].lower())

    def test_missing_data_and_hidden_assumptions_trigger(self):
        missing = fixture_report()
        missing["observations"]["revenue"]["status"] = "missing"
        scenario = fixture_report()
        scenario["scenarios"] = {"base": {}}
        scenario["assumptions"] = {"margin_pct": 10}
        self.assertIn(
            "FIN-DATA-001",
            {item["rule_id"] for item in detectors.evaluate_detectors(missing)},
        )
        self.assertIn(
            "FIN-VAL-005",
            {item["rule_id"] for item in detectors.evaluate_detectors(scenario)},
        )

    def test_every_detector_has_positive_and_missing_evidence_fixture(self):
        for rule in detectors.RULES:
            report = fixture_report()
            report["retrieved_at"] = "2020-01-01T00:00:00Z"
            report["warnings"] = [
                "period mismatch for debt and cash",
                "currency mismatch",
            ]
            report["data_mode"] = "live"
            report["observations"]["revenue"]["confidence"] = "conflicting"
            report["observations"]["operating_cash_flow"]["value"] = -10
            report["observations"]["working_capital_change"]["value"] = 10
            report["observations"]["stock_based_compensation"]["value"] = 20
            report["observations"]["free_cash_flow"]["value"] = 5
            report["observations"]["acquisition_cash_flow"]["value"] = 10
            report["observations"]["debt_maturity_profile_available"]["value"] = False
            report["observations"]["interest_expense"]["value"] = None
            report["observations"]["current_assets"]["value"] = 110
            report["observations"]["current_assets_prior"]["value"] = 100
            report["observations"]["current_liabilities"]["value"] = 130
            report["observations"]["current_liabilities_prior"]["value"] = 100
            report["observations"]["shares_outstanding"]["value"] = 1000
            report["observations"]["shares_prior"]["value"] = 440
            report["observations"]["share_buybacks"]["value"] = 1
            report["derived"]["share_dilution_pct"]["value"] = 2
            report["derived"]["net_debt"]["value"] = 100
            report["derived"]["ebitda_margin_pct"]["value"] = 10
            report["prior_derived"] = {
                "net_debt": 50,
                "ebitda_margin_pct": 5,
            }
            report["observations"]["market_cap"]["period_end"] = "2026-07-18T00:00:00Z"
            report["observations"]["total_debt"]["period_end"] = "2025-01-01T00:00:00Z"
            report["valuation_basis"] = {
                "type": "project_threshold",
                "decisive": True,
                "mixed_trailing_forward": True,
            }
            report["scenarios"] = {"base": {}}
            report["assumptions"] = {}
            report["classification"] = {
                "inferred_from_ratios": True,
                "benchmark_applicable": False,
            }
            report["company"]["sector"] = None

            if rule.rule_id == "FIN-DATA-001":
                report["observations"]["revenue"]["status"] = "missing"
            elif rule.rule_id == "FIN-CASH-004":
                report["observations"]["operating_cash_flow"]["value"] = None
            elif rule.rule_id == "FIN-VAL-001":
                report["valuation_basis"] = None

            with self.subTest(rule=rule.rule_id):
                self.assertIs(rule.evaluate(report), True)
                self.assertIn(rule.evaluate({}), {True, False, None})


class TestProviderAdapters(unittest.TestCase):
    def test_sec_fetch_uses_fixed_validated_endpoint(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"facts": {}}'
        with mock.patch.object(
            providers.urllib.request,
            "urlopen",
            return_value=response,
        ) as urlopen:
            payload = providers.SecCompanyFactsAdapter.fetch_company_facts(
                "320193",
                user_agent="finance-skills test@example.com",
            )
        self.assertEqual(payload, {"facts": {}})
        request = urlopen.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
        )
        with self.assertRaises(ValueError):
            providers.SecCompanyFactsAdapter.fetch_company_facts(
                "../../unsafe",
                user_agent="finance-skills test@example.com",
            )

    def test_sec_adapter_derives_reconciled_fcf(self):
        def fact(value, end="2026-06-30"):
            return {"val": value, "form": "10-Q", "fp": "Q2", "end": end, "filed": "2026-07-20", "accn": "x"}

        payload = {
            "facts": {
                "us-gaap": {
                    "Revenues": {"units": {"USD": [fact(1000)]}},
                    "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [fact(300)]}},
                    "PaymentsToAcquirePropertyPlantAndEquipment": {"units": {"USD": [fact(100)]}},
                    "OperatingIncomeLoss": {"units": {"USD": [fact(150)]}},
                    "DepreciationDepletionAndAmortization": {"units": {"USD": [fact(50)]}},
                }
            }
        }
        result = providers.SecCompanyFactsAdapter().normalize("TEST", payload)
        self.assertEqual(result.observations["free_cash_flow"]["value"], 200)
        self.assertEqual(result.observations["free_cash_flow"]["confidence"], "reconciled")
        self.assertEqual(result.observations["ebitda"]["value"], 200)
        self.assertEqual(result.observations["ebitda"]["confidence"], "reconciled")

    def test_reconciliation_marks_material_conflict(self):
        left = {"revenue": {"value": 100, "confidence": "primary"}}
        right = {"revenue": {"value": 120, "confidence": "secondary"}}
        result = providers.reconcile_observations(left, right)
        self.assertEqual(result["observations"]["revenue"]["status"], "conflicting")
        self.assertEqual(len(result["conflicts"]), 1)


class TestMigrationAndAdversarialValidation(unittest.TestCase):
    def test_config_and_snapshot_migrations_are_pure(self):
        config = {"default_currency": "EUR"}
        snapshot = {"ticker": "TEST", "report": {"data_mode": "fixture"}}
        migrated_config, config_changes = migrations.migrate_config(config)
        migrated_snapshot, snapshot_changes = migrations.migrate_snapshot(snapshot)
        self.assertEqual(config, {"default_currency": "EUR"})
        self.assertNotIn("schema_version", snapshot)
        self.assertEqual(migrated_config["schema_version"], "1.0")
        self.assertIn("filings", migrated_config["providers"])
        self.assertFalse(migrated_config["providers"]["estimates"]["enabled"])
        self.assertEqual(migrated_snapshot["data_mode"], "fixture")
        self.assertTrue(config_changes)
        self.assertTrue(snapshot_changes)

    def test_metric_company_period_currency_and_sign_swaps_fail(self):
        report = fixture_report()
        report["derived"]["fcf_margin_pct"]["value"] = abs(
            report["derived"]["fcf_margin_pct"]["value"]
        )
        report["observations"]["revenue"]["period_type"] = "ttm"
        report["observations"]["revenue_prior"]["period_type"] = "annual"
        report["observations"]["total_cash"]["currency"] = "EUR"
        result = validation.validate_report(report, expected_ticker="OTHER")
        self.assertFalse(result["valid"])
        joined = " ".join(result["errors"])
        self.assertIn("identity mismatch", joined)
        self.assertIn("fcf_margin_pct", joined)
        self.assertIn("period association", joined)
        self.assertIn("currency association", joined)

    def test_unsupported_causality_and_disabled_override_fail(self):
        report = fixture_report()
        claims = [{
            "claim": "Capex rose because demand accelerated.",
            "claim_type": "causal",
            "evidence_paths": ["$.observations.capex"],
        }]
        self.assertIn("unsupported causality", " ".join(validation.validate_claims(report, claims)))
        self.assertIn(
            "disabled automatic DCF",
            " ".join(validation.validate_disabled_analyses(
                report, {"intrinsic_value": 123}
            )),
        )

    def test_evaluation_targets_and_distribution_matrix(self):
        report = fixture_report()
        findings = detectors.evaluate_detectors(report)
        response = {
            "workflow": "screen",
            "ticker": report["ticker"],
            "claims": [{
                "claim": "Revenue growth is grounded.",
                "claim_type": "quantitative",
                "evidence_paths": ["$.derived.revenue_growth_pct"],
            }],
            "preserved_finding_ids": [
                item["rule_id"] for item in findings
                if item["severity"] in {"high", "critical"}
            ],
        }
        result = redesign_eval.evaluate_transcript(report, response)
        self.assertTrue(result["passed"])
        matrix = redesign_eval.adapter_support_matrix(ROOT)
        self.assertEqual(len(matrix), 5)
        self.assertTrue(all(item["command_contract"] == "passing" for item in matrix))
        self.assertTrue(all(item["eval"] == "unpublished" for item in matrix))


class TestWorkflowContract(unittest.TestCase):
    def test_primary_console_no_argument_loads_context(self):
        output = io.StringIO()
        original = sys.argv
        sys.argv = ["finance"]
        try:
            with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as raised:
                _entry.run()
        finally:
            sys.argv = original
        self.assertEqual(raised.exception.code, 0)
        self.assertIn("Recommended next actions", output.getvalue())
        self.assertNotIn("Fundamentals (derived)", output.getvalue())

    def test_router_dispatches_exact_redesigned_cli(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = router.main([
                "screen",
                "--ticker",
                "CRWV",
                "--fixture",
                "--format",
                "json",
            ])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["workflow"], "screen")

    def test_exactly_one_allowlisted_workflow_reference_loads(self):
        for command in skill_loader.WORKFLOW_REFERENCES:
            content = skill_loader.load_workflow(command)
            self.assertIn(f"Workflow — {command}", content)
        with self.assertRaises(ValueError):
            skill_loader.load_workflow("../../unsafe")
        self.assertIn(
            "Fundamental-analysis specialist",
            skill_loader.load_specialist(
                "fundamental_analyst",
                workflow="underwrite",
            ),
        )
        with self.assertRaises(ValueError):
            skill_loader.load_specialist(
                "fundamental_analyst",
                workflow="screen",
            )

    def test_redesigned_router_uses_workflow_intents(self):
        cases = {
            "NVDA": "screen",
            "deep dive NVDA": "underwrite",
            "audit NVDA": "audit",
            "compare NVDA AMD": "compare",
            "challenge NVDA": "challenge",
            "scenario NVDA": "stress",
            "track NVDA": "track",
            "refresh NVDA": "refresh",
            "explain free cash flow": "explain",
        }
        for query, expected in cases.items():
            with self.subTest(query=query):
                self.assertEqual(router.route_finance_request(query).intent, expected)

    def test_screen_and_underwrite_are_evidence_grounded(self):
        report = fixture_report()
        screen = workflows.screen(report)
        underwrite = workflows.underwrite(report)
        self.assertEqual(screen["workflow"], "screen")
        self.assertTrue(screen["risks"])
        self.assertTrue(
            all(claim["evidence_paths"] for claim in screen["strengths"] + screen["risks"])
        )
        self.assertEqual(len(underwrite["specialist_packets"]), 3)
        self.assertIn("core_assumption", underwrite)
        self.assertIn("disconfirming_conditions", underwrite)

    def test_compare_blocks_period_mismatch(self):
        first, second = fixture_report("CRWV"), fixture_report("NBIS")
        second["data_as_of"] = "different-period"
        result = workflows.compare([first, second])
        self.assertEqual(result["status"], "period_mismatch")
        self.assertTrue(result["comparison_blocked"])
        self.assertEqual(result["dimensions"], {})

    def test_stress_requires_and_displays_all_assumptions(self):
        report = fixture_report()
        missing = workflows.stress(report, {"margin_pct": 10})
        self.assertEqual(missing["status"], "unsupported_analysis")
        assumptions = {
            "revenue_growth_pct": 20,
            "margin_pct": 15,
            "valuation_multiple": 8,
            "dilution_pct": 2,
            "net_debt": 100,
            "horizon_years": 3,
        }
        result = workflows.stress(report, assumptions)
        self.assertEqual(result["status"], "success")
        self.assertEqual(set(result["assumptions"]), set(assumptions))
        self.assertIn("scenario_adjustments", result)
        self.assertIn("not a forecast or price target", result["scenarios"]["base"]["label"])
        self.assertNotIn(
            "FIN-VAL-005",
            {item["rule_id"] for item in result["detector_findings"]},
        )

    def test_explain_supported_and_unsupported_topics(self):
        self.assertEqual(workflows.explain("FCF")["topic"], "free cash flow")
        self.assertEqual(workflows.explain("astrology")["status"], "unsupported_analysis")

    def test_exact_cli_screen_contract(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = workflow_cli.main(
                ["screen", "--ticker", "CRWV", "--fixture", "--format", "json"]
            )
        payload = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["workflow"], "screen")
        self.assertEqual(payload["evidence_report"]["data_mode"], "fixture")


class TestImmutableState(unittest.TestCase):
    def _root(self):
        root = Path("/tmp") / f"finance-skills-state-{uuid.uuid4().hex}"
        root.mkdir()
        with (root / "pyproject.toml").open("x", encoding="utf-8") as handle:
            handle.write("[project]\nname='state-test'\n")
        return root

    def test_snapshot_is_immutable_and_duplicate_safe(self):
        root = self._root()
        report = state_report()
        first = state.create_snapshot(report, project_root=root)
        second = state.create_snapshot(report, project_root=root)
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(first["snapshot"]["report_hash"], second["snapshot"]["report_hash"])
        self.assertEqual(len(list((root / ".finance/companies/TEST/history").iterdir())), 1)

    def test_material_diff_and_refresh_proposal(self):
        root = self._root()
        previous = state_report(growth=30, fcf=10, dilution=1)
        state.create_snapshot(previous, project_root=root)
        current = state_report(growth=10, fcf=-5, dilution=5)
        result = state.refresh(current, project_root=root)
        self.assertEqual(result["workflow"], "refresh")
        self.assertIn(result["thesis_effect"], {"WEAKENED", "BROKEN"})
        self.assertTrue(result["material_changes"])
        self.assertIn("proposed_thesis_update", result)
        self.assertTrue((root / ".finance/companies/TEST/thesis.md").is_file())
        self.assertTrue((root / ".finance/companies/TEST/refresh-log.md").is_file())


class TestRedesignSecurity(unittest.TestCase):
    def test_permissions_are_exact_for_source_and_distributions(self):
        paths = [ROOT / "SKILL.md", ROOT / "skill/SKILL.src.md"]
        paths.extend((ROOT / "dist" / provider / "SKILL.md") for provider in (
            "claude", "codex", "cursor", "gemini", "generic"
        ))
        paths.extend((ROOT / "dist" / "0.14.0" / provider / "SKILL.md") for provider in (
            "claude", "codex", "cursor", "gemini", "generic"
        ))
        for path in paths:
            content = path.read_text(encoding="utf-8")
            self.assertNotIn("Bash(python3 *)", content)
            self.assertNotIn("Bash(python *)", content)

    def test_unknown_workflow_command_is_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                workflow_cli.main(["arbitrary-python"])

    def test_state_rejects_symlink_escape(self):
        root = Path("/tmp") / f"finance-skills-symlink-{uuid.uuid4().hex}"
        outside = Path("/tmp") / f"finance-skills-outside-{uuid.uuid4().hex}"
        root.mkdir()
        outside.mkdir()
        (root / ".finance").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ContextError):
            state.create_snapshot(state_report(), project_root=root)

    def test_provider_text_is_data_not_code(self):
        payload = {
            "facts": {
                "us-gaap": {
                    "Revenues": {
                        "units": {
                            "USD": [{
                                "val": "__import__('os').system('echo unsafe')",
                                "form": "10-Q",
                                "fp": "Q2",
                                "end": "2026-06-30",
                                "filed": "2026-07-20",
                                "accn": "x",
                            }]
                        }
                    }
                }
            }
        }
        result = providers.SecCompanyFactsAdapter().normalize("TEST", payload)
        self.assertEqual(
            result.observations["revenue"]["value"],
            "__import__('os').system('echo unsafe')",
        )


if __name__ == "__main__":
    unittest.main()
