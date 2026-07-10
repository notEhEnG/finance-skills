"""Canonical agent-facing EngineReport schema (P2).

Views (brief, valuation, …) MUST project from the same build_report + envelope
rather than inventing parallel calculations. Missing data is never encoded as
bare 0 or unexplained null.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

SCHEMA_VERSION = "1.0.0"

DataState = Literal[
    "live", "cache", "fixture", "unavailable", "unknown", "invalid", "stale", "not_applicable", "disabled"
]


@dataclass
class MetricValue:
    """A single fact or calculation with explicit availability."""
    name: str
    status: DataState
    value: float | str | bool | None = None
    units: str | None = None
    definition: str | None = None
    required_inputs: list[str] = field(default_factory=list)
    note: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DisabledAnalysis:
    analysis: str
    reason_code: str
    human_reason: str
    missing_inputs: list[str] = field(default_factory=list)
    unlock: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FlagItem:
    severity: str
    category: str
    flag: str
    detail: str
    interpretation_boundary: str = (
        "Heuristic flag from engine rules; not a recommendation."
    )

    def to_dict(self) -> dict:
        return asdict(self)


def _mv(name: str, value: Any, *, units: str | None = None, definition: str | None = None,
        required: list[str] | None = None) -> MetricValue:
    if value is None:
        return MetricValue(
            name=name, status="unavailable", value=None, units=units,
            definition=definition, required_inputs=required or [],
            note="unavailable — not computed or not present in source",
        )
    return MetricValue(
        name=name, status="live", value=value, units=units,
        definition=definition, required_inputs=required or [],
    )


def reason_code_for_disabled(analysis: str, human: str) -> str:
    h = human.lower()
    if "not positive" in h or "negative" in h:
        return "input_not_positive"
    if "missing" in h or "unknown" in h:
        return "input_missing"
    if "fabricat" in h:
        return "fail_closed_no_imputation"
    return "disabled"


def build_response_guidance(
    *,
    source: str | None,
    disabled: list[DisabledAnalysis],
    intent: str | None = None,
) -> dict[str, Any]:
    prohibited = [
        "unconditional_buy_recommendation",
        "unconditional_sell_recommendation",
        "unconditional_hold_recommendation",
        "guaranteed_outcome",
        "safe_as_verdict",
        "invented_numbers_not_in_report",
        "fill_missing_from_memory",
        "label_fixture_as_live",
    ]
    if any(d.analysis == "dcf" for d in disabled):
        prohibited.append("intrinsic_value_per_share_claim")
        prohibited.append("dcf_fair_value_claim")
    permitted = [
        "cite_report_metrics",
        "cite_flags_with_boundary",
        "state_disabled_analyses",
        "conditional_valuation_language",
        "filing_verification_items",
    ]
    caveats = [
        "not_investment_advice",
        "verify_primary_filings",
    ]
    if source == "fixture":
        caveats.insert(0, "fixture_sample_data_not_live")
    if intent == "valuation":
        caveats.append("buy_question_must_be_reframed_as_analysis")
    return {
        "permitted_claims": permitted,
        "prohibited_claims": prohibited,
        "mandatory_caveats": caveats,
    }


def envelope_from_build_report(
    report: dict[str, Any],
    *,
    fundamentals: Any | None = None,
    route: dict[str, Any] | None = None,
    invocation_mode: str = "agent",
    disabled_raw: list[dict[str, Any]] | None = None,
    flags_raw: list[dict[str, Any]] | None = None,
    checklist: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Wrap a build_report dict (and optional brief extras) as EngineReport JSON."""
    available = report.get("available", True)
    source = report.get("source")
    data_state: DataState
    if not available:
        data_state = "unavailable"
    elif source == "fixture":
        data_state = "fixture"
    elif source == "yfinance":
        data_state = "live"
    else:
        data_state = "unknown"

    disabled: list[DisabledAnalysis] = []
    if disabled_raw:
        for d in disabled_raw:
            disabled.append(DisabledAnalysis(
                analysis=d.get("analysis", "unknown"),
                reason_code=reason_code_for_disabled(
                    d.get("analysis", ""), d.get("reason", "")
                ),
                human_reason=d.get("reason", ""),
                missing_inputs=list(d.get("missing_inputs") or []),
                unlock=d.get("unlocks"),
            ))
    elif report.get("dcf_note") and "dcf" not in report:
        disabled.append(DisabledAnalysis(
            analysis="dcf",
            reason_code=reason_code_for_disabled("dcf", report["dcf_note"]),
            human_reason=report["dcf_note"],
            missing_inputs=[],
            unlock="positive FCF + shares + known net debt",
        ))
    if report.get("rule40_note") and "rule40" not in report:
        disabled.append(DisabledAnalysis(
            analysis="rule40",
            reason_code=reason_code_for_disabled("rule40", report["rule40_note"]),
            human_reason=report["rule40_note"],
            missing_inputs=[],
            unlock="revenue growth + EBITDA margin + FCF margin",
        ))

    flags: list[FlagItem] = []
    if flags_raw:
        for fl in flags_raw:
            flags.append(FlagItem(
                severity=str(fl.get("severity", "•")),
                category="redflag",
                flag=str(fl.get("flag", "")),
                detail=str(fl.get("detail", "")),
            ))

    d = report.get("derived") or {}
    calculations = [
        _mv("revenue_growth_pct", d.get("revenue_growth_pct"), units="percent",
            definition="YoY revenue growth", required=["revenue", "revenue_prior"]),
        _mv("ebitda_margin_pct", d.get("ebitda_margin_pct"), units="percent",
            definition="EBITDA / revenue", required=["ebitda", "revenue"]),
        _mv("fcf_margin_pct", d.get("fcf_margin_pct"), units="percent",
            definition="FCF / revenue", required=["free_cash_flow", "revenue"]),
        _mv("ev_sales", d.get("ev_sales"), units="multiple",
            definition="EV / sales", required=["market_cap", "net_debt", "revenue"]),
        _mv("ev_ebitda", d.get("ev_ebitda"), units="multiple",
            definition="EV / EBITDA", required=["market_cap", "net_debt", "ebitda"]),
        _mv("net_debt", d.get("net_debt"), units="currency",
            definition="total_debt - total_cash", required=["total_debt", "total_cash"]),
    ]
    if "rule40" in report:
        r40 = report["rule40"]
        calculations.append(_mv(
            "rule40_preferred", r40.get("preferred_score"), units="score",
            definition="regime-preferred Rule of 40 score",
            required=["revenue_growth", "ebitda_margin", "fcf_margin"],
        ))
    if "dcf" in report:
        calculations.append(_mv(
            "dcf_per_share", (report["dcf"] or {}).get("per_share"), units="currency_per_share",
            definition="heuristic two-stage DCF per share",
            required=["fcf", "shares", "net_debt"],
        ))
    else:
        calculations.append(MetricValue(
            name="dcf_per_share", status="disabled", value=None,
            units="currency_per_share",
            note=report.get("dcf_note") or "DCF not available",
            required_inputs=["positive_fcf", "shares_outstanding", "net_debt"],
        ))

    source_facts = [
        _mv("price", report.get("price"), units="currency"),
        _mv("market_cap", report.get("market_cap"), units="currency"),
        _mv("revenue", d.get("revenue"), units="currency"),
    ]

    intent = (route or {}).get("intent")
    guidance = build_response_guidance(
        source=source if available else None,
        disabled=disabled,
        intent=intent,
    )

    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    if not available:
        errors.append({
            "code": "data_unavailable",
            "message": str(report.get("error") or "fundamentals unavailable"),
        })
    if data_state == "fixture":
        warnings.append({
            "code": "fixture_sample",
            "message": "SAMPLE DATA — not live market data",
        })

    filing = checklist or [
        {"item": "revenue", "where": "Income statement", "why": "Growth and margins"},
        {"item": "free cash flow", "where": "Cash flow statement", "why": "FCF and DCF"},
        {"item": "total debt", "where": "Balance sheet", "why": "Net debt / EV"},
        {"item": "cash", "where": "Balance sheet", "why": "Net debt / runway"},
        {"item": "share count", "where": "Filings cover", "why": "Per-share metrics"},
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "request": {
            "original_query": (route or {}).get("original_query"),
            "route": route,
            "resolved_intent": intent,
            "tickers": (route or {}).get("tickers") or [report.get("ticker")],
            "invocation_mode": invocation_mode,
        },
        "company": {
            "requested_symbol": report.get("ticker"),
            "resolved_symbol": report.get("ticker"),
            "name": report.get("name"),
            "sector": report.get("sector"),
            "industry": report.get("industry"),
            "exchange": None,
            "status": "resolved" if available else "unavailable",
        },
        "source": {
            "provider": source or "unknown",
            "as_of": report.get("as_of"),
            "retrieval_timestamp_utc": report.get("as_of"),
            "data_state": data_state,
            "freshness_warning": (
                "fixture_not_live" if data_state == "fixture" else None
            ),
        },
        "source_facts": [m.to_dict() for m in source_facts],
        "calculations": [m.to_dict() for m in calculations],
        "flags": [f.to_dict() for f in flags],
        "disabled_analyses": [d.to_dict() for d in disabled],
        "filing_verification_checklist": filing,
        "response_guidance": guidance,
        "errors": errors,
        "warnings": warnings,
        # Backward-compatible raw engine slice for existing views/tests
        "legacy_report": report,
    }


