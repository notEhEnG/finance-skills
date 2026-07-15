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
    from finance_skills import metrics, report_schema
    from finance_skills.cli import run_single_ticker
    from finance_skills.data import Fundamentals
    from finance_skills.format import DISCLAIMER as DISCLAIMER
    from finance_skills.format import currency_for, fmt_money, footer, pct, source_line
else:
    import metrics
    import report_schema
    from cli import run_single_ticker
    from data import Fundamentals
    from format import DISCLAIMER as DISCLAIMER
    from format import currency_for, fmt_money, footer, pct, source_line

# Re-export presentation helpers for older call sites; prefer finance_skills.format.
_fmt_money = fmt_money
_pct = pct
_source_line = source_line
_footer = footer

# Map yfinance sector/industry text to a project-heuristic key.
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
    """Map absolute revenue to a project-heuristic stage bucket."""
    rev = f.revenue
    # The stage thresholds are denominated in USD. Do not apply them directly
    # to a known non-USD reporting currency without an explicit FX conversion.
    if rev is None or (f.currency is not None and f.currency != "USD"):
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

    period_warnings: list[str] = []

    def aligned_metric(name: str, numerator: float | None, *fields: str) -> float | None:
        if not f.periods_align(*fields):
            period_warnings.append(
                f"{name} disabled because source periods are mixed: {', '.join(fields)}"
            )
            return None
        return metrics.safe_margin(numerator, f.revenue)

    revenue_growth = (
        metrics.yoy_growth(f.revenue, f.revenue_prior)
        if f.periods_align("revenue", "revenue_prior")
        else None
    )
    if revenue_growth is None and not f.periods_align("revenue", "revenue_prior"):
        period_warnings.append("revenue growth disabled because current and prior revenue periods differ")
    gross_margin = aligned_metric("gross margin", f.gross_profit, "gross_profit", "revenue")
    ebitda_margin = aligned_metric("EBITDA margin", f.ebitda, "ebitda", "revenue")
    fcf_margin = aligned_metric("FCF margin", f.free_cash_flow, "free_cash_flow", "revenue")
    capex_intensity = aligned_metric("capex intensity", f.capex, "capex", "revenue")
    share_dilution = (
        metrics.yoy_growth(f.shares_outstanding, f.shares_prior)
        if f.periods_align("shares_outstanding", "shares_prior")
        else None
    )
    if not f.periods_align("shares_outstanding", "shares_prior"):
        period_warnings.append(
            "share dilution disabled because current and prior share-count periods differ"
        )

    net_debt = f.net_debt if f.currencies_align("total_debt", "total_cash") else None
    capital_currencies_align = f.currencies_align("market_cap", "total_debt", "total_cash")
    if f.net_debt is not None and net_debt is None:
        period_warnings.append("net debt disabled because debt and cash currencies differ")
    if f.market_cap is not None and f.net_debt is not None and not capital_currencies_align:
        period_warnings.append(
            "enterprise value disabled because market cap, debt and cash currencies differ"
        )
    enterprise_value = (
        metrics.enterprise_value(f.market_cap, net_debt)
        if capital_currencies_align
        else None
    )

    result: dict = {
        "ticker": f.ticker,
        "available": True,
        "name": f.name,
        "source": f.source,
        "data_state": f.data_state,
        "as_of": f.as_of,
        "retrieved_at": f.retrieved_at,
        "currency": f.currency,
        "source_url": f.source_url,
        "field_metadata": f.field_metadata,
        "warnings": period_warnings,
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
            "net_debt": net_debt,
            "enterprise_value": enterprise_value,
            "ev_ebitda": (
                metrics.ev_ebitda(f.market_cap, net_debt, f.ebitda)
                if capital_currencies_align else None
            ),
            "ev_sales": (
                metrics.ev_sales(f.market_cap, net_debt, f.revenue)
                if capital_currencies_align else None
            ),
        },
    }

    # Rule of 40 (segment-aware). Needs growth AND both margins — never impute.
    if revenue_growth is not None and ebitda_margin is not None and fcf_margin is not None:
        r40 = metrics.rule40_report(
            revenue_growth=revenue_growth,
            ebitda_margin=ebitda_margin,
            fcf_margin=fcf_margin,
            capex_intensity=capex_intensity,
            share_dilution=share_dilution,
            revenue=(
                f.revenue
                if f.currency is None or f.currency == "USD"
                else None
            ),
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
            + " — dual-margin EBITDA-to-FCF gap cannot be fabricated."
        )

    # DCF: fail closed. A revenue-growth extrapolation is not a defensible proxy
    # for ten years of FCF growth, so the automatic company path never emits an
    # intrinsic value. The pure metrics.dcf_* helpers remain available to callers
    # that explicitly collect and validate their own assumptions.
    dcf_blockers: list[str] = []
    if f.free_cash_flow is None:
        dcf_blockers.append("free cash flow is missing")
    elif f.free_cash_flow <= 0:
        dcf_blockers.append(
            f"free cash flow is not positive ({f.free_cash_flow:,.0f})"
        )
    if not f.shares_outstanding:
        dcf_blockers.append("shares outstanding is missing")
    if net_debt is None:
        sides = []
        if f.total_debt is None:
            sides.append("total debt")
        if f.total_cash is None:
            sides.append("total cash")
        if sides:
            dcf_blockers.append(
                "net debt unknown (" + " and ".join(sides) + " missing)"
            )
        else:
            dcf_blockers.append("net debt disabled because debt and cash currencies differ")
    dcf_blockers.append(
        "explicit FCF-growth, discount-rate, terminal-growth and forecast-horizon assumptions were not supplied"
    )
    result["dcf_note"] = "DCF disabled because " + "; ".join(dcf_blockers) + "."

    if f.ebitda and f.ebitda > 0 and net_debt is not None:
        result["leverage"] = {"net_debt_to_ebitda": round(net_debt / f.ebitda, 2)}

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
        f"Price: {fmt_money(r.get('price'), currency_for(r, 'price'))}   "
        f"Market cap: {fmt_money(r.get('market_cap'), currency_for(r, 'market_cap'))}",
        "",
        "Fundamentals (derived):",
        f"  Revenue growth (YoY): {pct(d['revenue_growth_pct'])}",
        f"  EBITDA margin: {pct(d['ebitda_margin_pct'])}   FCF margin: {pct(d['fcf_margin_pct'])}",
        f"  Capex intensity: {pct(d['capex_intensity_pct'])}   Share dilution: {pct(d['share_dilution_pct'])}",
        f"  Net debt: {fmt_money(d['net_debt'], currency_for(r))}",
    ]

    if "rule40" in r:
        x = r["rule40"]
        lines += [
            "",
            f"Rule of 40 — regime: {x['regime'].replace('_', ' ')}",
            f"  EBITDA-based: {x['score_ebitda']:.0f}   FCF-based: {x['score_fcf']:.0f}   "
            f"EBITDA-to-FCF gap: {x['capital_intensity_gap']:.0f}",
            "  EBITDA-minus-capex proxy: "
            + (
                f"{x['capex_adjusted_score']:.0f}"
                if x.get("capex_adjusted_score") is not None else "n/a"
            )
            + "   dilution-adjusted: "
            + (
                f"{x['dilution_adjusted_score']:.0f}"
                if x.get("dilution_adjusted_score") is not None else "n/a"
            ),
            f"  Judged on {x['preferred_score']:.0f} vs project heuristic {x['benchmark']:.0f} "
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
            f"DCF (simple 2-stage): intrinsic ≈ {fmt_money(dcf['per_share'], currency_for(r))}/share "
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
                    f"    {name}: {fmt_money(row['per_share'], currency_for(r))} "
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
    if not as_json:
        return format_report(r)
    return report_schema.enrich_report_for_agent(f, r, dict(r), intent="analyze")


def main(argv: list[str]) -> int:
    return run_single_ticker(
        argv,
        usage="usage: python scripts/analyze.py <TICKER> [--fixture] [--json]",
        build=build_report_view,
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
