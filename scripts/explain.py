"""Plain-language "why this matters" for engine metrics.

Educational layer only — no new math. Used by `--explain` on brief/valuation
and as a quick reference for agents composing answer-first replies.
"""

from __future__ import annotations

from typing import Any

# Metric key → one-line implication for a general investor.
WHY: dict[str, str] = {
    "rule40": (
        "Rule of 40 balances growth against profitability; a pass means the business "
        "is compounding without destroying unit economics (judge on the preferred score for its regime)."
    ),
    "capital_intensity_gap": (
        "A large EBITDA-vs-FCF gap means growth is funded by capex or working capital, "
        "not free cash — common in neoclouds, risky if funding dries up."
    ),
    "revenue_growth": (
        "Top-line growth drives the equity story, but without positive FCF or a clear path "
        "to it, high growth can still destroy value."
    ),
    "fcf_margin": (
        "Free-cash-flow margin shows whether the company funds itself; negative means it "
        "depends on markets, debt, or cash stockpiles to keep growing."
    ),
    "ebitda_margin": (
        "EBITDA margin is operating profitability before capex; useful, but can flatter "
        "capital-heavy businesses — always compare to FCF."
    ),
    "gross_margin": (
        "Gross margin is a fingerprint of pricing power and cost structure; high, stable "
        "margins often support moat narratives (still verify competitively)."
    ),
    "ev_sales": (
        "EV/Sales prices the firm on revenue when earnings or FCF are weak; very high "
        "multiples require sustained growth and eventual cash conversion."
    ),
    "ev_ebitda": (
        "EV/EBITDA is capital-structure-neutral vs peers; meaningless if EBITDA is distorted "
        "or near zero — prefer EV/Sales then."
    ),
    "dcf": (
        "DCF anchors a rough intrinsic value under explicit assumptions; tiny changes in "
        "growth or discount rate swing the number — use scenarios, not one printout."
    ),
    "dilution": (
        "Share-count growth dilutes existing owners; revenue 'bought' with equity is less "
        "valuable per share than organic growth."
    ),
    "net_debt": (
        "Net debt (debt − cash) drives leverage and DCF equity value; unknown net debt "
        "means multiples and per-share intrinsic value cannot be trusted."
    ),
    "capex_intensity": (
        "Capex/revenue shows how much hard investment growth requires; high intensity "
        "compresses FCF even when EBITDA looks fine."
    ),
    "leverage": (
        "Net debt/EBITDA gauges refinancing risk; elevated leverage is dangerous if growth "
        "or rates turn against the company."
    ),
}


def why_lines_for_report(report: dict[str, Any]) -> list[dict[str, str]]:
    """Pick implications that apply to the numbers actually present in the report."""
    d = report.get("derived") or {}
    out: list[dict[str, str]] = []

    def add(key: str) -> None:
        if key in WHY:
            out.append({"metric": key, "why": WHY[key]})

    if report.get("rule40"):
        add("rule40")
        gap = (report["rule40"] or {}).get("capital_intensity_gap")
        if gap is not None and gap > 20:
            add("capital_intensity_gap")
    if d.get("revenue_growth_pct") is not None:
        add("revenue_growth")
    if d.get("fcf_margin_pct") is not None:
        add("fcf_margin")
    if d.get("ebitda_margin_pct") is not None:
        add("ebitda_margin")
    if d.get("gross_margin_pct") is not None:
        add("gross_margin")
    if d.get("ev_sales") is not None:
        add("ev_sales")
    if d.get("ev_ebitda") is not None:
        add("ev_ebitda")
    if "dcf" in report:
        add("dcf")
    if d.get("share_dilution_pct") is not None:
        add("dilution")
    if d.get("net_debt") is not None:
        add("net_debt")
    if d.get("capex_intensity_pct") is not None:
        add("capex_intensity")
    if report.get("leverage"):
        add("leverage")
    return out


def render_why(items: list[dict[str, str]]) -> list[str]:
    if not items:
        return ["Why this matters: (no computed metrics to explain)"]
    lines = ["Why this matters"]
    for it in items:
        label = it["metric"].replace("_", " ")
        lines.append(f"  · {label}: {it['why']}")
    return lines
