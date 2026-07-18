"""Normalized financial evidence contract for redesigned workflows.

The legacy engine remains the calculation source of truth. This module projects
its report and provider record into explicit observations and derived metrics so
workflow code never has to infer definitions, periods, currencies, or formulas.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

if __package__:
    from finance_skills import analyze
    from finance_skills.data import Fundamentals
else:
    import analyze
    from data import Fundamentals

SCHEMA_VERSION = "2.0"
CALCULATION_VERSION = "2.0"

Confidence = Literal["primary", "reconciled", "secondary", "estimated", "conflicting", "unusable"]
ObservationStatus = Literal[
    "available",
    "missing",
    "not_reported",
    "not_supported",
    "stale",
    "conflicting",
    "period_mismatch",
    "currency_mismatch",
    "provider_error",
]


@dataclass(frozen=True)
class FinancialObservation:
    value: float | str | bool | None
    concept: str
    definition: str
    unit: str
    currency: str | None
    period_type: str | None
    period_start: str | None
    period_end: str | None
    source_type: str
    source_name: str
    source_reference: str | None
    retrieved_at: str | None
    confidence: Confidence
    is_estimate: bool
    status: ObservationStatus = "available"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DerivedMetric:
    value: float | None
    concept: str
    definition: str
    unit: str
    currency: str | None
    formula: str
    inputs: list[str]
    period_alignment: str
    currency_alignment: str
    calculation_version: str = CALCULATION_VERSION
    status: str = "available"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GroundedClaim:
    claim: str
    evidence_paths: list[str]
    claim_type: str = "quantitative"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EngineFailure:
    error_code: str
    message: str
    status: str = "engine_error"
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_OBSERVATION_SPECS: dict[str, tuple[str, str]] = {
    "price": ("market_price", "provider_market_price"),
    "market_cap": ("currency", "market_price_times_shares"),
    "revenue": ("currency", "reported_total_revenue"),
    "revenue_prior": ("currency", "reported_total_revenue_prior_comparable_period"),
    "gross_profit": ("currency", "reported_revenue_minus_cost_of_revenue"),
    "ebitda": ("currency", "provider_or_reported_ebitda"),
    "free_cash_flow": ("currency", "provider_free_cash_flow"),
    "capex": ("currency", "capital_expenditure_positive_magnitude"),
    "net_income": ("currency", "reported_net_income"),
    "total_debt": ("currency", "reported_total_debt"),
    "total_cash": ("currency", "reported_cash_and_cash_equivalents"),
    "shares_outstanding": ("shares", "provider_current_shares_outstanding"),
    "shares_prior": ("shares", "reported_prior_period_share_count"),
    "operating_cash_flow": ("currency", "reported_cash_from_operating_activities"),
    "working_capital_change": ("currency", "reported_change_in_working_capital"),
    "stock_based_compensation": ("currency", "reported_stock_based_compensation"),
    "acquisition_cash_flow": ("currency", "reported_acquisition_and_disposal_cash_flow"),
    "current_assets": ("currency", "reported_current_assets"),
    "current_assets_prior": ("currency", "reported_prior_period_current_assets"),
    "current_liabilities": ("currency", "reported_current_liabilities"),
    "current_liabilities_prior": ("currency", "reported_prior_period_current_liabilities"),
    "interest_expense": ("currency", "reported_interest_expense"),
    "share_buybacks": ("currency", "reported_share_repurchase_cash_flow"),
    "debt_maturity_profile_available": (
        "boolean",
        "whether_a_debt_maturity_schedule_is_available",
    ),
}

_DERIVED_SPECS: dict[str, tuple[str, str, str, list[str]]] = {
    "revenue_growth_pct": (
        "percent",
        "year_over_year_revenue_growth",
        "(revenue / revenue_prior - 1) * 100",
        ["revenue", "revenue_prior"],
    ),
    "gross_margin_pct": (
        "percent",
        "gross_profit_divided_by_revenue",
        "gross_profit / revenue * 100",
        ["gross_profit", "revenue"],
    ),
    "ebitda_margin_pct": (
        "percent",
        "ebitda_divided_by_revenue",
        "ebitda / revenue * 100",
        ["ebitda", "revenue"],
    ),
    "fcf_margin_pct": (
        "percent",
        "free_cash_flow_divided_by_revenue",
        "free_cash_flow / revenue * 100",
        ["free_cash_flow", "revenue"],
    ),
    "capex_intensity_pct": (
        "percent",
        "capital_expenditure_divided_by_revenue",
        "capex / revenue * 100",
        ["capex", "revenue"],
    ),
    "share_dilution_pct": (
        "percent",
        "year_over_year_share_count_growth",
        "(shares_outstanding / shares_prior - 1) * 100",
        ["shares_outstanding", "shares_prior"],
    ),
    "net_debt": (
        "currency",
        "total_debt_minus_total_cash",
        "total_debt - total_cash",
        ["total_debt", "total_cash"],
    ),
    "enterprise_value": (
        "currency",
        "market_cap_plus_net_debt",
        "market_cap + net_debt",
        ["market_cap", "total_debt", "total_cash"],
    ),
    "ev_sales": (
        "multiple",
        "enterprise_value_divided_by_revenue",
        "enterprise_value / revenue",
        ["market_cap", "total_debt", "total_cash", "revenue"],
    ),
    "ev_ebitda": (
        "multiple",
        "enterprise_value_divided_by_ebitda",
        "enterprise_value / ebitda",
        ["market_cap", "total_debt", "total_cash", "ebitda"],
    ),
}


def _data_mode(fundamentals: Fundamentals) -> str:
    return {
        "cache": "cached",
        "cached": "cached",
        "fixture": "fixture",
        "user_assumption": "user_assumption",
    }.get(fundamentals.data_state, "live")


def _source_type(fundamentals: Fundamentals) -> str:
    if fundamentals.data_state == "fixture" or fundamentals.source == "fixture":
        return "fixture"
    if fundamentals.source in {"sec", "sec_xbrl", "regulatory_filing"}:
        return "regulatory_filing"
    return "market_data"


def _confidence(fundamentals: Fundamentals) -> Confidence:
    if fundamentals.source in {"sec", "sec_xbrl", "regulatory_filing"}:
        return "primary"
    if fundamentals.source == "reconciled":
        return "reconciled"
    if fundamentals.data_state == "fixture":
        return "secondary"
    return "secondary"


def normalize_observations(fundamentals: Fundamentals) -> dict[str, dict[str, Any]]:
    observations: dict[str, dict[str, Any]] = {}
    for concept, (unit_kind, definition) in _OBSERVATION_SPECS.items():
        if not hasattr(fundamentals, concept):
            continue
        value = getattr(fundamentals, concept)
        metadata = fundamentals.field_metadata.get(concept) or {}
        unit = fundamentals.currency or "currency" if unit_kind in {"currency", "market_price"} else unit_kind
        currency = fundamentals.currency if unit_kind in {"currency", "market_price"} else None
        source_name = str(metadata.get("source") or fundamentals.source)
        observation = FinancialObservation(
            value=value,
            concept=concept,
            definition=definition,
            unit=unit,
            currency=currency,
            period_type=metadata.get("period_type"),
            period_start=metadata.get("period_start"),
            period_end=metadata.get("period_end") or fundamentals.as_of,
            source_type=_source_type(fundamentals),
            source_name=source_name,
            source_reference=fundamentals.source_url,
            retrieved_at=fundamentals.retrieved_at,
            confidence=_confidence(fundamentals),
            is_estimate="estimate" in source_name.lower(),
            status="available" if value is not None else "missing",
        )
        observations[concept] = observation.to_dict()
    return observations


def normalize_derived(
    fundamentals: Fundamentals,
    legacy_report: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    derived_values = legacy_report.get("derived") or {}
    warnings = [str(item).lower() for item in legacy_report.get("warnings") or []]
    normalized: dict[str, dict[str, Any]] = {}
    for concept, (unit, definition, formula, inputs) in _DERIVED_SPECS.items():
        value = derived_values.get(concept)
        period_alignment = (
            "mismatched"
            if any(concept.replace("_pct", "").replace("_", " ") in warning and "period" in warning for warning in warnings)
            else "matched"
        )
        currency_alignment = (
            "mismatched"
            if any(
                ("currency" in warning)
                and (concept in {"net_debt", "enterprise_value", "ev_sales", "ev_ebitda"})
                for warning in warnings
            )
            else "matched"
        )
        status = "available"
        if period_alignment == "mismatched":
            status = "period_mismatch"
        elif currency_alignment == "mismatched":
            status = "currency_mismatch"
        elif value is None:
            status = "missing"
        normalized[concept] = DerivedMetric(
            value=value,
            concept=concept,
            definition=definition,
            unit=fundamentals.currency or "currency" if unit == "currency" else unit,
            currency=fundamentals.currency if unit == "currency" else None,
            formula=formula,
            inputs=[f"$.observations.{name}" for name in inputs],
            period_alignment=period_alignment,
            currency_alignment=currency_alignment,
            status=status,
        ).to_dict()
    return normalized


def build_evidence_report(
    fundamentals: Fundamentals,
    *,
    observation_overrides: dict[str, dict[str, Any]] | None = None,
    provider_results: list[dict[str, Any]] | None = None,
    reconciliation_conflicts: list[dict[str, Any]] | None = None,
    extra_warnings: list[str] | None = None,
    estimate_observations: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return the normalized contract consumed by every redesigned workflow."""
    if not fundamentals.available:
        failure = EngineFailure(
            error_code=(
                "INVALID_ARGUMENT"
                if fundamentals.error and "invalid ticker" in fundamentals.error
                else "LIVE_DATA_UNAVAILABLE"
            ),
            message=fundamentals.error or "Financial data is unavailable.",
            status="provider_error",
            details={"ticker": fundamentals.ticker},
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "status": failure.status,
            "ticker": fundamentals.ticker,
            "failure": failure.to_dict(),
            "data_mode": _data_mode(fundamentals),
            "observations": {},
            "estimate_observations": estimate_observations or {},
            "derived": {},
            "findings": [],
            "warnings": [failure.message, *(extra_warnings or [])],
            "provider_results": provider_results or [],
            "reconciliation_conflicts": reconciliation_conflicts or [],
        }

    legacy = analyze.build_report(fundamentals)
    observations = normalize_observations(fundamentals)
    if observation_overrides:
        observations.update(observation_overrides)
    derived = normalize_derived(fundamentals, legacy)
    missing_core = [
        name
        for name in ("revenue", "free_cash_flow", "total_debt", "total_cash")
        if observations.get(name, {}).get("status") == "missing"
    ]
    warnings = list(legacy.get("warnings") or [])
    warnings.extend(extra_warnings or [])
    if missing_core:
        warnings.append("Missing core observations: " + ", ".join(missing_core))
    disabled: list[dict[str, Any]] = []
    if legacy.get("dcf_note"):
        disabled.append(
            {
                "analysis": "automatic_dcf",
                "status": "disabled",
                "reason": legacy["dcf_note"],
            }
        )
    if legacy.get("rule40_note"):
        disabled.append(
            {
                "analysis": "rule40",
                "status": "disabled",
                "reason": legacy["rule40_note"],
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "partial" if warnings or reconciliation_conflicts else "success",
        "ticker": fundamentals.ticker,
        "company": {
            "name": fundamentals.name,
            "sector": fundamentals.sector,
            "industry": fundamentals.industry,
        },
        "data_mode": _data_mode(fundamentals),
        "data_as_of": fundamentals.as_of,
        "retrieved_at": fundamentals.retrieved_at,
        "currency": fundamentals.currency,
        "observations": observations,
        "estimate_observations": estimate_observations or {},
        "derived": derived,
        "warnings": warnings,
        "provider_results": provider_results or [],
        "reconciliation_conflicts": reconciliation_conflicts or [],
        "disabled_analyses": disabled,
        "valuation_basis": {
            "type": "growth_and_margin_adjusted_framework",
            "label": "project-authored reference band",
            "decisive": False,
        },
        "source_summary": {
            "provider": fundamentals.source,
            "source_reference": fundamentals.source_url,
            "confidence": _confidence(fundamentals),
            "observation_count": len(observations),
            "available_observation_count": sum(
                item["status"] == "available" for item in observations.values()
            ),
            "confidence_statistics": {
                confidence: sum(
                    item.get("confidence") == confidence for item in observations.values()
                )
                for confidence in (
                    "primary",
                    "reconciled",
                    "secondary",
                    "estimated",
                    "conflicting",
                    "unusable",
                )
            },
        },
        "legacy_report": legacy,
    }


def metric_value(report: dict[str, Any], concept: str) -> float | None:
    metric = (report.get("derived") or {}).get(concept) or {}
    value = metric.get("value")
    return float(value) if isinstance(value, (int, float)) else None


def observation_value(report: dict[str, Any], concept: str) -> float | None:
    observation = (report.get("observations") or {}).get(concept) or {}
    value = observation.get("value")
    return float(value) if isinstance(value, (int, float)) else None
