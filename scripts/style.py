"""Investor persona styles — same facts, different emphasis.

`--style=value|growth|quality|risk` reorders and highlights sections of the
brief without recalculating numbers.
"""

from __future__ import annotations

from typing import Any

STYLES = ("value", "growth", "quality", "risk")

_STYLE_BLURB = {
    "value": "Emphasis: price vs cash flows and multiples — is it cheap on what you can measure?",
    "growth": "Emphasis: top-line trajectory and whether growth is cash-funded or burn-funded.",
    "quality": "Emphasis: margins, Rule of 40, dilution, and balance-sheet durability.",
    "risk": "Emphasis: red flags, leverage, burn, and what could go wrong first.",
}


def normalize_style(raw: str | None) -> str | None:
    if not raw:
        return None
    s = raw.strip().lower()
    return s if s in STYLES else None


def style_focus(style: str, payload: dict[str, Any]) -> list[str]:
    """Ordered focus bullets for the given persona from an existing brief payload."""
    d_val = payload.get("valuation") or {}
    d_sol = payload.get("solvency") or {}
    rule = payload.get("rule40") or {}
    flags = payload.get("redflags") or []
    lines: list[str] = [_STYLE_BLURB[style], ""]

    if style == "value":
        lines.append(
            f"  Multiples: EV/S {d_val.get('ev_sales') if d_val.get('ev_sales') is not None else 'n/a'}x · "
            f"EV/EBITDA {d_val.get('ev_ebitda') if d_val.get('ev_ebitda') is not None else 'n/a'}x"
        )
        dcf = d_val.get("dcf_per_share")
        lines.append(
            f"  DCF/share: {dcf if dcf is not None else 'n/a'}"
            + (f" — {d_val.get('dcf_note')}" if dcf is None and d_val.get("dcf_note") else "")
        )
        if rule.get("preferred_score") is not None:
            lines.append(
                f"  Preferred Rule of 40: {rule['preferred_score']:.0f} vs project heuristic {rule.get('benchmark')}"
            )

    elif style == "growth":
        lines.append(f"  Revenue growth: {d_sol.get('revenue_growth_pct')}%")
        lines.append(f"  Capex intensity: {d_sol.get('capex_intensity_pct')}%")
        lines.append(f"  FCF margin: {d_sol.get('fcf_margin_pct')}%")
        if rule.get("capital_intensity_gap") is not None:
            lines.append(
                f"  Capital-intensity gap (EBITDA vs FCF Rule-40): {rule['capital_intensity_gap']:.0f} pts"
            )
        lines.append(f"  Regime: {(payload.get('regime') or 'unknown').replace('_', ' ')}")

    elif style == "quality":
        if rule.get("preferred_score") is not None:
            verdict = "PASS" if rule.get("passes") else "BELOW BAR"
            lines.append(
                f"  Rule of 40 preferred {rule['preferred_score']:.0f} vs project heuristic {rule.get('benchmark')} → {verdict}"
            )
        lines.append(f"  FCF margin: {d_sol.get('fcf_margin_pct')}%")
        lines.append(f"  Dilution: {d_sol.get('share_dilution_pct')}%")
        lines.append(f"  Net debt: {d_sol.get('net_debt')}")
        lev = d_sol.get("net_debt_to_ebitda")
        if lev is not None:
            lines.append(f"  Net debt/EBITDA: {lev}x")

    else:  # risk
        if flags:
            lines.append("  Top flags:")
            for fl in flags[:5]:
                lines.append(f"    {fl.get('severity')} {fl.get('flag')}: {fl.get('detail')}")
        else:
            lines.append("  No engine red flags tripped (still verify qualitative risks).")
        lines.append(f"  FCF margin: {d_sol.get('fcf_margin_pct')}%")
        lines.append(f"  Dilution: {d_sol.get('share_dilution_pct')}%")
        lev = d_sol.get("net_debt_to_ebitda")
        lines.append(f"  Leverage: {lev if lev is not None else 'n/a'}x net debt/EBITDA")

    return lines
