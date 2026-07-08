"""analyze — the flagship orchestrator.

Fetches fundamentals (data.py), derives the inputs, runs the pure engine
(metrics.py), and formats an analyst-style report. Every specialised command
in the skill (valuation, growth, risk, rule40, ai-cloud, ...) is a view over
this same engine, so there is one source of truth for the numbers.

Usage:
    python scripts/analyze.py <TICKER> [--fixture] [--json]

`--fixture` forces the offline sample record (handy where the network/yfinance
is unavailable, e.g. the Claude.ai sandbox).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import metrics
from data import Fundamentals, get_fundamentals_or_fixture, load_fixture

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


def build_report(f: Fundamentals, as_json: bool = False):
    if not f.available:
        msg = (
            f"Live data for {f.ticker} is unavailable ({f.error}).\n"
            "Live fetching needs yfinance + network, which run on Claude Code but not the "
            "Claude.ai sandbox. Try `--fixture` if a sample exists, or run on Claude Code."
        )
        return {"ticker": f.ticker, "available": False, "error": f.error} if as_json else msg

    revenue_growth = metrics.yoy_growth(f.revenue, f.revenue_prior)
    ebitda_margin = metrics.safe_margin(f.ebitda, f.revenue)
    fcf_margin = metrics.safe_margin(f.free_cash_flow, f.revenue)
    capex_intensity = metrics.safe_margin(f.capex, f.revenue)
    share_dilution = metrics.yoy_growth(f.shares_outstanding, f.shares_prior)

    result: dict = {
        "ticker": f.ticker,
        "name": f.name,
        "source": f.source,
        "as_of": f.as_of,
        "sector": f.sector,
        "industry": f.industry,
        "price": f.price,
        "market_cap": f.market_cap,
        "derived": {
            "revenue_growth_pct": revenue_growth,
            "ebitda_margin_pct": ebitda_margin,
            "fcf_margin_pct": fcf_margin,
            "capex_intensity_pct": capex_intensity,
            "share_dilution_pct": share_dilution,
            "net_debt": f.net_debt,
        },
    }

    # Rule of 40 (segment-aware). The engine's whole value is the EBITDA-vs-FCF
    # capital-intensity gap, so it needs growth AND both margins — imputing the
    # missing one from the other would zero out that gap and make the two scores
    # look independently observed. If a margin is missing, skip and say why.
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
    elif revenue_growth is not None:
        if ebitda_margin is None and fcf_margin is None:
            missing = "EBITDA and FCF margins are"
        else:
            missing = ("FCF margin is" if fcf_margin is None else "EBITDA margin is")
        result["rule40_note"] = (
            f"Rule of 40 skipped: {missing} unavailable, so the EBITDA-vs-FCF "
            "capital-intensity gap can't be computed without fabricating a margin."
        )

    # DCF only makes sense on positive FCF; say so otherwise.
    if f.free_cash_flow is not None and f.free_cash_flow > 0 and f.shares_outstanding:
        try:
            # Growth is a heuristic: trailing revenue growth, capped at 25% so the
            # 2-stage model can't compound a runaway rate. Explicit None check so a
            # genuine 0% is not silently read as "missing" and bumped to 8%.
            base = revenue_growth if revenue_growth is not None else 8.0
            g = min(base, 25.0)
            result["dcf"] = metrics.dcf_intrinsic_value(
                fcf=f.free_cash_flow, growth_rate=g,
                shares_outstanding=f.shares_outstanding, net_debt=f.net_debt or 0.0,
            )
            growth_src = "default 8% (no trailing growth available)" if revenue_growth is None \
                else f"trailing revenue growth {revenue_growth:.1f}%"
            result["dcf_basis"] = (
                f"Heuristic estimate — growth from {growth_src}, modelled at {g:.1f}% "
                "(capped at 25%); discount 10%, terminal 3%. Highly sensitive to these "
                "assumptions; treat as a rough anchor, not a target price."
            )
        except ValueError as exc:
            result["dcf_note"] = str(exc)
    else:
        result["dcf_note"] = "DCF skipped: free cash flow is not positive (typical for capex-heavy growth names)."

    # Lightweight leverage read.
    if f.ebitda and f.ebitda > 0 and f.net_debt is not None:
        result["leverage"] = {"net_debt_to_ebitda": round(f.net_debt / f.ebitda, 2)}

    return result if as_json else _format(result)


def _fmt_money(v) -> str:
    if v is None:
        return "n/a"
    a = abs(v)
    for unit, scale in (("T", 1e12), ("B", 1e9), ("M", 1e6)):
        if a >= scale:
            return f"${v/scale:.2f}{unit}"
    return f"${v:,.0f}"


def _pct(v) -> str:
    return "n/a" if v is None else f"{v:.1f}%"


def _format(r: dict) -> str:
    d = r["derived"]
    lines = [
        f"═══ {r['name'] or r['ticker']} ({r['ticker']}) ═══",
        f"Source: {r['source']} · as of {r['as_of']}"
        + ("  [SAMPLE DATA — not live]" if r["source"] == "fixture" else ""),
        f"Sector: {r.get('sector') or 'n/a'} / {r.get('industry') or 'n/a'}",
        f"Price: {_fmt_money(r.get('price'))}   Market cap: {_fmt_money(r.get('market_cap'))}",
        "",
        "Fundamentals (derived):",
        f"  Revenue growth (YoY): {_pct(d['revenue_growth_pct'])}",
        f"  EBITDA margin: {_pct(d['ebitda_margin_pct'])}   FCF margin: {_pct(d['fcf_margin_pct'])}",
        f"  Capex intensity: {_pct(d['capex_intensity_pct'])}   Share dilution: {_pct(d['share_dilution_pct'])}",
        f"  Net debt: {_fmt_money(d['net_debt'])}",
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
            f"DCF (simple 2-stage): intrinsic ≈ {_fmt_money(dcf['per_share'])}/share "
            f"(g={dcf['assumptions']['growth_rate']}%, r={dcf['assumptions']['discount_rate']}%)",
        ]
        if "dcf_basis" in r:
            lines.append(f"  {r['dcf_basis']}")
    elif "dcf_note" in r:
        lines += ["", f"DCF: {r['dcf_note']}"]

    if "leverage" in r:
        lines += [f"Leverage: net debt / EBITDA = {r['leverage']['net_debt_to_ebitda']}x"]

    lines += [
        "",
        "─" * 60,
        "Read-only market analysis for research/education. Not investment advice; "
        "no trades are placed. Verify figures against primary filings before acting.",
    ]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}
    if not args:
        print("usage: python scripts/analyze.py <TICKER> [--fixture] [--json]", file=sys.stderr)
        return 2

    ticker = args[0].upper()
    if "--fixture" in flags:
        f = load_fixture(ticker) or Fundamentals(ticker=ticker, available=False, error="no fixture for this ticker")
    else:
        f = get_fundamentals_or_fixture(ticker)

    report = build_report(f, as_json="--json" in flags)
    print(json.dumps(report, indent=2) if "--json" in flags else report)
    return 0 if (isinstance(report, str) or report.get("available", True)) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