_ENVELOPE_KEYS = (
    "schema_version", "request", "company", "source", "source_facts",
    "calculations", "flags", "disabled_analyses",
    "filing_verification_checklist", "response_guidance",
    "errors", "warnings",
)


def attach_engine_report(
    view_payload: dict[str, Any],
    report: dict[str, Any],
    *,
    fundamentals: Any | None = None,
    route: dict[str, Any] | None = None,
    invocation_mode: str = "agent",
    disabled_raw: list[dict[str, Any]] | None = None,
    flags_raw: list[dict[str, Any]] | None = None,
    checklist: list[dict[str, Any]] | None = None,
    intent: str | None = None,
) -> dict[str, Any]:
    """Attach canonical engine_report to any view JSON (brief, valuation, …)."""
    route = dict(route or {})
    if intent and not route.get("intent"):
        route["intent"] = intent
    envelope = envelope_from_build_report(
        report,
        fundamentals=fundamentals,
        route=route or None,
        invocation_mode=invocation_mode,
        disabled_raw=disabled_raw,
        flags_raw=flags_raw,
        checklist=checklist,
    )
    out = dict(view_payload)
    out["schema_version"] = envelope["schema_version"]
    out["engine_report"] = {k: envelope[k] for k in _ENVELOPE_KEYS}
    return out


