from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import context
import provider_orchestrator
import providers
import workflow_cli
from data import Fundamentals


def _fact(
    value: float,
    *,
    start: str | None,
    end: str,
    filed: str,
    accession: str,
    form: str = "10-K",
    fiscal_period: str = "FY",
) -> dict:
    item = {
        "val": value,
        "end": end,
        "filed": filed,
        "accn": accession,
        "form": form,
        "fp": fiscal_period,
    }
    if start is not None:
        item["start"] = start
    return item


def _sec_payload() -> dict:
    current = {
        "start": "2025-01-01",
        "end": "2025-12-31",
        "filed": "2026-02-20",
        "accession": "0001-26-000001",
    }
    prior = {
        "start": "2024-01-01",
        "end": "2024-12-31",
        "filed": "2025-02-20",
        "accession": "0001-25-000001",
    }

    def duration(value: float, concept: str, previous: float | None = None) -> tuple[str, dict]:
        values = [
            _fact(
                value,
                start=current["start"],
                end=current["end"],
                filed=current["filed"],
                accession=current["accession"],
            )
        ]
        if previous is not None:
            values.append(
                _fact(
                    previous,
                    start=prior["start"],
                    end=prior["end"],
                    filed=prior["filed"],
                    accession=prior["accession"],
                )
            )
        return concept, {"units": {"USD": values}}

    def instant(value: float, concept: str, unit: str = "USD") -> tuple[str, dict]:
        return concept, {
            "units": {
                unit: [
                    _fact(
                        value,
                        start=None,
                        end=current["end"],
                        filed=current["filed"],
                        accession=current["accession"],
                    )
                ]
            }
        }

    facts = dict(
        [
            duration(
                100.0,
                "RevenueFromContractWithCustomerExcludingAssessedTax",
                previous=80.0,
            ),
            duration(60.0, "GrossProfit"),
            duration(90.0, "NetCashProvidedByUsedInOperatingActivities"),
            duration(20.0, "PaymentsToAcquirePropertyPlantAndEquipment"),
            duration(30.0, "OperatingIncomeLoss"),
            duration(10.0, "DepreciationDepletionAndAmortization"),
            instant(15.0, "CashAndCashEquivalentsAtCarryingValue"),
            instant(5.0, "LongTermDebtAndFinanceLeaseObligationsCurrent"),
            instant(45.0, "LongTermDebtAndFinanceLeaseObligationsNoncurrent"),
            instant(10.0, "EntityCommonStockSharesOutstanding", unit="shares"),
        ]
    )
    return {"facts": {"us-gaap": facts}}


class TestSecCompanyFacts(unittest.TestCase):
    def test_selected_cohort_and_derived_primitives(self):
        result = providers.SecCompanyFactsAdapter().normalize(
            "TEST",
            _sec_payload(),
            retrieved_at="2026-03-01T00:00:00+00:00",
        )
        observations = result.observations
        self.assertEqual(observations["revenue"]["value"], 100.0)
        self.assertEqual(observations["revenue_prior"]["value"], 80.0)
        self.assertEqual(observations["free_cash_flow"]["value"], 70.0)
        self.assertEqual(observations["ebitda"]["value"], 40.0)
        self.assertEqual(observations["total_debt"]["value"], 50.0)
        self.assertEqual(observations["revenue"]["period_end"], "2025-12-31")
        self.assertEqual(observations["free_cash_flow"]["period_end"], "2025-12-31")

    def test_cik_resolution_uses_only_fixed_endpoint(self):
        response = mock.MagicMock()
        response.read.return_value = (
            b'{"0":{"cik_str":320193,"ticker":"AAPL","title":"Apple Inc."}}'
        )
        response.__enter__.return_value = response
        with mock.patch.object(
            providers.urllib.request,
            "urlopen",
            return_value=response,
        ) as urlopen:
            cik = providers.SecCompanyFactsAdapter.fetch_cik(
                "AAPL",
                user_agent="finance-skills test@example.com",
            )
        self.assertEqual(cik, "0000320193")
        request = urlopen.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "https://www.sec.gov/files/company_tickers.json",
        )


