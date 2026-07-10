"""health — financial-health / solvency view as a Metric | Value | Read table.

Answers "can this company survive?" from the shared engine: leverage, whether it
funds itself from cash flow, how long its cash lasts at the current burn, and
dilution. Altman-Z and Piotroski need line items the summary fetch does not
carry; they stay pure helpers in `metrics` for callers that have those inputs,
and are not faked here.

    python scripts/health.py <TICKER> [--fixture|--json]
"""

from __future__ import annotations

import sys
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

if __package__:
    from finance_skills import analyze
    from finance_skills.cli import run_single_ticker
    from finance_skills.data import Fundamentals
    from finance_skills.format import (
        fmt_money,
        leverage_cell,
        pct,
        render_metric_table,
        source_line,
    )
else:
    import analyze
    from cli import run_single_ticker
    from data import Fundamentals
    from format import fmt_money, leverage_cell, pct, render_metric_table, source_line


def _runway(f: Fundamentals) -> tuple[str, str]:
    """Cash runway = cash ÷ annual burn, when the company is burning cash."""
    if f.total_cash is None or f.free_cash_flow is None:
        return "n/a", "cash or FCF not disclosed"
    if f.free_cash_flow >= 0:
        return "n/a", "FCF positive — self-funding, no runway question"
    years = f.total_cash / -f.free_cash_flow
    read = "tight — under ~1yr at this burn" if years < 1 else \
           "watch — 1–2yr of cash" if years < 2 else "comfortable at current burn"
    return f"{years:.1f} yr", read


def _rows(f: Fundamentals, r: dict) -> list[tuple[str, str, str]]:
    d = r["derived"]
    rows: list[tuple[str, str, str]] = []

    nd = d.get("net_debt")
    if nd is None:
        rows.append(("Net debt", "n/a", "debt or cash not disclosed — can't judge leverage"))
    elif nd < 0:
        rows.append(("Net cash", fmt_money(-nd), "more cash than debt — a solvency cushion"))
    else:
        rows.append(("Net debt", fmt_money(nd), "carries more debt than cash"))

    lev = (r.get("leverage") or {}).get("net_debt_to_ebitda")
    if lev is not None:
        value, read = leverage_cell(lev)
        rows.append(("Net debt / EBITDA", value, read))

    fcf_m = d.get("fcf_margin_pct")
    rows.append(("FCF margin", pct(fcf_m),
                 "n/a" if fcf_m is None else "self-funding" if fcf_m > 0 else "burns cash — depends on funding"))

    rv, rr = _runway(f)
    rows.append(("Cash runway", rv, rr))

    dil = d.get("share_dilution_pct")
    rows.append(("Share dilution (YoY)", pct(dil),
                 "n/a" if dil is None else "minimal" if dil <= 2 else "moderate" if dil <= 5 else "heavy — erodes per-share value"))

    # Named composites stay pure helpers in metrics until those line items are fetched.
    rows.append(("Altman Z-Score", "needs line items",
                 "working capital / retained earnings / EBIT not in fetched data"))
    rows.append(("Piotroski F-Score", "needs line items",
                 "9 YoY signals need multi-year statement detail"))
    return rows


def _verdict(f: Fundamentals, r: dict) -> str:
    d = r["derived"]
    lev = (r.get("leverage") or {}).get("net_debt_to_ebitda")
    fcf_m = d.get("fcf_margin_pct")
    if fcf_m is not None and fcf_m > 0 and (lev is None or lev < 3):
        return "Solid: self-funding with contained leverage on the fetched data."
    if fcf_m is not None and fcf_m < 0:
        rv, _ = _runway(f)
        return f"Burning cash (FCF {pct(fcf_m)}); solvency rides on funding — runway ≈ {rv}. Verify facilities/backlog."
    if lev is not None and lev >= 5:
        return "Highly levered on EBITDA — refinancing is the key risk; confirm maturities."
    return "Mixed — not enough disclosed to call it strong or fragile; check the full balance sheet."


def build_health(f: Fundamentals, as_json: bool = False):
    report = analyze.build_report(f)
    if not report.get("available", True):
        return report if as_json else analyze.format_report(report)
    rows = _rows(f, report)
    if as_json:
        return {"ticker": report["ticker"], "verdict": _verdict(f, report),
                "rows": [{"metric": m, "value": v, "read": rd} for m, v, rd in rows]}
    title = [
        f"═══ {report['name'] or report['ticker']} ({report['ticker']}) — financial health ═══",
        source_line(report),
    ]
    return render_metric_table(title, rows, verdict=_verdict(f, report))


def main(argv: list[str]) -> int:
    return run_single_ticker(
        argv,
        usage="usage: python scripts/health.py <TICKER> [--fixture] [--json]",
        build=build_health,
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
