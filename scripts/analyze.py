"""analyze — the flagship orchestrator.

Fetches fundamentals (data.py), derives the inputs, runs the pure engine
(metrics.py), and formats an analyst-style report. Every specialised command
in the skill (valuation, growth, risk, rule40, ai-cloud, ...) is a view over
this same engine, so there is one source of truth for the numbers.

`build_report` always returns a structured dict. Use `format_report` for text.
Views never recompute for formatting.

Usage:
    python scripts/analyze.py <TICKER> [--fixture] [--json]
"""

from __future__ import annotations

import sys
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

if __package__:
    from finance_skills import metrics
    from finance_skills.cli import run_single_ticker
    from finance_skills.data import Fundamentals
    from finance_skills.format import DISCLAIMER as DISCLAIMER
    from finance_skills.format import fmt_money, footer, pct, source_line
else:
    import metrics
    from cli import run_single_ticker
    from data import Fundamentals
    from format import DISCLAIMER as DISCLAIMER
    from format import fmt_money, footer, pct, source_line

# Re-export presentation helpers for older call sites; prefer finance_skills.format.
_fmt_money = fmt_money
_pct = pct
_source_line = source_line
_footer = footer

# Map yfinance sector/industry text to a benchmark key in metrics.SECTOR_BENCHMARKS.
_SECTOR_HINTS = [
    ("cyber", "cybersecurity"),
    ("security", "cybersecurity"),
    ("fintech", "fintech"),
    ("financial", "fintech"),
    ("software", "ai_ml_saas"),
    ("information technology services", "ai_ml_saas"),
]


def _sector_key(f: Fundamentals) -> str | None:
    text = f" {f.sector or ''} {f.industry or ''} ".lower()
    for hint, key in _SECTOR_HINTS:
        if hint in text:
            return key
    return None


def _stage_key(f: Fundamentals) -> str | None:
    """Map absolute revenue to a STAGE_BENCHMARKS bucket, so the stage-matched
    Rule 40 bar binds when we can't identify a sector. `sector_key` still wins
    when it resolves; this only fills the gap the regime fallback used to cover."""
    rev = f.revenue
    if rev is None:
        return None
    if rev < 1_000_000:
        return "early_stage"
    if rev < 100_000_000:
        return "growth_stage"
    return "mature"


def build_report(f: Fundamentals) -> dict:
    """Always return a structured engine report (never a rendered string)."""
    if not f.available:
        return {"ticker": f.ticker, "available": False, "error": f.error}

    revenue_growth = metrics.yoy_growth(f.revenue, f.revenue_prior)
    gross_margin = metrics.safe_margin(f.gross_profit, f.revenue)
    ebitda_margin = metrics.safe_margin(f.ebitda, f.revenue)
    fcf_margin = metrics.safe_margin(f.free_cash_flow, f.revenue)
    capex_intensity = metrics.safe_margin(f.capex, f.revenue)
    share_dilution = metrics.yoy_growth(f.shares_outstanding, f.shares_prior)

    result: dict = {
        "ticker": f.ticker,
        "available": True,
        "name": f.name,
        "source": f.source,
        "as_of": f.as_of,
        "sector": f.sector,
        "industry": f.industry,
        "price": f.price,
        "market_cap": f.market_cap,
        "derived": {
            "revenue": f.revenue,
            "revenue_growth_pct": revenue_growth,
            "gross_margin_pct": gross_margin,
            "ebitda_margin_pct": ebitda_margin,
            "fcf_margin_pct": fcf_margin,
            "capex_intensity_pct": capex_intensity,
            "share_dilution_pct": share_dilution,
            "net_debt": f.net_debt,
            "enterprise_value": metrics.enterprise_value(f.market_cap, f.net_debt),
            "ev_ebitda": metrics.ev_ebitda(f.market_cap, f.net_debt, f.ebitda),
            "ev_sales": metrics.ev_sales(f.market_cap, f.net_debt, f.revenue),
        },
    }

    # Rule of 40 (segment-aware). Needs growth AND both margins — never impute.
    if revenue_growth is not None and ebitda_margin is not None and fcf_margin is not None:
        r40 = metrics.rule40_report(
            revenue_growth=revenue_growth,
            ebitda_margin=ebitda_margin,
            fcf_margin=fcf_margin,
            capex_intensity=capex_intensity or 0.0,
            share_dilution=share_dilution or 0.0,
            revenue=f.revenue,
            stage=_stage_key(f),
            sector_key=_sector_key(f),
        )
        result["rule40"] = r40.to_dict()
    else:
        parts: list[str] = []
        if revenue_growth is None:
            parts.append("revenue growth (need current + prior revenue)")
        if ebitda_margin is None:
            parts.append("EBITDA margin (need EBITDA + revenue)")
        if fcf_margin is None:
            parts.append("FCF margin (need free cash flow + revenue)")
        result["rule40_note"] = (
            "Rule of 40 skipped because "
            + ("; ".join(parts) if parts else "required inputs missing")
            + " — dual-margin capital-intensity gap cannot be fabricated."
        )

    # DCF: fail-closed with precise missing-input reasons + scenarios when runnable.
    dcf_blockers: list[str] = []
    if f.free_cash_flow is None:
        dcf_blockers.append("free cash flow is missing")
    elif f.free_cash_flow <= 0:
        dcf_blockers.append(
            f"free cash flow is not positive ({f.free_cash_flow:,.0f}; typical for capex-heavy growth)"
        )
    if not f.shares_outstanding:
        dcf_blockers.append("shares outstanding is missing")
    if f.net_debt is None:
        sides = []
        if f.total_debt is None:
            sides.append("total debt")
        if f.total_cash is None:
            sides.append("total cash")
        dcf_blockers.append(
            "net debt unknown (" + " and ".join(sides or ["debt/cash"]) + " missing)"
        )

    if not dcf_blockers:
        try:
            base = revenue_growth if revenue_growth is not None else 8.0
            g = min(base, 25.0)
            result["dcf"] = metrics.dcf_intrinsic_value(
                fcf=f.free_cash_flow,
                growth_rate=g,
                shares_outstanding=f.shares_outstanding,
                net_debt=f.net_debt,
            )
            growth_src = (
                "default 8% (no trailing growth available)"
                if revenue_growth is None
                else f"trailing revenue growth {revenue_growth:.1f}%"
            )
            result["dcf_basis"] = (
                f"Heuristic estimate — growth from {growth_src}, modelled at {g:.1f}% "
                "(capped at 25%); discount 10%, terminal 3%. Highly sensitive to these "
                "assumptions; treat as a rough anchor, not a target price."
            )
            result["dcf_scenarios"] = metrics.dcf_scenarios(
                fcf=f.free_cash_flow,
                base_growth=g,
                shares_outstanding=f.shares_outstanding,
                net_debt=f.net_debt,
                price=f.price,
            )
        except ValueError as exc:
            result["dcf_note"] = str(exc)
    else:
        result["dcf_note"] = "DCF skipped because " + "; ".join(dcf_blockers) + "."

    if f.ebitda and f.ebitda > 0 and f.net_debt is not None:
        result["leverage"] = {"net_debt_to_ebitda": round(f.net_debt / f.ebitda, 2)}

    return result


