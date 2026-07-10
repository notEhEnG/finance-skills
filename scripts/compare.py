"""compare — put two (or more) tickers side by side, one column each.

Runs the shared engine for every ticker and lays the metrics out as rows, so the
contrast is instant and the columns are guaranteed to line up (the agent used to
stitch two JSON dumps by hand, which risked mismatched rows). Purely a view over
`analyze.build_report`, so a number here always equals the same number in that
ticker's own `valuation` / `company` output.

    python scripts/compare.py <A> <B> [<C> ...] [--fixture|--json]
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:  # installed as the `finance_skills` package…
    from finance_skills import analyze
    from finance_skills.analyze import _fmt_money, _pct
    from finance_skills.data import Fundamentals, get_fundamentals_or_fixture, load_fixture
except ImportError:  # …or run directly via `python3 scripts/compare.py` (skill path)
    import analyze
    from analyze import _fmt_money, _pct
    from data import Fundamentals, get_fundamentals_or_fixture, load_fixture


def _rule40_cell(r: dict) -> str:
    x = r.get("rule40")
    if not x:
        return "n/a"
    return f"{x['preferred_score']:.0f} vs {x['benchmark']:.0f} {'✓' if x['passes'] else '✗'}"


def _dcf_cell(r: dict) -> str:
    if "dcf" not in r or r["dcf"].get("per_share") is None:
        return "n/a"
    ps, price = r["dcf"]["per_share"], r.get("price")
    tag = "" if price is None else (" (cheap)" if ps >= price else " (rich)")
    return f"{_fmt_money(ps)}{tag}"


def _mult(v) -> str:
    return "n/a" if v is None else f"{v}x"


def _lev_cell(r: dict) -> str:
    v = r.get("leverage", {}).get("net_debt_to_ebitda")
    if v is None:
        return "n/a"
    return f"net cash ({abs(v)}x)" if v < 0 else f"{v}x"


# (row label, cell-from-report) — the curated comparison set. Order = story order.
ROWS: list[tuple[str, Callable[[dict], str]]] = [
    ("Price",              lambda r: _fmt_money(r.get("price"))),
    ("Market cap",         lambda r: _fmt_money(r.get("market_cap"))),
    ("Revenue growth",     lambda r: _pct(r["derived"].get("revenue_growth_pct"))),
    ("Gross margin",       lambda r: _pct(r["derived"].get("gross_margin_pct"))),
    ("EBITDA margin",      lambda r: _pct(r["derived"].get("ebitda_margin_pct"))),
    ("FCF margin",         lambda r: _pct(r["derived"].get("fcf_margin_pct"))),
    ("Rule of 40",         _rule40_cell),
    ("EV / Sales",         lambda r: _mult(r["derived"].get("ev_sales"))),
    ("EV / EBITDA",        lambda r: _mult(r["derived"].get("ev_ebitda"))),
    ("Net debt / EBITDA",  _lev_cell),
    ("DCF / share",        _dcf_cell),
]


def build_compare(reports: list[dict], as_json: bool = False):
    if as_json:
        return {
            "tickers": [r["ticker"] for r in reports],
            "rows": [{"metric": label, "values": {r["ticker"]: fn(r) for r in reports}}
                     for label, fn in ROWS],
        }
    return _render(reports)


def _render(reports: list[dict]) -> str:
    tickers = [r["ticker"] for r in reports]
    label_w = max(len(lbl) for lbl, _ in ROWS)
    # Size each column to the widest of its ticker header and every cell it holds,
    # so a wide value like "net cash (4.88x)" can't shove the row out of alignment.
    cell_widths = [len(fn(r)) for _, fn in ROWS for r in reports]
    col_w = max(10, *(len(t) for t in tickers), *cell_widths)
    header = f"  {'Metric'.ljust(label_w)}   " + "   ".join(t.ljust(col_w) for t in tickers)
    out = [
        "═══ Compare: " + " vs ".join(tickers) + " ═══",
        "  " + " | ".join(f"{r['ticker']}: {analyze._source_line(r).replace('Source: ', '')}" for r in reports),
        "",
        header,
        f"  {'─' * (label_w + (col_w + 3) * len(tickers) + 1)}",
    ]
    for label, fn in ROWS:
        cells = "   ".join(fn(r).ljust(col_w) for r in reports)
        out.append(f"  {label.ljust(label_w)}   {cells}")
    out += ["", *analyze._footer()]
    return "\n".join(out)


def _load(ticker: str, use_fixture: bool) -> Fundamentals:
    if use_fixture:
        return load_fixture(ticker) or Fundamentals(ticker=ticker, available=False, error="no fixture for this ticker")
    return get_fundamentals_or_fixture(ticker)


def main(argv: list[str]) -> int:
    args = [a.upper() for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}
    if len(args) < 2:
        print("usage: python scripts/compare.py <A> <B> [<C> ...] [--fixture] [--json]", file=sys.stderr)
        return 2

    reports = []
    unavailable = []
    for ticker in args:
        f = _load(ticker, "--fixture" in flags)
        rep = analyze.build_report(f, as_json=True)
        if isinstance(rep, dict) and rep.get("available", True):
            reports.append(rep)
        else:
            unavailable.append(ticker)

    if len(reports) < 2:
        print(f"Need at least two tickers with data; unavailable: {', '.join(unavailable) or '—'}", file=sys.stderr)
        return 1

    result = build_compare(reports, as_json="--json" in flags)
    if "--json" in flags:
        if unavailable:
            result["unavailable"] = unavailable
        print(json.dumps(result, indent=2))
    else:
        print(result)
        if unavailable:
            print(f"\n(No data for: {', '.join(unavailable)} — omitted.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
