"""Adversarial validators for identity, association, and grounded claims."""

from __future__ import annotations

import re
from typing import Any


def resolve_path(payload: dict[str, Any], path: str) -> Any:
    if not path.startswith("$."):
        raise ValueError(f"invalid evidence path: {path}")
    current: Any = payload
    for part in path[2:].split("."):
        if not isinstance(current, dict) or part not in current:
            raise KeyError(path)
        current = current[part]
    return current


def validate_identity(report: dict[str, Any], expected_ticker: str) -> list[str]:
    ticker = str(report.get("ticker") or "").upper()
    return [] if ticker == expected_ticker.strip().upper() else [
        f"company identity mismatch: expected {expected_ticker.upper()}, got {ticker or 'missing'}"
    ]


def _number(report: dict[str, Any], section: str, concept: str) -> float | None:
    value = ((report.get(section) or {}).get(concept) or {}).get("value")
    return float(value) if isinstance(value, (int, float)) else None


def validate_calculations(report: dict[str, Any], *, tolerance: float = 1e-6) -> list[str]:
    """Recalculate core associations to catch swaps, signs, and wrong inputs."""
    errors: list[str] = []
    revenue = _number(report, "observations", "revenue")
    prior = _number(report, "observations", "revenue_prior")
    expected: dict[str, float | None] = {
        "revenue_growth_pct": (
            (revenue / prior - 1) * 100 if revenue is not None and prior not in (None, 0) else None
        ),
    }
    for concept, numerator in (
        ("gross_margin_pct", "gross_profit"),
        ("ebitda_margin_pct", "ebitda"),
        ("fcf_margin_pct", "free_cash_flow"),
        ("capex_intensity_pct", "capex"),
    ):
        value = _number(report, "observations", numerator)
        expected[concept] = (
            value / revenue * 100 if value is not None and revenue not in (None, 0) else None
        )
    shares = _number(report, "observations", "shares_outstanding")
    shares_prior = _number(report, "observations", "shares_prior")
    expected["share_dilution_pct"] = (
        (shares / shares_prior - 1) * 100
        if shares is not None and shares_prior not in (None, 0)
        else None
    )
    debt = _number(report, "observations", "total_debt")
    cash = _number(report, "observations", "total_cash")
    expected["net_debt"] = debt - cash if debt is not None and cash is not None else None

    for concept, correct in expected.items():
        actual = _number(report, "derived", concept)
        if actual is None or correct is None:
            continue
        allowed_error = max(0.051, tolerance * max(abs(correct), 1))
        if abs(actual - correct) > allowed_error:
            errors.append(
                f"calculation association mismatch for {concept}: expected {correct}, got {actual}"
            )
    return errors


def validate_alignment(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for concept, metric in (report.get("derived") or {}).items():
        periods = {
            (resolve_path(report, path) or {}).get("period_type")
            for path in metric.get("inputs") or []
            if path.startswith("$.observations.")
        }
        periods.discard(None)
        if len(periods) > 1 and metric.get("period_alignment") == "matched":
            errors.append(f"period association mismatch for {concept}")
        currencies = {
            (resolve_path(report, path) or {}).get("currency")
            for path in metric.get("inputs") or []
            if path.startswith("$.observations.")
        }
        currencies.discard(None)
        currencies.discard("shares")
        if len(currencies) > 1 and metric.get("currency_alignment") == "matched":
            errors.append(f"currency association mismatch for {concept}")
    return errors


def validate_claims(report: dict[str, Any], claims: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for claim in claims:
        paths = claim.get("evidence_paths") or []
        if not paths:
            errors.append(f"ungrounded claim: {claim.get('claim')}")
            continue
        for path in paths:
            try:
                resolve_path(report, path)
            except (KeyError, ValueError):
                errors.append(f"invalid evidence path {path} for claim {claim.get('claim')}")
        if claim.get("claim_type") == "causal" and not any(
            path.startswith("$.external_facts.") for path in paths
        ):
            errors.append(f"unsupported causality: {claim.get('claim')}")
    return errors


def validate_disabled_analyses(
    report: dict[str, Any],
    rendered_output: dict[str, Any] | str,
) -> list[str]:
    disabled = {
        item.get("analysis") for item in report.get("disabled_analyses") or []
    }
    serialized = str(rendered_output).lower()
    errors = []
    if "automatic_dcf" in disabled and re.search(r"\b(dcf_per_share|intrinsic_value|price_target)\b", serialized):
        errors.append("disabled automatic DCF was recreated")
    return errors


def validate_report(
    report: dict[str, Any],
    *,
    expected_ticker: str | None = None,
) -> dict[str, Any]:
    errors = []
    if expected_ticker:
        errors.extend(validate_identity(report, expected_ticker))
    errors.extend(validate_calculations(report))
    errors.extend(validate_alignment(report))
    if report.get("data_mode") == "live" and any(
        item.get("source_type") == "fixture"
        for item in (report.get("observations") or {}).values()
    ):
        errors.append("fixture evidence is labelled live")
    return {"valid": not errors, "errors": errors}
