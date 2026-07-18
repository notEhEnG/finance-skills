"""Provider adapters for filing, market-data, assumption, and fixture evidence.

Adapters normalize supplied provider payloads. Network access remains confined to
the existing data shell; these classes never fetch arbitrary URLs.
"""

from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

if __package__:
    from finance_skills.evidence import FinancialObservation
else:
    from evidence import FinancialObservation


@dataclass(frozen=True)
class ProviderResult:
    provider: str
    data_mode: str
    observations: dict[str, dict[str, Any]]
    warnings: list[str]
    confidence_statistics: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "data_mode": self.data_mode,
            "observations": self.observations,
            "warnings": self.warnings,
            "confidence_statistics": self.confidence_statistics,
        }


class SecCompanyFactsAdapter:
    """Fetch and normalize fixed SEC Company Facts resources."""

    CONCEPTS: dict[str, tuple[tuple[str, ...], str, str]] = {
        "revenue": (
            (
                "RevenueFromContractWithCustomerExcludingAssessedTax",
                "SalesRevenueNet",
                "Revenues",
            ),
            "reported_total_revenue",
            "USD",
        ),
        "gross_profit": (("GrossProfit",), "reported_gross_profit", "USD"),
        "operating_cash_flow": (
            ("NetCashProvidedByUsedInOperatingActivities",),
            "reported_cash_from_operating_activities",
            "USD",
        ),
        "capex": (
            ("PaymentsToAcquirePropertyPlantAndEquipment",),
            "reported_property_plant_and_equipment_purchases",
            "USD",
        ),
        "net_income": (("NetIncomeLoss",), "reported_net_income", "USD"),
        "operating_income": (
            ("OperatingIncomeLoss",),
            "reported_operating_income",
            "USD",
        ),
        "depreciation_and_amortization": (
            (
                "DepreciationDepletionAndAmortization",
                "DepreciationDepletionAndAmortizationPropertyPlantAndEquipment",
            ),
            "reported_depreciation_and_amortization",
            "USD",
        ),
        "total_cash": (
            ("CashAndCashEquivalentsAtCarryingValue",),
            "reported_cash_and_cash_equivalents",
            "USD",
        ),
        "total_debt": (
            ("LongTermDebtAndFinanceLeaseObligations", "LongTermDebt"),
            "reported_total_debt",
            "USD",
        ),
        "debt_current": (
            ("LongTermDebtAndFinanceLeaseObligationsCurrent", "LongTermDebtCurrent"),
            "reported_current_debt",
            "USD",
        ),
        "debt_noncurrent": (
            (
                "LongTermDebtAndFinanceLeaseObligationsNoncurrent",
                "LongTermDebtNoncurrent",
            ),
            "reported_noncurrent_debt",
            "USD",
        ),
        "stock_based_compensation": (
            ("ShareBasedCompensation",),
            "reported_stock_based_compensation",
            "USD",
        ),
        "shares_outstanding": (
            ("EntityCommonStockSharesOutstanding",),
            "reported_common_shares_outstanding",
            "shares",
        ),
        "current_assets": (("AssetsCurrent",), "reported_current_assets", "USD"),
        "current_liabilities": (
            ("LiabilitiesCurrent",),
            "reported_current_liabilities",
            "USD",
        ),
        "interest_expense": (
            ("InterestExpenseNonOperating", "InterestExpense"),
            "reported_interest_expense",
            "USD",
        ),
        "share_buybacks": (
            ("PaymentsForRepurchaseOfCommonStock",),
            "reported_share_repurchase_cash_flow",
            "USD",
        ),
    }

    INSTANT_CONCEPTS = {
        "total_cash",
        "total_debt",
        "debt_current",
        "debt_noncurrent",
        "shares_outstanding",
        "current_assets",
        "current_liabilities",
    }

    @staticmethod
    def fetch_company_facts(
        cik: str,
        *,
        user_agent: str,
        timeout_seconds: float = 15.0,
    ) -> dict[str, Any]:
        """Fetch one fixed SEC Company Facts endpoint with validated inputs."""
        normalized_cik = cik.strip().lstrip("0") or "0"
        if not re.fullmatch(r"\d{1,10}", normalized_cik):
            raise ValueError(f"invalid SEC CIK: {cik!r}")
        if not user_agent.strip() or "@" not in user_agent:
            raise ValueError("SEC user agent must include a contact email")
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(normalized_cik):010d}.json"
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": user_agent.strip(),
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("SEC Company Facts response is not an object")
        return payload

    @staticmethod
    def fetch_cik(
        ticker: str,
        *,
        user_agent: str,
        timeout_seconds: float = 15.0,
    ) -> str:
        """Resolve a ticker through the SEC's fixed company-ticker resource."""
        normalized = ticker.strip().upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9._-]{0,15}", normalized):
            raise ValueError(f"invalid ticker: {ticker!r}")
        if not user_agent.strip() or "@" not in user_agent:
            raise ValueError("SEC user agent must include a contact email")
        request = urllib.request.Request(
            "https://www.sec.gov/files/company_tickers.json",
            headers={"User-Agent": user_agent.strip(), "Accept": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("SEC company ticker response is not an object")
        for item in payload.values():
            if (
                isinstance(item, dict)
                and str(item.get("ticker") or "").upper() == normalized
                and isinstance(item.get("cik_str"), int)
            ):
                return f"{item['cik_str']:010d}"
        raise ValueError(f"SEC CIK not found for ticker {normalized}")

    @classmethod
    def _fact_candidates(
        cls,
        payload: dict[str, Any],
        xbrl_concepts: tuple[str, ...],
        unit: str,
    ) -> list[dict[str, Any]]:
        accepted: list[dict[str, Any]] = []
        gaap = (payload.get("facts") or {}).get("us-gaap") or {}
        for xbrl_concept in xbrl_concepts:
            facts = gaap.get(xbrl_concept) or {}
            for item in (facts.get("units") or {}).get(unit) or []:
                if item.get("form") in {"10-K", "10-Q"} and item.get("val") is not None:
                    accepted.append({**item, "_xbrl_concept": xbrl_concept})
        return accepted

    @classmethod
    def _latest_fact(
        cls,
        payload: dict[str, Any],
        xbrl_concepts: tuple[str, ...],
        unit: str,
        *,
        anchor: dict[str, Any] | None = None,
        instant: bool = False,
    ) -> dict[str, Any] | None:
        accepted = cls._fact_candidates(payload, xbrl_concepts, unit)
        if anchor is not None:
            if instant:
                accepted = [
                    item
                    for item in accepted
                    if item.get("accn") == anchor.get("accn")
                    and item.get("end") == anchor.get("end")
                ]
            else:
                accepted = [
                    item
                    for item in accepted
                    if item.get("accn") == anchor.get("accn")
                    and item.get("start") == anchor.get("start")
                    and item.get("end") == anchor.get("end")
                ]
        if not accepted:
            return None
        return max(
            accepted,
            key=lambda item: (
                str(item.get("end") or ""),
                str(item.get("filed") or ""),
                str(item.get("accn") or ""),
            ),
        )

    @classmethod
    def _prior_comparable_revenue(
        cls,
        payload: dict[str, Any],
        anchor: dict[str, Any],
    ) -> dict[str, Any] | None:
        concepts = cls.CONCEPTS["revenue"][0]
        candidates = cls._fact_candidates(payload, concepts, "USD")
        try:
            anchor_duration = (
                date.fromisoformat(str(anchor["end"]))
                - date.fromisoformat(str(anchor["start"]))
            ).days
        except (KeyError, TypeError, ValueError):
            return None
        comparable = []
        anchor_end = anchor.get("end")
        if not isinstance(anchor_end, str):
            return None
        for item in candidates:
            item_end = item.get("end")
            if not isinstance(item_end, str) or item_end >= anchor_end:
                continue
            if item.get("form") != anchor.get("form") or item.get("fp") != anchor.get("fp"):
                continue
            try:
                duration = (
                    date.fromisoformat(str(item["end"]))
                    - date.fromisoformat(str(item["start"]))
                ).days
            except (KeyError, TypeError, ValueError):
                continue
            if abs(duration - anchor_duration) <= 10:
                comparable.append(item)
        return max(comparable, key=lambda item: str(item.get("end") or "")) if comparable else None

    @staticmethod
    def _period_type(fact: dict[str, Any]) -> str:
        if fact.get("form") == "10-K" or fact.get("fp") == "FY":
            return "annual"
        try:
            duration = (
                date.fromisoformat(str(fact["end"]))
                - date.fromisoformat(str(fact["start"]))
            ).days
        except (KeyError, TypeError, ValueError):
            return "quarterly"
        return "ytd" if duration > 120 else "quarterly"

    def normalize(
        self,
        ticker: str,
        payload: dict[str, Any],
        *,
        retrieved_at: str | None = None,
    ) -> ProviderResult:
        retrieved = retrieved_at or datetime.now(timezone.utc).isoformat()
        observations: dict[str, dict[str, Any]] = {}
        warnings: list[str] = []
        revenue_concepts = self.CONCEPTS["revenue"][0]
        anchor = self._latest_fact(payload, revenue_concepts, "USD")
        if anchor is None:
            warnings.append("SEC filing cohort unavailable: revenue anchor not found")
        for concept, (xbrl_concepts, definition, unit) in self.CONCEPTS.items():
            fact = (
                self._latest_fact(
                    payload,
                    xbrl_concepts,
                    unit,
                    anchor=anchor,
                    instant=concept in self.INSTANT_CONCEPTS,
                )
                if anchor is not None
                else None
            )
            if fact is None:
                warnings.append(
                    "SEC concept unavailable in selected cohort: "
                    + "/".join(xbrl_concepts)
                )
                continue
            value = fact["val"]
            if concept in {"capex", "interest_expense", "share_buybacks"} and isinstance(
                value,
                (int, float),
            ):
                value = abs(value)
            observations[concept] = FinancialObservation(
                value=value,
                concept=concept,
                definition=definition,
                unit=unit,
                currency="USD" if unit == "USD" else None,
                period_type=(
                    "point_in_time"
                    if concept in self.INSTANT_CONCEPTS
                    else self._period_type(fact)
                ),
                period_start=fact.get("start"),
                period_end=fact.get("end"),
                source_type="regulatory_filing",
                source_name="SEC XBRL Company Facts",
                source_reference=fact.get("accn"),
                retrieved_at=retrieved,
                confidence="primary",
                is_estimate=False,
            ).to_dict()
        if anchor is not None:
            prior_revenue = self._prior_comparable_revenue(payload, anchor)
            if prior_revenue is not None:
                observations["revenue_prior"] = FinancialObservation(
                    value=prior_revenue["val"],
                    concept="revenue_prior",
                    definition="reported_total_revenue_prior_comparable_period",
                    unit="USD",
                    currency="USD",
                    period_type=self._period_type(prior_revenue),
                    period_start=prior_revenue.get("start"),
                    period_end=prior_revenue.get("end"),
                    source_type="regulatory_filing",
                    source_name="SEC XBRL Company Facts",
                    source_reference=prior_revenue.get("accn"),
                    retrieved_at=retrieved,
                    confidence="primary",
                    is_estimate=False,
                ).to_dict()
            else:
                warnings.append("SEC prior comparable revenue unavailable")
        self._derive_total_debt(observations, retrieved)
        self._derive_fcf(observations, retrieved)
        self._derive_ebitda(observations, retrieved)
        return ProviderResult(
            provider="sec_company_facts",
            data_mode="live",
            observations=observations,
            warnings=warnings,
            confidence_statistics={
                "primary": len(observations),
                "reconciled": sum(
                    item.get("confidence") == "reconciled" for item in observations.values()
                ),
                "missing": len(warnings),
            },
        )

    @staticmethod
    def _derive_total_debt(
        observations: dict[str, dict[str, Any]],
        retrieved_at: str,
    ) -> None:
        if "total_debt" in observations:
            return
        current = observations.get("debt_current")
        noncurrent = observations.get("debt_noncurrent")
        if not current or not noncurrent or current.get("period_end") != noncurrent.get("period_end"):
            return
        observations["total_debt"] = FinancialObservation(
            value=float(current["value"]) + float(noncurrent["value"]),
            concept="total_debt",
            definition="current_debt_plus_noncurrent_debt",
            unit="USD",
            currency="USD",
            period_type="point_in_time",
            period_start=None,
            period_end=current.get("period_end"),
            source_type="regulatory_filing",
            source_name="SEC XBRL derived",
            source_reference=current.get("source_reference"),
            retrieved_at=retrieved_at,
            confidence="reconciled",
            is_estimate=False,
        ).to_dict()

    @staticmethod
    def _derive_fcf(observations: dict[str, dict[str, Any]], retrieved_at: str) -> None:
        operating = observations.get("operating_cash_flow")
        capex = observations.get("capex")
        if not operating or not capex:
            return
        if operating.get("period_end") != capex.get("period_end"):
            return
        observations["free_cash_flow"] = FinancialObservation(
            value=float(operating["value"]) - float(capex["value"]),
            concept="free_cash_flow",
            definition="operating_cash_flow_minus_capex",
            unit="USD",
            currency="USD",
            period_type=operating.get("period_type"),
            period_start=operating.get("period_start"),
            period_end=operating.get("period_end"),
            source_type="regulatory_filing",
            source_name="SEC XBRL derived",
            source_reference=operating.get("source_reference"),
            retrieved_at=retrieved_at,
            confidence="reconciled",
            is_estimate=False,
        ).to_dict()

    @staticmethod
    def _derive_ebitda(observations: dict[str, dict[str, Any]], retrieved_at: str) -> None:
        operating_income = observations.get("operating_income")
        depreciation = observations.get("depreciation_and_amortization")
        if not operating_income or not depreciation:
            return
        if operating_income.get("period_end") != depreciation.get("period_end"):
            return
        observations["ebitda"] = FinancialObservation(
            value=float(operating_income["value"]) + float(depreciation["value"]),
            concept="ebitda",
            definition="operating_income_plus_depreciation_and_amortization",
            unit="USD",
            currency="USD",
            period_type=operating_income.get("period_type"),
            period_start=operating_income.get("period_start"),
            period_end=operating_income.get("period_end"),
            source_type="regulatory_filing",
            source_name="SEC XBRL derived",
            source_reference=operating_income.get("source_reference"),
            retrieved_at=retrieved_at,
            confidence="reconciled",
            is_estimate=False,
        ).to_dict()


class InvestorRelationsAdapter:
    """Normalize project-local IR disclosures without fetching their references."""

    _CONCEPT_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

    def normalize(
        self,
        ticker: str,
        payload: dict[str, Any],
        *,
        retrieved_at: str | None = None,
    ) -> ProviderResult:
        del ticker
        retrieved = retrieved_at or datetime.now(timezone.utc).isoformat()
        raw_observations = payload.get("observations")
        if not isinstance(raw_observations, list):
            raise ValueError("IR payload observations must be a list")
        observations: dict[str, dict[str, Any]] = {}
        warnings: list[str] = []
        for index, item in enumerate(raw_observations):
            if not isinstance(item, dict):
                warnings.append(f"IR observation {index} is not an object")
                continue
            concept = item.get("concept")
            value = item.get("value")
            required_text = (
                item.get("definition"),
                item.get("unit"),
                item.get("period_end"),
                item.get("source_reference"),
            )
            if (
                not isinstance(concept, str)
                or not self._CONCEPT_RE.fullmatch(concept)
                or not isinstance(value, (int, float, bool))
                or not all(isinstance(part, str) and part.strip() for part in required_text)
            ):
                warnings.append(f"IR observation {index} failed schema validation")
                continue
            currency = item.get("currency")
            if currency is not None and (
                not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency)
            ):
                warnings.append(f"IR observation {index} has invalid currency")
                continue
            observations[concept] = FinancialObservation(
                value=value,
                concept=concept,
                definition=str(item["definition"]),
                unit=str(item["unit"]),
                currency=currency,
                period_type=str(item.get("period_type") or "reported"),
                period_start=(
                    str(item["period_start"]) if item.get("period_start") is not None else None
                ),
                period_end=str(item["period_end"]),
                source_type="investor_relations",
                source_name=str(payload.get("source_name") or "company investor relations"),
                source_reference=str(item["source_reference"]),
                retrieved_at=retrieved,
                confidence="secondary",
                is_estimate=False,
            ).to_dict()
        return ProviderResult(
            provider="investor_relations",
            data_mode="live",
            observations=observations,
            warnings=warnings,
            confidence_statistics={
                "secondary": len(observations),
                "missing": len(warnings),
            },
        )


class EstimatesAdapter:
    """Normalize explicitly enabled provider estimates as non-reported evidence."""

    ALLOWED = {
        "forward_revenue",
        "forward_eps",
        "earnings_growth_estimate_pct",
        "revenue_growth_estimate_pct",
    }

    def normalize(
        self,
        estimates: dict[str, float],
        *,
        currency: str | None,
        period_end: str | None,
        retrieved_at: str | None,
    ) -> ProviderResult:
        observations: dict[str, dict[str, Any]] = {}
        warnings: list[str] = []
        for concept, value in estimates.items():
            if concept not in self.ALLOWED or not isinstance(value, (int, float)):
                warnings.append(f"Unsupported estimate ignored: {concept}")
                continue
            is_currency = concept == "forward_revenue"
            observations[concept] = FinancialObservation(
                value=value,
                concept=concept,
                definition="provider_consensus_estimate",
                unit=currency or "currency" if is_currency else (
                    "per_share" if concept == "forward_eps" else "percent"
                ),
                currency=currency if is_currency else None,
                period_type="forward",
                period_start=None,
                period_end=period_end,
                source_type="estimates_provider",
                source_name="yfinance estimates",
                source_reference=None,
                retrieved_at=retrieved_at,
                confidence="estimated",
                is_estimate=True,
            ).to_dict()
        return ProviderResult(
            provider="market_estimates",
            data_mode="live",
            observations=observations,
            warnings=warnings,
            confidence_statistics={
                "estimated": len(observations),
                "missing": len(warnings),
            },
        )


class AssumptionAdapter:
    """Normalize explicit user assumptions without relabelling them as reported."""

    def normalize(self, assumptions: dict[str, float]) -> ProviderResult:
        retrieved = datetime.now(timezone.utc).isoformat()
        observations = {
            concept: FinancialObservation(
                value=value,
                concept=concept,
                definition="explicit_user_assumption",
                unit="assumption",
                currency=None,
                period_type="scenario",
                period_start=None,
                period_end=None,
                source_type="user_assumption",
                source_name="explicit user assumptions",
                source_reference=None,
                retrieved_at=retrieved,
                confidence="estimated",
                is_estimate=True,
            ).to_dict()
            for concept, value in assumptions.items()
        }
        return ProviderResult(
            provider="user_assumption",
            data_mode="user_assumption",
            observations=observations,
            warnings=[],
            confidence_statistics={"estimated": len(observations)},
        )


def reconcile_observations(
    primary: dict[str, dict[str, Any]],
    secondary: dict[str, dict[str, Any]],
    *,
    relative_tolerance_pct: float = 1.0,
) -> dict[str, Any]:
    """Compare two normalized sources without silently choosing a winner."""
    reconciled: dict[str, Any] = {}
    conflicts: list[dict[str, Any]] = []
    for concept in sorted(set(primary) | set(secondary)):
        left, right = primary.get(concept), secondary.get(concept)
        if left is None or right is None:
            reconciled[concept] = left or right
            continue
        left_period = (left.get("period_type"), left.get("period_end"))
        right_period = (right.get("period_type"), right.get("period_end"))
        if all(left_period) and all(right_period) and left_period != right_period:
            conflicts.append(
                {
                    "concept": concept,
                    "primary": left.get("value"),
                    "secondary": right.get("value"),
                    "primary_period": left_period,
                    "secondary_period": right_period,
                    "status": "period_mismatch",
                }
            )
            reconciled[concept] = dict(left)
            continue
        left_currency = left.get("currency")
        right_currency = right.get("currency")
        if left_currency and right_currency and left_currency != right_currency:
            conflicts.append(
                {
                    "concept": concept,
                    "primary": left.get("value"),
                    "secondary": right.get("value"),
                    "primary_currency": left_currency,
                    "secondary_currency": right_currency,
                    "status": "currency_mismatch",
                }
            )
            reconciled[concept] = dict(left)
            continue
        left_value, right_value = left.get("value"), right.get("value")
        if not isinstance(left_value, (int, float)) or not isinstance(right_value, (int, float)):
            reconciled[concept] = left
            continue
        denominator = max(abs(left_value), 1.0)
        difference_pct = abs(right_value - left_value) / denominator * 100
        if difference_pct > relative_tolerance_pct:
            conflict = {
                "concept": concept,
                "primary": left_value,
                "secondary": right_value,
                "difference_pct": difference_pct,
                "status": "conflicting",
            }
            conflicts.append(conflict)
            chosen = dict(left)
            chosen["confidence"] = "conflicting"
            chosen["status"] = "conflicting"
            reconciled[concept] = chosen
        else:
            chosen = dict(left)
            chosen["confidence"] = "reconciled"
            reconciled[concept] = chosen
    return {"observations": reconciled, "conflicts": conflicts}