def project_brief_payload(envelope: dict[str, Any], legacy_brief: dict[str, Any]) -> dict[str, Any]:
    """Attach envelope keys onto a brief JSON payload for agents."""
    out = dict(legacy_brief)
    out["schema_version"] = envelope["schema_version"]
    out["engine_report"] = {k: envelope[k] for k in _ENVELOPE_KEYS}
    return out


def enrich_report_for_agent(
    f: Any,
    report: dict[str, Any],
    view_payload: dict[str, Any],
    *,
    intent: str,
) -> dict[str, Any]:
    """Shared path: diagnostics + flags + envelope on any available report."""
    try:
        if __package__:
            from finance_skills import diagnostics, redflags
        else:
            import diagnostics
            import redflags
    except ImportError:
        import diagnostics
        import redflags

    if not report.get("available", True):
        return attach_engine_report(
            view_payload if view_payload else report,
            report,
            fundamentals=f,
            intent=intent,
        )
    disabled = diagnostics.disabled_analyses(f, report)
    flags = redflags.flags_for(report)
    checklist = diagnostics.filing_checklist({"disabled": disabled, "gaps": []})
    return attach_engine_report(
        view_payload,
        report,
        fundamentals=f,
        intent=intent,
        disabled_raw=disabled,
        flags_raw=flags,
        checklist=checklist,
    )
