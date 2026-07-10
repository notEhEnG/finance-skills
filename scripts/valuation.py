"""valuation — the "is it cheap?" view, rendered as a table.

Leads with the valuation slice of the shared engine (DCF, EV/Sales, EV/EBITDA,
Rule of 40 vs benchmark) laid out as a scannable Metric | Value | Read table, so
the takeaway is obvious at a glance. Reuses `analyze.build_report`, so the numbers
never diverge from `analyze`, `company`, or `framework`.

    python scripts/valuation.py <TICKER> [--fixture|--json]
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
except ImportError:  # …or run directly via `python3 scripts/valuation.py` (skill path)
    import analyze
    from analyze import _fmt_money, _pct
    from data import Fundamentals, get_fundamentals_or_fixture, load_fixture


def _mult(v) -> str:
    return "n/a" if v is None else f"{v}x"


def _rows(r: dict) -> list[tuple[str, str, str]]:
    """Build (metric, value, read) rows for the valuation table."""
    d = r["derived"]
    rows: list[tuple[str, str, str]] = [
        ("Price", _fmt_money(r.get("price")), "—"),
        ("Market cap", _fmt_money(r.get("market_cap")), "—"),
    ]

    ev = d.get("enterprise_value")
    rows.append(("Enterprise value", _fmt_money(ev) if ev is not None else "n/a",
                 "market cap + net debt" if ev is not None else "net debt unknown"))

    # EV / Sales — the cleaner multiple when FCF is negative and EBITDA distorted.
    evs = d.get("ev_sales")
    rows.append(("EV / Sales", _mult(evs), _ev_sales_read(evs)))

    # EV / EBITDA — flag when EBITDA margin > 100% (non-operating items inflate it).
    eve, em = d.get("ev_ebitda"), d.get("ebitda_margin_pct")
    if em is not None and em > 100 and eve is not None:
        eve_read = "⚠ distorted — EBITDA margin >100% (non-operating items); trust EV/Sales more"
    elif eve is None:
        # Name the actual missing input rather than blaming EBITDA generically.
        eve_read = "net debt unknown" if ev is None else "needs positive EBITDA"
    else:
        eve_read = _ev_ebitda_read(eve)
    rows.append(("EV / EBITDA", _mult(eve), eve_read))

    # DCF — intrinsic value per share, or why it's skipped.
    if "dcf" in r:
        ps = r["dcf"].get("per_share")
        rows.append(("DCF / share", _fmt_money(ps), _dcf_read(ps, r.get("price"))))
    else:
        note = r.get("dcf_note", "not computed")
        short = "FCF negative — DCF skipped" if "not positive" in note else note
        rows.append(("DCF / share", "n/a", short))

    # Rule of 40 — the segment-aware pass/fail vs its benchmark.
    rule = r.get("rule40")
    if rule:
        verdict = "PASS" if rule["passes"] else "BELOW BAR"
        rows.append(("Rule of 40", f"{rule['preferred_score']:.0f} vs {rule['benchmark']:.0f}",
                     f"{verdict} ({rule['regime'].replace('_', ' ')})"))
    elif "rule40_note" in r:
        rows.append(("Rule of 40", "n/a", "insufficient margin data"))

    rows.append(("Revenue growth", _pct(d.get("revenue_growth_pct")), _growth_read(d.get("revenue_growth_pct"))))
    rows.append(("FCF margin", _pct(d.get("fcf_margin_pct")), _fcf_read(d.get("fcf_margin_pct"))))
    if "leverage" in r:
        x = r["leverage"]["net_debt_to_ebitda"]
        # Negative net debt is net cash, not "low leverage" — say so and drop the sign.
        if x < 0:
            value, read = f"net cash ({abs(x)}x)", "net cash — no leverage risk"
        else:
            value, read = f"{x}x", "low leverage" if x < 3 else "elevated — watch refinancing"
        rows.append(("Net debt / EBITDA", value, read))
    return rows


def _ev_sales_read(v) -> str:
    if v is None:
        return "not computable"
    if v < 0:
        return "negative EV — net cash exceeds market cap"
    if v >= 20:
        return "extreme — priced on growth, not sales"
    if v >= 10:
        return "rich"
    return "moderate for the multiple"


def _ev_ebitda_read(v) -> str:
    if v is None:
        return "needs positive EBITDA and known net debt"
    if v < 0:
        return "negative EV — net cash exceeds market cap"
    if v >= 30:
        return "expensive"
    if v >= 15:
        return "full"
    return "moderate"


def _dcf_read(ps, price) -> str:
    if ps is None or price is None:
        return "heuristic estimate"
    if ps >= price:
        return f"above price {_fmt_money(price)} → cheap on this DCF (heuristic)"
    return f"below price {_fmt_money(price)} → rich on this DCF (heuristic)"


def _growth_read(v) -> str:
    if v is None:
        return "n/a"
    if v >= 100:
        return "hypergrowth"
    if v >= 25:
        return "fast"
    if v >= 0:
        return "steady"
    return "shrinking"


def _fcf_read(v) -> str:
    if v is None:
        return "n/a"
    return "self-funding" if v > 0 else "cash burn — depends on funding"


def _verdict(r: dict) -> str:
    d = r["derived"]
    if "dcf" in r and r["dcf"].get("per_share") is not None and r.get("price") is not None:
        ps, price = r["dcf"]["per_share"], r["price"]
        stance = "screens cheap" if ps >= price else "screens rich"
        return f"{stance} vs a heuristic DCF near {_fmt_money(ps)}/share; corroborate with the multiples above."
    evs = d.get("ev_sales")
    if evs is None:
        # Neither an intrinsic anchor (no positive-FCF DCF) nor an EV multiple is
        # available — don't assert a valuation on no data.
        return ("No positive-FCF DCF and EV/Sales isn't computable (net debt or revenue "
                "unknown), so there isn't enough data to call it cheap or expensive.")
    return (f"No DCF (FCF not positive), so it can't be anchored to intrinsic value — "
            f"expensive on EV/Sales {evs}x; a growth/backlog bet, not supported by current cash flows.")


def build_valuation(f: Fundamentals, as_json: bool = False):
    report = analyze.build_report(f, as_json=True)
    if isinstance(report, dict) and not report.get("available", True):
        return report if as_json else analyze.build_report(f, as_json=False)
    rows = _rows(report)
    if as_json:
        return {"ticker": report["ticker"], "verdict": _verdict(report),
                "rows": [{"metric": m, "value": v, "read": rd} for m, v, rd in rows]}
    return _render(report, rows)


def _render(r: dict, rows: list[tuple[str, str, str]]) -> str:
    mw = max(len(m) for m, _, _ in rows)
    vw = max(len(v) for _, v, _ in rows)
    out = [
        f"═══ {r['name'] or r['ticker']} ({r['ticker']}) — valuation ═══",
        analyze._source_line(r),
        "",
        f"  {'Metric'.ljust(mw)}   {'Value'.ljust(vw)}   Read",
        f"  {'─' * (mw + vw + 40)}",
    ]
    for m, v, rd in rows:
        out.append(f"  {m.ljust(mw)}   {v.ljust(vw)}   {rd}")
    out += ["", f"Verdict: {_verdict(r)}", *analyze._footer()]
    return "\n".join(out)


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}
    if not args:
        print("usage: python scripts/valuation.py <TICKER> [--fixture] [--json]", file=sys.stderr)
        return 2
    ticker = args[0].upper()
    if "--fixture" in flags:
        f = load_fixture(ticker) or Fundamentals(ticker=ticker, available=False, error="no fixture for this ticker")
    else:
        f = get_fundamentals_or_fixture(ticker)
    report = build_valuation(f, as_json="--json" in flags)
    print(json.dumps(report, indent=2) if "--json" in flags else report)
    return 0 if f.available else 1  # surface unavailable/missing-fixture to callers


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
