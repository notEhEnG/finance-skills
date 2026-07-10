"""health — financial-health / solvency view as a Metric | Value | Read table.

Answers "can this company survive?" from the shared engine: leverage, whether it
funds itself from cash flow, how long its cash lasts at the current burn, and
dilution. Altman-Z and Piotroski are named but flagged "needs line items not
fetched" — they require working capital / retained earnings / EBIT detail that
the summary financials here don't carry, and the honesty rule forbids faking a
score. `metrics.altman_z` / `metrics.piotroski_f_score` exist for callers that
do have those inputs.

    python scripts/health.py <TICKER> [--fixture|--json]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:  # installed as the `finance_skills` package…
    from finance_skills import analyze
    from finance_skills.analyze import _fmt_money, _pct
    from finance_skills.data import Fundamentals, get_fundamentals_or_fixture, load_fixture
except ImportError:  # …or run directly via `python3 scripts/health.py` (skill path)
    import analyze
    from analyze import _fmt_money, _pct
    from data import Fundamentals, get_fundamentals_or_fixture, load_fixture


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
        rows.append(("Net cash", _fmt_money(-nd), "more cash than debt — a solvency cushion"))
    else:
        rows.append(("Net debt", _fmt_money(nd), "carries more debt than cash"))

    lev = r.get("leverage", {}).get("net_debt_to_ebitda")
    if lev is not None:
        if lev < 0:
            rows.append(("Net debt / EBITDA", f"net cash ({abs(lev)}x)", "no leverage risk"))
        else:
            read = "low" if lev < 3 else "elevated — watch refinancing" if lev < 5 else "high — stress on any downturn"
            rows.append(("Net debt / EBITDA", f"{lev}x", read))

    fcf_m = d.get("fcf_margin_pct")
    rows.append(("FCF margin", _pct(fcf_m),
                 "n/a" if fcf_m is None else "self-funding" if fcf_m > 0 else "burns cash — depends on funding"))

    rv, rr = _runway(f)
    rows.append(("Cash runway", rv, rr))

    dil = d.get("share_dilution_pct")
    rows.append(("Share dilution (YoY)", _pct(dil),
                 "n/a" if dil is None else "minimal" if dil <= 2 else "moderate" if dil <= 5 else "heavy — erodes per-share value"))

    # Named-but-not-computable composite scores (honesty rule).
    rows.append(("Altman Z-Score", "needs line items",
                 "working capital / retained earnings / EBIT not in fetched data — see metrics.altman_z"))
    rows.append(("Piotroski F-Score", "needs line items",
                 "9 YoY signals need multi-year statement detail — see metrics.piotroski_f_score"))
    return rows


def _verdict(f: Fundamentals, r: dict) -> str:
    d = r["derived"]
    lev = r.get("leverage", {}).get("net_debt_to_ebitda")
    fcf_m = d.get("fcf_margin_pct")
    if fcf_m is not None and fcf_m > 0 and (lev is None or lev < 3):
        return "Solid: self-funding with contained leverage on the fetched data."
    if fcf_m is not None and fcf_m < 0:
        rv, _ = _runway(f)
        return f"Burning cash (FCF {_pct(fcf_m)}); solvency rides on funding — runway ≈ {rv}. Verify facilities/backlog."
    if lev is not None and lev >= 5:
        return "Highly levered on EBITDA — refinancing is the key risk; confirm maturities."
    return "Mixed — not enough disclosed to call it strong or fragile; check the full balance sheet."


def build_health(f: Fundamentals, as_json: bool = False):
    report = analyze.build_report(f, as_json=True)
    if isinstance(report, dict) and not report.get("available", True):
        return report if as_json else analyze.build_report(f, as_json=False)
    rows = _rows(f, report)
    if as_json:
        return {"ticker": report["ticker"], "verdict": _verdict(f, report),
                "rows": [{"metric": m, "value": v, "read": rd} for m, v, rd in rows]}
    return _render(report, rows, _verdict(f, report))


def _render(r: dict, rows: list[tuple[str, str, str]], verdict: str) -> str:
    mw = max(len(m) for m, _, _ in rows)
    vw = max(len(v) for _, v, _ in rows)
    out = [
        f"═══ {r['name'] or r['ticker']} ({r['ticker']}) — financial health ═══",
        analyze._source_line(r),
        "",
        f"  {'Metric'.ljust(mw)}   {'Value'.ljust(vw)}   Read",
        f"  {'─' * (mw + vw + 40)}",
    ]
    for m, v, rd in rows:
        out.append(f"  {m.ljust(mw)}   {v.ljust(vw)}   {rd}")
    out += ["", f"Verdict: {verdict}", *analyze._footer()]
    return "\n".join(out)


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}
    if not args:
        print("usage: python scripts/health.py <TICKER> [--fixture] [--json]", file=sys.stderr)
        return 2
    ticker = args[0].upper()
    if "--fixture" in flags:
        f = load_fixture(ticker) or Fundamentals(ticker=ticker, available=False, error="no fixture for this ticker")
    else:
        f = get_fundamentals_or_fixture(ticker)
    report = build_health(f, as_json="--json" in flags)
    print(json.dumps(report, indent=2) if "--json" in flags else report)
    return 0 if f.available else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