class TestSecondaryProviders(unittest.TestCase):
    def test_ir_payload_is_normalized_as_secondary_evidence(self):
        result = providers.InvestorRelationsAdapter().normalize(
            "TEST",
            {
                "source_name": "TEST investor relations",
                "observations": [
                    {
                        "concept": "revenue",
                        "value": 100.0,
                        "definition": "reported_total_revenue",
                        "unit": "USD",
                        "currency": "USD",
                        "period_type": "annual",
                        "period_end": "2025-12-31",
                        "source_reference": "earnings-release-2025",
                    }
                ],
            },
        )
        observation = result.observations["revenue"]
        self.assertEqual(observation["source_type"], "investor_relations")
        self.assertEqual(observation["confidence"], "secondary")
        self.assertFalse(observation["is_estimate"])

    def test_estimates_are_explicit_and_separate(self):
        result = providers.EstimatesAdapter().normalize(
            {"forward_revenue": 125.0, "forward_eps": 4.5},
            currency="USD",
            period_end=None,
            retrieved_at="2026-03-01T00:00:00+00:00",
        )
        self.assertTrue(result.observations["forward_revenue"]["is_estimate"])
        self.assertEqual(result.observations["forward_eps"]["confidence"], "estimated")

    def test_period_and_currency_mismatches_are_preserved(self):
        left = {
            "revenue": {
                "value": 100.0,
                "period_type": "annual",
                "period_end": "2025-12-31",
                "currency": "USD",
            }
        }
        period_right = {
            "revenue": {
                "value": 100.0,
                "period_type": "quarterly",
                "period_end": "2025-12-31",
                "currency": "USD",
            }
        }
        result = providers.reconcile_observations(left, period_right)
        self.assertEqual(result["conflicts"][0]["status"], "period_mismatch")
        currency_right = {
            "revenue": {
                "value": 100.0,
                "period_type": "annual",
                "period_end": "2025-12-31",
                "currency": "EUR",
            }
        }
        result = providers.reconcile_observations(left, currency_right)
        self.assertEqual(result["conflicts"][0]["status"], "currency_mismatch")


class TestProviderOrchestration(unittest.TestCase):
    def setUp(self):
        self.config = {
            **context.DEFAULT_CONFIG,
            "providers": {
                "filings": {"enabled": True},
                "investor_relations": {"enabled": True},
                "market_data": {"enabled": True},
                "estimates": {"enabled": False},
            },
        }
        self.market = Fundamentals(
            ticker="TEST",
            available=True,
            source="yfinance",
            data_state="live",
            as_of="2025-12-31",
            retrieved_at="2026-03-01T00:00:00+00:00",
            currency="USD",
            name="Test Company",
            price=10.0,
            market_cap=100.0,
            revenue=95.0,
            revenue_prior=75.0,
            gross_profit=55.0,
            ebitda=35.0,
            free_cash_flow=65.0,
            capex=20.0,
            total_cash=14.0,
            total_debt=49.0,
            shares_outstanding=10.0,
            field_metadata={
                name: {
                    "source": "yfinance",
                    "period_type": "annual",
                    "period_end": "2025-12-31",
                    "currency": "USD",
                }
                for name in (
                    "revenue",
                    "revenue_prior",
                    "gross_profit",
                    "ebitda",
                    "free_cash_flow",
                    "capex",
                    "total_cash",
                    "total_debt",
                )
            },
        )

    def _patch_common(self, sec_result):
        return (
            mock.patch.object(
                provider_orchestrator.context,
                "load_project_config",
                return_value=(ROOT, self.config, "loaded"),
            ),
            mock.patch.object(
                provider_orchestrator,
                "load_for_workflow",
                return_value=self.market,
            ),
            mock.patch.object(
                provider_orchestrator,
                "_load_sec",
                return_value=(
                    sec_result,
                    {
                        "provider": "sec_company_facts",
                        "status": "success",
                        "data_mode": "live",
                    },
                    [],
                ),
            ),
            mock.patch.object(
                provider_orchestrator,
                "_load_ir",
                return_value=(
                    None,
                    {
                        "provider": "investor_relations",
                        "status": "not_configured",
                        "data_mode": "live",
                    },
                    [],
                ),
            ),
        )

    def test_filing_observations_drive_calculations_and_conflicts_remain_visible(self):
        sec_result = providers.SecCompanyFactsAdapter().normalize("TEST", _sec_payload())
        patches = self._patch_common(sec_result)
        with patches[0], patches[1], patches[2], patches[3]:
            report = provider_orchestrator.build_reconciled_report("TEST")
        self.assertEqual(report["observations"]["revenue"]["value"], 100.0)
        self.assertEqual(report["derived"]["fcf_margin_pct"]["value"], 70.0)
        self.assertTrue(report["reconciliation_conflicts"])
        self.assertEqual(report["source_summary"]["provider"], "reconciled")

    def test_estimates_require_explicit_opt_in(self):
        self.market.estimates = {"forward_revenue": 125.0}
        patches = self._patch_common(None)
        with patches[0], patches[1], patches[2], patches[3]:
            disabled = provider_orchestrator.build_reconciled_report("TEST")
            enabled = provider_orchestrator.build_reconciled_report(
                "TEST",
                include_estimates=True,
            )
        self.assertEqual(disabled["estimate_observations"], {})
        self.assertEqual(
            enabled["estimate_observations"]["forward_revenue"]["value"],
            125.0,
        )

    def test_fixture_mode_never_invokes_live_providers(self):
        with mock.patch.object(
            provider_orchestrator,
            "_load_sec",
        ) as load_sec:
            report = provider_orchestrator.build_reconciled_report(
                "CRWV",
                use_fixture=True,
            )
        load_sec.assert_not_called()
        self.assertEqual(report["data_mode"], "fixture")

    def test_cli_accepts_estimate_opt_in(self):
        args = workflow_cli.build_parser().parse_args(
            ["screen", "--ticker", "TEST", "--include-estimates"]
        )
        self.assertTrue(args.include_estimates)


if __name__ == "__main__":
    unittest.main()
