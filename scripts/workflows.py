"""Deterministic redesigned finance workflows over one normalized report."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

if __package__:
    from finance_skills import detectors
    from finance_skills.evidence import GroundedClaim, metric_value, observation_value
else:
    import detectors
    from evidence import GroundedClaim, metric_value, observation_value


def prepare_report(report: dict[str, Any]) -> dict[str, Any]:
    """Attach detector output once and return the report."""
    if "detector_results" not in report:
        detectors.attach_findings(report)
    return report


def _claim(text: str, *paths: str, claim_type: str = "qualitative") -> dict[str, Any]:
    return GroundedClaim(text, list(paths), claim_type).to_dict()


def _limitations(report: dict[str, Any]) -> list[str]:
    limitations = [str(item) for item in report.get("warnings") or []]
    limitations.extend(
        f"{item.get('analysis')}: {item.get('reason')}"
        for item in report.get("disabled_analyses") or []
    )
    if report.get("data_mode") != "live":
        limitations.insert(0, f"Data mode is {report.get('data_mode')}, not live.")
    return list(dict.fromkeys(limitations))


def _signals(report: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    strengths: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []
    growth = metric_value(report, "revenue_growth_pct")
    ebitda = metric_value(report, "ebitda_margin_pct")
    fcf = metric_value(report, "fcf_margin_pct")
    dilution = metric_value(report, "share_dilution_pct")
    net_debt = metric_value(report, "net_debt")

    if growth is not None:
        target = strengths if growth > 15 else risks if growth < 0 else strengths
        target.append(_claim(
            f"Revenue growth is {growth:.1f}%.",
            "$.derived.revenue_growth_pct",
            claim_type="quantitative",
        ))
    if ebitda is not None:
        target = strengths if ebitda > 0 else risks
        target.append(_claim(
            f"EBITDA margin is {ebitda:.1f}%.",
            "$.derived.ebitda_margin_pct",
            claim_type="quantitative",
        ))
    if fcf is not None:
        target = strengths if fcf > 0 else risks
        target.append(_claim(
            f"Free-cash-flow margin is {fcf:.1f}%.",
            "$.derived.fcf_margin_pct",
            claim_type="quantitative",
        ))
    if dilution is not None and dilution >= 2:
        risks.append(_claim(
            f"Diluted share count increased {dilution:.1f}%.",
            "$.derived.share_dilution_pct",
            claim_type="quantitative",
        ))
    if net_debt is not None:
        target = strengths if net_debt < 0 else risks
        target.append(_claim(
            f"Net debt is {net_debt:,.0f} {report.get('currency') or 'currency units'}.",
            "$.derived.net_debt",
            claim_type="quantitative",
        ))
    for finding in report.get("findings") or []:
        if finding.get("severity") in {"high", "critical"}:
            risks.append(
                _claim(
                    f"{finding['rule_id']}: {finding['title']}.",
                    *finding.get("evidence_paths", []),
                )
            )
    return strengths, risks


def screen(report: dict[str, Any]) -> dict[str, Any]:
    report = prepare_report(report)
    if report.get("status") in {"provider_error", "engine_error"}:
        return report
    strengths, risks = _signals(report)
    growth = metric_value(report, "revenue_growth_pct")
    fcf = metric_value(report, "fcf_margin_pct")
    if growth is None or fcf is None:
        bottom_line = "The available evidence is insufficient for a complete screen."
    elif growth > 20 and fcf < 0:
        bottom_line = "Growth is strong, but current free-cash-flow conversion does not support it."
    elif growth > 0 and fcf > 0:
        bottom_line = "Growth and cash conversion are both positive, subject to valuation and source limitations."
    else:
        bottom_line = "The screen is mixed and depends on improving the weakest operating dimension."
    result = {
        "workflow": "screen",
        "status": report.get("status"),
        "ticker": report.get("ticker"),
        "bottom_line": bottom_line,
        "key_metrics": {
            name: (report.get("derived") or {}).get(name)
            for name in (
                "revenue_growth_pct",
                "ebitda_margin_pct",
                "fcf_margin_pct",
                "capex_intensity_pct",
                "share_dilution_pct",
                "net_debt",
                "ev_sales",
                "ev_ebitda",
            )
        },
        "strengths": strengths,
        "risks": risks,
        "valuation_context": {
            "basis": report.get("valuation_basis"),
            "ev_sales": (report.get("derived") or {}).get("ev_sales"),
            "ev_ebitda": (report.get("derived") or {}).get("ev_ebitda"),
            "conclusion": "No cheap/expensive verdict is made without peer, historical, or explicit-scenario context.",
        },
        "detector_findings": report.get("findings") or [],
        "limitations": _limitations(report),
        "assumption_doing_most_work": (
            "Future growth must convert into durable free cash flow."
            if fcf is not None and fcf < 0
            else "Current operating economics must remain representative."
        ),
        "conditional_conclusion": (
            "The evidence improves if growth persists while cash conversion and per-share economics strengthen."
        ),
        "next_command": f"/finance underwrite {report.get('ticker')}",
        "evidence_report": report,
    }
    return result


def _specialist_packets(report: dict[str, Any]) -> list[dict[str, Any]]:
    strengths, risks = _signals(report)
    return [
        {
            "specialist": "fundamental_analyst",
            "claims": strengths,
            "counterarguments": risks,
            "unresolved_questions": [
                "Is observed growth durable across comparable periods?",
                "What must happen for cash conversion to improve?",
            ],
            "evidence_packet_hash_required": True,
        },
        {
            "specialist": "forensic_accountant",
            "claims": [
                _claim(
                    f"{item['rule_id']}: {item['title']}.",
                    *item.get("evidence_paths", []),
                )
                for item in report.get("findings") or []
            ],
            "counterarguments": [
                explanation
                for item in report.get("findings") or []
                for explanation in item.get("possible_benign_explanations") or []
            ],
            "unresolved_questions": [
                item["remediation"] for item in report.get("findings") or []
            ],
            "evidence_packet_hash_required": True,
        },
        {
            "specialist": "valuation_skeptic",
            "claims": [
                _claim(
                    "Valuation remains conditional because the engine has no decisive peer or historical basis.",
                    "$.valuation_basis",
                )
            ],
            "counterarguments": strengths,
            "unresolved_questions": [
                "Which peer or historical comparison basis is appropriate?",
                "Which growth and margin assumptions are embedded in the current multiple?",
            ],
            "evidence_packet_hash_required": True,
        },
    ]


def underwrite(report: dict[str, Any]) -> dict[str, Any]:
    report = prepare_report(report)
    if report.get("status") in {"provider_error", "engine_error"}:
        return report
    strengths, risks = _signals(report)
    fcf = metric_value(report, "fcf_margin_pct")
    dilution = metric_value(report, "share_dilution_pct")
    thesis = (
        "The thesis is conditional on growth becoming durable per-share cash generation."
        if fcf is not None and fcf < 0
        else "The thesis is conditional on maintaining operating economics without valuation expansion."
    )
    return {
        "workflow": "underwrite",
        "status": report.get("status"),
        "ticker": report.get("ticker"),
        "thesis": thesis,
        "business_and_growth_quality": strengths,
        "economics_and_cash_flow": {
            "ebitda_margin": (report.get("derived") or {}).get("ebitda_margin_pct"),
            "fcf_margin": (report.get("derived") or {}).get("fcf_margin_pct"),
            "capital_intensity": (report.get("derived") or {}).get("capex_intensity_pct"),
        },
        "balance_sheet_and_dilution": {
            "net_debt": (report.get("derived") or {}).get("net_debt"),
            "share_dilution": (report.get("derived") or {}).get("share_dilution_pct"),
            "interpretation": (
                "Per-share economics are a material thesis risk."
                if dilution is not None and dilution >= 2
                else "Available dilution evidence is not currently a high-severity signal."
            ),
        },
        "valuation_condition": (
            "The current valuation is defensible only if operating growth and margins support the multiple; "
            "the project-authored reference band is not decisive proof."
        ),
        "bull_case": strengths,
        "bear_case": risks,
        "core_assumption": "Growth converts into sustainable free cash flow without excessive dilution.",
        "disconfirming_conditions": [
            "Revenue growth materially deteriorates.",
            "Free-cash-flow margin fails to improve.",
            "Dilution prevents improvement in per-share economics.",
            "Balance-sheet risk rises faster than operating profitability.",
        ],
        "unresolved_questions": [
            item["remediation"] for item in report.get("findings") or []
        ],
        "specialist_packets": _specialist_packets(report),
        "specialist_disagreement": (
            "The fundamental view may emphasize growth while the forensic and valuation views "
            "require better cash conversion and comparison evidence."
        ),
        "limitations": _limitations(report),
        "next_command": f"/finance challenge {report.get('ticker')}",
        "evidence_report": report,
    }


def audit(report: dict[str, Any]) -> dict[str, Any]:
    report = prepare_report(report)
    findings = report.get("findings") or []
    high = [item for item in findings if item.get("severity") in {"high", "critical"}]
    medium = [item for item in findings if item.get("severity") == "medium"]
    return {
        "workflow": "audit",
        "status": report.get("status"),
        "ticker": report.get("ticker"),
        "audit_conclusion": (
            "Material evidence-quality conditions require verification."
            if high
            else "No high-severity detector triggered on the available evidence."
        ),
        "high_severity_findings": high,
        "medium_severity_findings": medium,
        "all_detector_results": report.get("detector_results") or [],
        "data_quality_limitations": _limitations(report),
        "plausible_benign_explanations": list(
            dict.fromkeys(
                explanation
                for item in findings
                for explanation in item.get("possible_benign_explanations") or []
            )
        ),
        "verification_checklist": list(
            dict.fromkeys(item["remediation"] for item in findings)
        ),
        "prohibited_inference": "Detector findings are evidence, not allegations of fraud or misconduct.",
        "next_command": f"/finance underwrite {report.get('ticker')}",
        "evidence_report": report,
    }


def compare(reports: list[dict[str, Any]]) -> dict[str, Any]:
    prepared = [prepare_report(report) for report in reports]
    currencies = {report.get("currency") for report in prepared if report.get("currency")}
    periods = {report.get("data_as_of") for report in prepared if report.get("data_as_of")}
    sectors = {
        (report.get("company") or {}).get("sector")
        for report in prepared
        if (report.get("company") or {}).get("sector")
    }
    comparability = {
        "period_compatibility": "matched" if len(periods) <= 1 else "mismatched",
        "currency_compatibility": "matched" if len(currencies) <= 1 else "mismatched",
        "classification_compatibility": "matched" if len(sectors) <= 1 else "different_profiles",
        "periods": sorted(str(item) for item in periods),
        "currencies": sorted(str(item) for item in currencies),
        "sectors": sorted(str(item) for item in sectors),
    }
    blocked = len(currencies) > 1 or len(periods) > 1
    dimensions = {}
    for name in (
        "revenue_growth_pct",
        "ebitda_margin_pct",
        "fcf_margin_pct",
        "capex_intensity_pct",
        "share_dilution_pct",
        "net_debt",
        "ev_sales",
        "ev_ebitda",
    ):
        dimensions[name] = {
            report["ticker"]: (report.get("derived") or {}).get(name)
            for report in prepared
        }
    return {
        "workflow": "compare",
        "status": "period_mismatch" if len(periods) > 1 else "currency_mismatch" if len(currencies) > 1 else "success",
        "tickers": [report.get("ticker") for report in prepared],
        "comparability": comparability,
        "comparison_blocked": blocked,
        "dimensions": dimensions if not blocked else {},
        "strongest_case_for_each": {
            report["ticker"]: _signals(report)[0] for report in prepared
        },
        "key_tradeoff": (
            "The companies differ by dimension; no universal winner is manufactured."
        ),
        "conditional_conclusion": (
            "Comparison is blocked until periods and currencies align."
            if blocked
            else "Relative strength depends on which compatible dimension the user prioritizes."
        ),
        "limitations": {
            report["ticker"]: _limitations(report) for report in prepared
        },
        "next_command": None,
        "evidence_reports": prepared,
    }


def challenge(
    report: dict[str, Any],
    *,
    saved_thesis: str | None = None,
    saved_watchpoints: str | None = None,
) -> dict[str, Any]:
    report = prepare_report(report)
    strengths, risks = _signals(report)
    return {
        "workflow": "challenge",
        "status": report.get("status"),
        "ticker": report.get("ticker"),
        "thesis_being_challenged": saved_thesis or "No saved thesis; challenging the current evidence-led screen.",
        "strongest_counterargument": risks[0] if risks else _claim(
            "The available evidence may not cover the risk that matters most.",
            "$.warnings",
        ),
        "contradictory_evidence": risks,
        "evidence_supporting_thesis": strengths,
        "hidden_assumption": "Current growth and margins are durable and representative.",
        "invalidation_conditions": [
            "Cash conversion deteriorates or remains structurally negative.",
            "Per-share growth materially trails enterprise growth.",
            "A high-severity detector remains unresolved.",
        ],
        "saved_watchpoints": saved_watchpoints,
        "revised_confidence": "lower" if risks else "unchanged",
        "limitations": _limitations(report),
        "next_command": f"/finance stress {report.get('ticker')}",
        "evidence_report": report,
    }


_REQUIRED_ASSUMPTIONS = (
    "revenue_growth_pct",
    "margin_pct",
    "valuation_multiple",
    "dilution_pct",
    "net_debt",
    "horizon_years",
)


def _scenario(
    revenue: float,
    shares: float | None,
    assumptions: dict[str, float],
) -> dict[str, Any]:
    horizon = int(assumptions["horizon_years"])
    future_revenue = revenue * (1 + assumptions["revenue_growth_pct"] / 100) ** horizon
    operating_metric = future_revenue * assumptions["margin_pct"] / 100
    enterprise_value = operating_metric * assumptions["valuation_multiple"]
    equity_value = enterprise_value - assumptions["net_debt"]
    diluted_shares = (
        shares * (1 + assumptions["dilution_pct"] / 100) ** horizon
        if shares is not None
        else None
    )
    return {
        "assumptions": assumptions,
        "future_revenue": future_revenue,
        "operating_metric": operating_metric,
        "implied_enterprise_value": enterprise_value,
        "implied_equity_value": equity_value,
        "implied_value_per_diluted_share": (
            equity_value / diluted_shares if diluted_shares else None
        ),
        "label": "explicit sensitivity scenario; not a forecast or price target",
    }


def stress(report: dict[str, Any], assumptions: dict[str, Any]) -> dict[str, Any]:
    report = prepare_report(report)
    missing = [name for name in _REQUIRED_ASSUMPTIONS if name not in assumptions]
    if missing:
        return {
            "workflow": "stress",
            "status": "unsupported_analysis",
            "failure": {
                "error_code": "INVALID_ARGUMENT",
                "message": "Missing explicit scenario assumptions: " + ", ".join(missing),
            },
            "required_assumptions": list(_REQUIRED_ASSUMPTIONS),
            "provided_assumptions": assumptions,
        }
    try:
        base = {name: float(assumptions[name]) for name in _REQUIRED_ASSUMPTIONS}
    except (TypeError, ValueError):
        return {
            "workflow": "stress",
            "status": "unsupported_analysis",
            "failure": {
                "error_code": "INVALID_ARGUMENT",
                "message": "Every scenario assumption must be numeric.",
            },
        }
    if base["horizon_years"] <= 0 or base["valuation_multiple"] < 0:
        return {
            "workflow": "stress",
            "status": "unsupported_analysis",
            "failure": {
                "error_code": "INVALID_ARGUMENT",
                "message": "Horizon must be positive and valuation multiple cannot be negative.",
            },
        }
    revenue = observation_value(report, "revenue")
    shares = observation_value(report, "shares_outstanding")
    if revenue is None:
        return {
            "workflow": "stress",
            "status": "insufficient_data",
            "failure": {
                "error_code": "INSUFFICIENT_DATA",
                "message": "Reported revenue is required for scenario analysis.",
            },
        }
    upside = deepcopy(base)
    downside = deepcopy(base)
    upside["revenue_growth_pct"] += 5
    upside["margin_pct"] += 5
    upside["valuation_multiple"] += 1
    downside["revenue_growth_pct"] -= 5
    downside["margin_pct"] -= 5
    downside["valuation_multiple"] = max(downside["valuation_multiple"] - 1, 0)
    result = {
        "workflow": "stress",
        "status": "success",
        "ticker": report.get("ticker"),
        "assumptions": base,
        "scenario_adjustments": {
            "upside": {"growth_pct_points": 5, "margin_pct_points": 5, "multiple": 1},
            "downside": {"growth_pct_points": -5, "margin_pct_points": -5, "multiple": -1},
            "label": "project-authored sensitivity deltas; fully visible, not forecasts",
        },
        "scenarios": {
            "base": _scenario(revenue, shares, base),
            "upside": _scenario(revenue, shares, upside),
            "downside": _scenario(revenue, shares, downside),
        },
        "highest_sensitivity_variable": "valuation_multiple",
        "conditions_required": [
            "Revenue follows the explicit growth path.",
            "The explicit margin is achieved.",
            "The selected valuation multiple remains applicable.",
            "Dilution and net debt follow the displayed assumptions.",
        ],
        "limitations": [
            "These are explicit sensitivity scenarios, not forecasts or price targets.",
            *_limitations(report),
        ],
        "next_command": f"/finance track {report.get('ticker')}",
        "evidence_report": report,
    }
    detector_input = deepcopy(report)
    detector_input["assumptions"] = base
    detector_input["scenarios"] = result["scenarios"]
    result["detector_findings"] = [
        item
        for item in detectors.evaluate_detectors(detector_input)
        if item["category"] == "valuation"
    ]
    return result


_TOPICS: dict[str, dict[str, Any]] = {
    "rule of 40": {
        "definition": "Revenue growth plus a profitability margin.",
        "formula": "revenue growth % + EBITDA or free-cash-flow margin %",
        "why_it_matters": "It makes the growth-versus-profitability tradeoff visible.",
        "example": "30% growth plus 12% FCF margin equals 42.",
        "common_mistakes": ["Mixing periods", "Hiding which margin is used", "Treating 40 as universal"],
        "limitations": ["It is a project-authored reference framework, not a valuation proof."],
    },
    "enterprise value": {
        "definition": "Market capitalization plus net debt.",
        "formula": "market cap + total debt - cash",
        "why_it_matters": "It compares operating value across different capital structures.",
        "example": "A 10bn market cap plus 2bn net debt gives 12bn enterprise value.",
        "common_mistakes": ["Using mismatched dates", "Treating missing debt as zero"],
        "limitations": ["Lease, pension, minority-interest, and other adjustments may matter."],
    },
    "free cash flow": {
        "definition": "Cash remaining after operating needs and capital expenditure.",
        "formula": "operating cash flow - capital expenditure",
        "why_it_matters": "It tests whether accounting performance converts into cash after investment.",
        "example": "500m operating cash flow less 200m capex gives 300m FCF.",
        "common_mistakes": ["Deducting capex twice", "Ignoring working capital", "Mixing provider definitions"],
        "limitations": ["Acquisitions, leases, and capitalization policy can affect comparability."],
    },
    "working capital": {
        "definition": "Short-term operating assets minus short-term operating liabilities.",
        "formula": "current operating assets - current operating liabilities",
        "why_it_matters": "Changes can materially raise or lower operating cash flow.",
        "example": "Receivables rising faster than payables consumes cash.",
        "common_mistakes": ["Treating temporary timing as structural", "Ignoring deferred revenue"],
        "limitations": ["Definitions vary by business model."],
    },
    "dilution": {
        "definition": "An increase in shares that reduces each existing share's ownership percentage.",
        "formula": "(current diluted shares / prior diluted shares - 1) * 100",
        "why_it_matters": "Enterprise growth may not translate into per-share growth.",
        "example": "Revenue rises 10% while shares rise 12%, so revenue per share falls.",
        "common_mistakes": ["Looking only at basic shares", "Ignoring SBC and convertibles"],
        "limitations": ["Buybacks and issuance timing require multi-period review."],
    },
    "net debt": {
        "definition": "Total debt minus cash.",
        "formula": "total debt - cash",
        "why_it_matters": "It connects capital structure to enterprise value and refinancing risk.",
        "example": "5bn debt less 2bn cash equals 3bn net debt.",
        "common_mistakes": ["Treating missing cash as zero", "Mixing balance dates or currencies"],
        "limitations": ["Restricted cash and off-balance-sheet obligations may matter."],
    },
    "operating leverage": {
        "definition": "The sensitivity of operating profit to changes in revenue.",
        "formula": "change in operating profit % / change in revenue %",
        "why_it_matters": "It shows whether scale improves or weakens margins.",
        "example": "Revenue grows 10% while operating profit grows 20%, implying positive leverage.",
        "common_mistakes": ["Extrapolating one period", "Ignoring mix and one-time costs"],
        "limitations": ["Cyclicality and accounting classifications can dominate short periods."],
    },
}


def explain(topic: str) -> dict[str, Any]:
    normalized = " ".join(topic.strip().lower().replace("-", " ").split())
    aliases = {"fcf": "free cash flow", "ev": "enterprise value", "rule40": "rule of 40"}
    normalized = aliases.get(normalized, normalized)
    lesson = _TOPICS.get(normalized)
    if lesson is None:
        return {
            "workflow": "explain",
            "status": "unsupported_analysis",
            "failure": {
                "error_code": "UNSUPPORTED_ANALYSIS",
                "message": f"Unsupported topic: {topic}",
            },
            "supported_topics": sorted(_TOPICS),
        }
    return {
        "workflow": "explain",
        "status": "success",
        "topic": normalized,
        **lesson,
        "boundary": "Educational content only; not a company recommendation.",
    }