def format_report(r: dict) -> str:
    """Render a structured engine report as the flagship text dump."""
    if not r.get("available", True):
        return (
            f"Live data for {r.get('ticker', '?')} is unavailable ({r.get('error')}).\n"
            "Live fetching needs yfinance + network, which run on Claude Code but not the "
            "Claude.ai sandbox. Try `--fixture` if a sample exists, or run on Claude Code."
        )

    d = r["derived"]
    lines = [
        f"═══ {r['name'] or r['ticker']} ({r['ticker']}) ═══",
        source_line(r),
        f"Sector: {r.get('sector') or 'n/a'} / {r.get('industry') or 'n/a'}",
        f"Price: {fmt_money(r.get('price'))}   Market cap: {fmt_money(r.get('market_cap'))}",
        "",
        "Fundamentals (derived):",
        f"  Revenue growth (YoY): {pct(d['revenue_growth_pct'])}",
        f"  EBITDA margin: {pct(d['ebitda_margin_pct'])}   FCF margin: {pct(d['fcf_margin_pct'])}",
        f"  Capex intensity: {pct(d['capex_intensity_pct'])}   Share dilution: {pct(d['share_dilution_pct'])}",
        f"  Net debt: {fmt_money(d['net_debt'])}",
    ]

    if "rule40" in r:
        x = r["rule40"]
        lines += [
            "",
            f"Rule of 40 — regime: {x['regime'].replace('_', ' ')}",
            f"  EBITDA-based: {x['score_ebitda']:.0f}   FCF-based: {x['score_fcf']:.0f}   "
            f"capital-intensity gap: {x['capital_intensity_gap']:.0f}",
            f"  Capex-adjusted: {x['capex_adjusted_score']:.0f}   "
            f"dilution-adjusted: {x['dilution_adjusted_score']:.0f}",
            f"  Judged on {x['preferred_score']:.0f} vs benchmark {x['benchmark']:.0f} "
            f"→ {'PASS' if x['passes'] else 'BELOW BAR'}",
            f"  Verdict: {x['verdict']}",
        ]
        for note in x["notes"]:
            lines.append(f"    • {note}")
    elif "rule40_note" in r:
        lines += ["", f"Rule of 40: {r['rule40_note']}"]

    if "dcf" in r:
        dcf = r["dcf"]
        lines += [
            "",
            f"DCF (simple 2-stage): intrinsic ≈ {fmt_money(dcf['per_share'])}/share "
            f"(g={dcf['assumptions']['growth_rate']}%, r={dcf['assumptions']['discount_rate']}%)",
        ]
        if "dcf_basis" in r:
            lines.append(f"  {r['dcf_basis']}")
        sc = r.get("dcf_scenarios") or {}
        if sc.get("growth"):
            lines.append("  Scenarios (per share):")
            for name, row in sc["growth"].items():
                vs = row.get("vs_price_pct")
                vs_s = f", {vs:+.1f}% vs price" if vs is not None else ""
                lines.append(
                    f"    {name}: {fmt_money(row['per_share'])} "
                    f"(g={row['growth_rate']}%, r={row['discount_rate']}%){vs_s}"
                )
    elif "dcf_note" in r:
        lines += ["", f"DCF: {r['dcf_note']}"]

    if "leverage" in r:
        lines += [f"Leverage: net debt / EBITDA = {r['leverage']['net_debt_to_ebitda']}x"]

    lines += ["", *footer()]
    return "\n".join(lines)


def build_report_view(f: Fundamentals, as_json: bool = False):
    """View adapter for the shared CLI / export registry."""
    r = build_report(f)
    return r if as_json else format_report(r)


def main(argv: list[str]) -> int:
    return run_single_ticker(
        argv,
        usage="usage: python scripts/analyze.py <TICKER> [--fixture] [--json]",
        build=build_report_view,
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
