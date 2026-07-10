"""Precise missing-data diagnostics and filing verification checklist.

Fail-closed companion to the engine: name which inputs are missing and which
analyses are disabled — never a generic "n/a". Also lists what to verify in
primary filings before trusting yfinance-backed output.
"""

from __future__ import annotations

from typing import Any

if __package__:
    from finance_skills.data import Fundamentals
else:
    from data import Fundamentals


def _missing_fundamentals(f: Fundamentals) -> list[str]:
    """Human-readable list of missing raw inputs on the Fundamentals record."""
    miss: list[str] = []
    if f.revenue is None:
        miss.append("revenue")
    if f.revenue_prior is None:
        miss.append("prior-year revenue")
    if f.gross_profit is None:
        miss.append("gross profit")
    if f.ebitda is None:
        miss.append("EBITDA")
    if f.free_cash_flow is None:
        miss.append("free cash flow")
    if f.capex is None:
        miss.append("capex")
    if f.total_debt is None:
        miss.append("total debt")
    if f.total_cash is None:
        miss.append("total cash")
    if f.shares_outstanding is None:
        miss.append("shares outstanding")
    if f.shares_prior is None:
        miss.append("prior share count")
    if f.market_cap is None:
        miss.append("market cap")
    if f.price is None:
        miss.append("price")
    return miss


def disabled_analyses(f: Fundamentals, report: dict[str, Any]) -> list[dict[str, Any]]:
    """Analyses the engine could not run, with exact missing inputs and reasons."""
    d = report.get("derived") or {}
    out: list[dict[str, Any]] = []

    def add(analysis: str, reason: str, missing: list[str], unlocks: str) -> None:
        out.append({
            "analysis": analysis,
            "reason": reason,
            "missing_inputs": missing,
            "unlocks": unlocks,
        })

    # Rule of 40
    if "rule40" not in report:
        miss: list[str] = []
        if d.get("revenue_growth_pct") is None:
            if f.revenue is None:
                miss.append("revenue")
            if f.revenue_prior is None:
                miss.append("prior-year revenue")
        if d.get("ebitda_margin_pct") is None:
            if f.ebitda is None:
                miss.append("EBITDA")
            if f.revenue is None and "revenue" not in miss:
                miss.append("revenue")
        if d.get("fcf_margin_pct") is None:
            if f.free_cash_flow is None:
                miss.append("free cash flow")
            if f.revenue is None and "revenue" not in miss:
                miss.append("revenue")
        add(
            "rule40",
            report.get("rule40_note")
            or "dual-margin Rule of 40 needs growth + EBITDA margin + FCF margin",
            miss or ["growth and/or margins"],
            "income statement (revenue, EBITDA) + cash flow (FCF) for two periods",
        )

    # DCF — spell out each gate
    if "dcf" not in report:
        miss = []
        reason_parts: list[str] = []
        if f.free_cash_flow is None:
            miss.append("free cash flow")
            reason_parts.append("free cash flow is missing")
        elif f.free_cash_flow <= 0:
            miss.append("positive free cash flow")
            reason_parts.append(
                f"free cash flow is not positive ({f.free_cash_flow:,.0f})"
            )
        if not f.shares_outstanding:
            miss.append("shares outstanding")
            reason_parts.append("shares outstanding is missing")
        if f.net_debt is None:
            if f.total_debt is None:
                miss.append("total debt")
            if f.total_cash is None:
                miss.append("total cash")
            reason_parts.append("net debt unknown (need both debt and cash)")
        reason = report.get("dcf_note") or (
            "DCF skipped because " + "; ".join(reason_parts)
            if reason_parts
            else "DCF not computed"
        )
        # Prefer precise composed reason when we can
        if reason_parts:
            reason = "DCF skipped because " + "; ".join(reason_parts)
        add(
            "dcf",
            reason,
            miss,
            "positive FCF + shares outstanding + total debt + cash on the balance sheet",
        )

    # EV multiples
    if d.get("enterprise_value") is None:
        miss = []
        if f.market_cap is None:
            miss.append("market cap")
        if f.net_debt is None:
            if f.total_debt is None:
                miss.append("total debt")
            if f.total_cash is None:
                miss.append("total cash")
        add(
            "enterprise_value",
            "EV (and EV multiples) need market cap and known net debt",
            miss,
            "market cap + balance sheet debt and cash",
        )
    else:
        if d.get("ev_ebitda") is None:
            miss = []
            if f.ebitda is None or (f.ebitda is not None and f.ebitda <= 0):
                miss.append("positive EBITDA")
            add(
                "ev_ebitda",
                "EV/EBITDA needs positive EBITDA and known EV",
                miss or ["positive EBITDA"],
                "income statement EBITDA",
            )
        if d.get("ev_sales") is None:
            miss = []
            if f.revenue is None or (f.revenue is not None and f.revenue <= 0):
                miss.append("positive revenue")
            add(
                "ev_sales",
                "EV/Sales needs positive revenue and known EV",
                miss or ["positive revenue"],
                "income statement revenue",
            )

    # Leverage
    if "leverage" not in report:
        miss = []
        if f.ebitda is None or (f.ebitda is not None and f.ebitda <= 0):
            miss.append("positive EBITDA")
        if f.net_debt is None:
            if f.total_debt is None:
                miss.append("total debt")
            if f.total_cash is None:
                miss.append("total cash")
        add(
            "net_debt_to_ebitda",
            "leverage ratio needs known net debt and positive EBITDA",
            miss,
            "balance sheet debt/cash + income statement EBITDA",
        )

    # Growth
    if d.get("revenue_growth_pct") is None:
        miss = []
        if f.revenue is None:
            miss.append("revenue")
        if f.revenue_prior is None:
            miss.append("prior-year revenue")
        add(
            "revenue_growth",
            "YoY growth needs current and prior revenue",
            miss,
            "two periods of revenue on the income statement",
        )

    return out


