"""Deterministic detector registry with stable IDs and structured findings."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any

if __package__:
    from finance_skills.evidence import metric_value, observation_value
else:
    from evidence import metric_value, observation_value


@dataclass(frozen=True)
class Finding:
    rule_id: str
    category: str
    title: str
    severity: str
    confidence: str
    status: str
    evidence_paths: list[str]
    explanation: str
    possible_benign_explanations: list[str]
    remediation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Rule:
    rule_id: str
    category: str
    title: str
    severity: str
    evidence_paths: list[str]
    explanation: str
    benign: list[str]
    remediation: str
    evaluate: Callable[[dict[str, Any]], bool | None]


def _obs(name: str) -> Callable[[dict[str, Any]], float | None]:
    return lambda report: observation_value(report, name)


def _missing(report: dict[str, Any]) -> bool:
    return any(
        ((report.get("observations") or {}).get(name) or {}).get("status") != "available"
        for name in ("revenue", "free_cash_flow", "total_debt", "total_cash")
    )


def _warning(report: dict[str, Any], word: str) -> bool:
    return any(word in str(item).lower() for item in report.get("warnings") or [])


def _stale(report: dict[str, Any]) -> bool | None:
    raw = report.get("retrieved_at") or report.get("data_as_of")
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            parsed = date.fromisoformat(raw[:10])
        except ValueError:
            return None
    return (date.today() - parsed).days > 120


def _ratio_greater(
    numerator: str,
    denominator: str,
    threshold: float,
) -> Callable[[dict[str, Any]], bool | None]:
    def check(report: dict[str, Any]) -> bool | None:
        num, den = observation_value(report, numerator), observation_value(report, denominator)
        if num is None or den in (None, 0):
            return None
        return abs(num / den) > threshold

    return check


def _debt_without(report: dict[str, Any], field: str) -> bool | None:
    debt = observation_value(report, "total_debt")
    if debt is None:
        return None
    value = ((report.get("observations") or {}).get(field) or {}).get("value")
    return debt > 0 and not bool(value)


def _positive_ebitda_negative_ocf(report: dict[str, Any]) -> bool | None:
    ebitda = observation_value(report, "ebitda")
    operating_cash_flow = observation_value(report, "operating_cash_flow")
    if ebitda is None or operating_cash_flow is None:
        return None
    return ebitda > 0 and operating_cash_flow < 0


def _sbc_exceeds_fcf(report: dict[str, Any]) -> bool | None:
    stock_compensation = observation_value(report, "stock_based_compensation")
    free_cash_flow = observation_value(report, "free_cash_flow")
    if stock_compensation is None or free_cash_flow is None:
        return None
    return stock_compensation > max(free_cash_flow, 0)


def _metric_at_least(concept: str, threshold: float) -> Callable[[dict[str, Any]], bool | None]:
    def check(report: dict[str, Any]) -> bool | None:
        value = metric_value(report, concept)
        return None if value is None else value >= threshold

    return check


def _buybacks_without_offset(report: dict[str, Any]) -> bool | None:
    buybacks = observation_value(report, "share_buybacks")
    dilution = metric_value(report, "share_dilution_pct")
    if buybacks is None or dilution is None:
        return None
    return buybacks > 0 and dilution > 0


def _worsening_net_debt_improving_profit(report: dict[str, Any]) -> bool | None:
    current_debt = metric_value(report, "net_debt")
    current_margin = metric_value(report, "ebitda_margin_pct")
    prior = report.get("prior_derived") or {}
    prior_debt = prior.get("net_debt")
    prior_margin = prior.get("ebitda_margin_pct")
    if (
        current_debt is None
        or current_margin is None
        or not isinstance(prior_debt, (int, float))
        or not isinstance(prior_margin, (int, float))
    ):
        return None
    return current_debt > prior_debt and current_margin > prior_margin


def _liability_growth(report: dict[str, Any]) -> bool | None:
    ca, ca0 = observation_value(report, "current_assets"), observation_value(report, "current_assets_prior")
    cl, cl0 = observation_value(report, "current_liabilities"), observation_value(report, "current_liabilities_prior")
    if None in (ca, ca0, cl, cl0) or ca0 == 0 or cl0 == 0:
        return None
    return ((cl / cl0) - 1) - ((ca / ca0) - 1) >= 0.10


def _revenue_per_share(report: dict[str, Any]) -> bool | None:
    revenue, prior = observation_value(report, "revenue"), observation_value(report, "revenue_prior")
    shares, shares_prior = observation_value(report, "shares_outstanding"), observation_value(report, "shares_prior")
    if None in (revenue, prior, shares, shares_prior) or prior == 0 or shares == 0 or shares_prior == 0:
        return None
    return revenue > prior and revenue / shares <= prior / shares_prior


def _market_balance_date_mismatch(report: dict[str, Any]) -> bool | None:
    observations = report.get("observations") or {}
    market = (observations.get("market_cap") or {}).get("period_end")
    balance = (observations.get("total_debt") or {}).get("period_end")
    if not isinstance(market, str) or not isinstance(balance, str):
        return None
    try:
        market_date = datetime.fromisoformat(market.replace("Z", "+00:00")).date()
        balance_date = datetime.fromisoformat(balance.replace("Z", "+00:00")).date()
    except ValueError:
        return None
    return abs((market_date - balance_date).days) > 120


def _rule(
    rule_id: str,
    category: str,
    title: str,
    severity: str,
    paths: list[str],
    explanation: str,
    remediation: str,
    evaluate: Callable[[dict[str, Any]], bool | None],
    benign: list[str] | None = None,
) -> Rule:
    return Rule(
        rule_id,
        category,
        title,
        severity,
        paths,
        explanation,
        benign or [],
        remediation,
        evaluate,
    )


RULES: tuple[Rule, ...] = (
    _rule("FIN-DATA-001", "data_integrity", "Required value missing", "high",
          ["$.observations"], "One or more core observations are unavailable.",
          "Verify the missing value in the latest filing.", _missing),
    _rule("FIN-DATA-002", "data_integrity", "Period mismatch", "critical",
          ["$.warnings"], "Inputs with incompatible periods cannot support the calculation.",
          "Align all inputs to a comparable period.", lambda r: _warning(r, "period")),
    _rule("FIN-DATA-003", "data_integrity", "Currency mismatch", "critical",
          ["$.warnings"], "Inputs with incompatible currencies cannot be combined.",
          "Normalize currencies using a dated, explicit FX basis.", lambda r: _warning(r, "currenc")),
    _rule("FIN-DATA-004", "data_integrity", "Stale observation", "medium",
          ["$.retrieved_at"], "The evidence is older than the default fundamentals limit.",
          "Refresh the provider data.", _stale),
    _rule("FIN-DATA-005", "data_integrity", "Conflicting source values", "high",
          ["$.observations"], "At least one observation has conflicting source confidence.",
          "Reconcile the values against a primary filing.",
          lambda r: any(v.get("confidence") == "conflicting" for v in (r.get("observations") or {}).values())),
    _rule("FIN-DATA-006", "data_integrity", "Fixture or cached data labelled live", "critical",
          ["$.data_mode", "$.observations"], "Non-live evidence is incorrectly labelled live.",
          "Correct the report data-mode label before analysis.",
          lambda r: r.get("data_mode") == "live" and any(
              v.get("source_type") == "fixture" for v in (r.get("observations") or {}).values()
          )),
    _rule("FIN-CASH-001", "cash_flow_quality", "Positive EBITDA with negative operating cash flow", "high",
          ["$.observations.ebitda", "$.observations.operating_cash_flow"],
          "Reported profitability is not converting into operating cash flow.",
          "Review the cash-flow statement and working-capital bridge.",
          _positive_ebitda_negative_ocf),
    _rule("FIN-CASH-002", "cash_flow_quality", "Working-capital movement dominates operating cash flow", "medium",
          ["$.observations.working_capital_change", "$.observations.operating_cash_flow"],
          "Working capital is a major driver of reported operating cash flow.",
          "Inspect receivables, payables, inventory, and contract balances.",
          _ratio_greater("working_capital_change", "operating_cash_flow", 0.50)),
    _rule("FIN-CASH-003", "cash_flow_quality", "Capital-expenditure definition incomplete", "medium",
          ["$.observations.capex"], "Provider capex may not capture every capitalized investment.",
          "Verify the capex definition and reconciliation in the filing.",
          lambda r: None if _obs("capex")(r) is None else (
              ((r.get("observations") or {}).get("capex") or {}).get("source_type") != "regulatory_filing"
          ), ["Provider coverage may be complete despite a non-filing label."]),
    _rule("FIN-CASH-004", "cash_flow_quality", "Provider free cash flow is not independently reconciled", "medium",
          ["$.observations.free_cash_flow", "$.observations.operating_cash_flow", "$.observations.capex"],
          "The provider-defined FCF value cannot be checked against filing primitives.",
          "Verify operating cash flow and capex in the latest filing.",
          lambda r: None if _obs("free_cash_flow")(r) is None else (
              _obs("operating_cash_flow")(r) is None or _obs("capex")(r) is None
          ), ["The provider may use a different capital-expenditure definition."]),
    _rule("FIN-CASH-005", "cash_flow_quality", "Stock-based compensation exceeds free cash flow", "high",
          ["$.observations.stock_based_compensation", "$.observations.free_cash_flow"],
          "Equity compensation is large relative to cash available after capex.",
          "Compare SBC, issuance, and diluted share count over time.",
          _sbc_exceeds_fcf),
    _rule("FIN-CASH-006", "cash_flow_quality", "Acquisition or disposal cash flows distort comparability", "medium",
          ["$.observations.acquisition_cash_flow", "$.observations.operating_cash_flow"],
          "Material transaction cash flows reduce period comparability.",
          "Separate organic operations from acquisition and disposal effects.",
          _ratio_greater("acquisition_cash_flow", "operating_cash_flow", 0.25)),
    _rule("FIN-BS-001", "balance_sheet", "Debt maturity profile unavailable", "medium",
          ["$.observations.total_debt", "$.observations.debt_maturity_profile_available"],
          "Debt exists but refinancing timing cannot be evaluated.",
          "Review the debt footnote and maturity schedule.",
          lambda r: _debt_without(r, "debt_maturity_profile_available")),
    _rule("FIN-BS-002", "balance_sheet", "Cash and debt periods do not align", "critical",
          ["$.observations.total_cash", "$.observations.total_debt"],
          "Net debt cannot be relied on when balance dates differ.",
          "Use cash and debt from the same balance-sheet date.",
          lambda r: _warning(r, "debt and cash") and _warning(r, "period")),
    _rule("FIN-BS-003", "balance_sheet", "Current liabilities outgrow current assets", "medium",
          ["$.observations.current_assets", "$.observations.current_liabilities"],
          "Near-term obligations are growing faster than near-term resources.",
          "Inspect liquidity composition and payment timing.", _liability_growth),
    _rule("FIN-BS-004", "balance_sheet", "Net debt worsens while profitability improves", "medium",
          ["$.derived.net_debt", "$.derived.ebitda_margin_pct"],
          "Improving reported profitability is accompanied by worsening leverage.",
          "Compare consistent multi-period net debt and profitability.",
          _worsening_net_debt_improving_profit),
    _rule("FIN-BS-005", "balance_sheet", "Interest burden cannot be evaluated", "medium",
          ["$.observations.total_debt", "$.observations.interest_expense"],
          "Debt exists but interest expense is unavailable.",
          "Verify interest expense and coverage in the latest filing.",
          lambda r: _debt_without(r, "interest_expense")),
    _rule("FIN-EQ-001", "shareholder_economics", "Diluted share count rises materially", "medium",
          ["$.derived.share_dilution_pct"], "Share count growth dilutes per-share participation.",
          "Review equity issuance, SBC, and diluted weighted-average shares.",
          _metric_at_least("share_dilution_pct", 2.0)),
    _rule("FIN-EQ-002", "shareholder_economics", "Revenue growth does not become revenue-per-share growth", "high",
          ["$.observations.revenue", "$.observations.shares_outstanding"],
          "Enterprise growth is not reaching shareholders on a per-share basis.",
          "Track revenue and free cash flow per diluted share.", _revenue_per_share),
    _rule("FIN-EQ-003", "shareholder_economics", "Stock-based compensation is large versus operating cash flow", "medium",
          ["$.observations.stock_based_compensation", "$.observations.operating_cash_flow"],
          "SBC consumes a material share of operating cash generation.",
          "Review SBC policy and share-count outcomes.",
          _ratio_greater("stock_based_compensation", "operating_cash_flow", 0.25)),
    _rule("FIN-EQ-004", "shareholder_economics", "Buybacks do not offset issuance", "medium",
          ["$.observations.share_buybacks", "$.derived.share_dilution_pct"],
          "Repurchases have not prevented net dilution.",
          "Compare repurchase spending with gross issuance and diluted shares.",
          _buybacks_without_offset),
    _rule("FIN-VAL-001", "valuation", "Valuation conclusion lacks comparison basis", "high",
          ["$.valuation_basis"], "Valuation language requires an explicit comparison basis.",
          "Use peers, history, an explicit scenario, or a user threshold.",
          lambda r: not bool(r.get("valuation_basis"))),
    _rule("FIN-VAL-002", "valuation", "Trailing and forward multiples are mixed", "high",
          ["$.valuation_basis"], "Mixing trailing and forward metrics invalidates the comparison.",
          "Label and compare multiples on the same basis.",
          lambda r: bool((r.get("valuation_basis") or {}).get("mixed_trailing_forward"))),
    _rule("FIN-VAL-003", "valuation", "Enterprise value dates do not align", "high",
          ["$.observations.market_cap", "$.observations.total_debt", "$.observations.total_cash"],
          "Market and balance-sheet values are too far apart in time.",
          "Use a market value dated near the balance-sheet observations.", _market_balance_date_mismatch),
    _rule("FIN-VAL-004", "valuation", "Static threshold presented as authoritative", "high",
          ["$.valuation_basis"], "A project-authored threshold cannot prove valuation.",
          "Label the threshold as a reference band and add another basis.",
          lambda r: (r.get("valuation_basis") or {}).get("type") == "project_threshold"
          and bool((r.get("valuation_basis") or {}).get("decisive"))),
    _rule("FIN-VAL-005", "valuation", "Scenario output hides assumptions", "critical",
          ["$.assumptions"], "Scenario results are invalid unless every required assumption is visible.",
          "Display growth, margin, multiple, dilution, debt/cash, and horizon.",
          lambda r: "scenarios" in r and not all(
              key in (r.get("assumptions") or {})
              for key in ("revenue_growth_pct", "margin_pct", "valuation_multiple",
                          "dilution_pct", "net_debt", "horizon_years")
          )),
    _rule("FIN-CLASS-001", "classification", "Business model inferred from ratios alone", "medium",
          ["$.classification"], "Ratios alone cannot establish a specific business model.",
          "Verify the business model from company disclosures.",
          lambda r: bool((r.get("classification") or {}).get("inferred_from_ratios"))),
    _rule("FIN-CLASS-002", "classification", "Sector classification confidence is low", "low",
          ["$.company.sector", "$.company.industry"], "Sector evidence is missing or weak.",
          "Verify sector and industry from primary disclosures.",
          lambda r: not bool((r.get("company") or {}).get("sector"))),
    _rule("FIN-CLASS-003", "classification", "Benchmark is not applicable", "medium",
          ["$.classification"], "The selected benchmark does not match the company profile.",
          "Use a company-appropriate comparison framework.",
          lambda r: (r.get("classification") or {}).get("benchmark_applicable") is False),
)


def evaluate_detectors(report: dict[str, Any], *, include_clear: bool = False) -> list[dict[str, Any]]:
    """Evaluate every registered rule without throwing on missing evidence."""
    results: list[dict[str, Any]] = []
    for rule in RULES:
        try:
            outcome = rule.evaluate(report)
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            outcome = None
        status = "triggered" if outcome is True else "clear" if outcome is False else "not_evaluated"
        if status != "triggered" and not include_clear:
            continue
        confidence = "high" if outcome is not None else "unusable"
        results.append(
            Finding(
                rule_id=rule.rule_id,
                category=rule.category,
                title=rule.title,
                severity=rule.severity,
                confidence=confidence,
                status=status,
                evidence_paths=rule.evidence_paths,
                explanation=rule.explanation if outcome is not None else "Required evidence is unavailable.",
                possible_benign_explanations=rule.benign,
                remediation=rule.remediation,
            ).to_dict()
        )
    return results


def attach_findings(report: dict[str, Any]) -> dict[str, Any]:
    report["findings"] = evaluate_detectors(report)
    report["detector_results"] = evaluate_detectors(report, include_clear=True)
    return report