def filing_checklist(report: dict[str, Any] | None = None) -> list[dict[str, str]]:
    """What to verify in 10-K/10-Q before trusting summary-feed output."""
    items = [
        {"item": "revenue", "where": "Income statement — total revenue (and segments if material)",
         "why": "Growth and margins start here; feed errors show up first as wrong growth."},
        {"item": "free cash flow", "where": "Cash flow statement — operating CF − capex (or disclosed FCF)",
         "why": "FCF margin, DCF, and self-funding claims depend on it."},
        {"item": "capex", "where": "Cash flow — capital expenditures",
         "why": "Capital intensity and neocloud/GPU burn narratives."},
        {"item": "total debt", "where": "Balance sheet — short + long-term debt / total debt",
         "why": "Net debt, EV, leverage, and DCF equity bridge."},
        {"item": "cash", "where": "Balance sheet — cash and cash equivalents (and short-term investments if used)",
         "why": "Net debt and cash runway."},
        {"item": "share count", "where": "Cover / diluted shares outstanding (and share activity note)",
         "why": "Per-share DCF and dilution YoY."},
        {"item": "EBITDA / operating income", "where": "Income statement or non-GAAP reconciliation",
         "why": "Margins, EV/EBITDA, leverage; watch non-operating inflation."},
        {"item": "segment / backlog notes", "where": "MD&A, backlog/RPO, remaining performance obligations",
         "why": "Not in summary feeds; critical for AI infra and multi-segment names."},
    ]
    # Highlight items that the current report already shows as gaps
    if report:
        disabled = {d["analysis"] for d in (report.get("disabled") or [])}
        gap_fields = {g.get("field") for g in (report.get("gaps") or [])}
        for it in items:
            if it["item"] in ("total debt", "cash") and (
                "dcf" in disabled or "enterprise_value" in disabled or "net_debt" in gap_fields
            ):
                it["priority"] = "high — missing in this run"
            elif it["item"] == "free cash flow" and "dcf" in disabled:
                it["priority"] = "high — missing or non-positive in this run"
            elif it["item"] == "share count" and any(
                "shares" in m for d in (report.get("disabled") or []) for m in d.get("missing_inputs", [])
            ):
                it["priority"] = "high — missing in this run"
            else:
                it.setdefault("priority", "standard")
    else:
        for it in items:
            it["priority"] = "standard"
    return items


def render_disabled(items: list[dict[str, Any]]) -> list[str]:
    if not items:
        return ["Disabled analyses: none — core set computable from fetched inputs"]
    lines = ["Disabled analyses (exact inputs)"]
    for it in items:
        miss = ", ".join(it["missing_inputs"]) if it["missing_inputs"] else "—"
        lines.append(f"  · {it['analysis']}: {it['reason']}")
        lines.append(f"      missing: {miss}")
        lines.append(f"      unlocks via: {it['unlocks']}")
    return lines


def render_filing_checklist(items: list[dict[str, str]]) -> list[str]:
    lines = ["Filing verification checklist (before trusting this output)"]
    for it in items:
        pri = it.get("priority", "standard")
        tag = f" [{pri}]" if pri.startswith("high") else ""
        lines.append(f"  · {it['item']}{tag}")
        lines.append(f"      where: {it['where']}")
        lines.append(f"      why: {it['why']}")
    return lines
