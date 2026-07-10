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

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

if __package__:
    from finance_skills import analyze, peers, rank
    from finance_skills.cli import flag_value, parse_argv
    from finance_skills.data import load_for_cli
    from finance_skills.format import fmt_money, footer, leverage_cell, mult, pct, source_line
else:
    import analyze
    import peers
    import rank
    from cli import flag_value, parse_argv
    from data import load_for_cli
    from format import fmt_money, footer, leverage_cell, mult, pct, source_line


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
    return f"{fmt_money(ps)}{tag}"


def _lev_cell(r: dict) -> str:
    v = (r.get("leverage") or {}).get("net_debt_to_ebitda")
    value, _ = leverage_cell(v)
    return value


# (row label, cell-from-report) — the curated comparison set. Order = story order.
ROWS: list[tuple[str, Callable[[dict], str]]] = [
    ("Price",              lambda r: fmt_money(r.get("price"))),
    ("Market cap",         lambda r: fmt_money(r.get("market_cap"))),
    ("Revenue growth",     lambda r: pct(r["derived"].get("revenue_growth_pct"))),
    ("Gross margin",       lambda r: pct(r["derived"].get("gross_margin_pct"))),
    ("EBITDA margin",      lambda r: pct(r["derived"].get("ebitda_margin_pct"))),
    ("FCF margin",         lambda r: pct(r["derived"].get("fcf_margin_pct"))),
    ("Rule of 40",         _rule40_cell),
    ("EV / Sales",         lambda r: mult(r["derived"].get("ev_sales"))),
    ("EV / EBITDA",        lambda r: mult(r["derived"].get("ev_ebitda"))),
    ("Net debt / EBITDA",  _lev_cell),
    ("DCF / share",        _dcf_cell),
]


def build_compare(reports: list[dict], as_json: bool = False, *, preset: str | None = None):
    ranking = rank.rank_reports(reports)
    if as_json:
        return {
            "tickers": [r["ticker"] for r in reports],
            "preset": preset,
            "rows": [{"metric": label, "values": {r["ticker"]: fn(r) for r in reports}}
                     for label, fn in ROWS],
            "ranking": ranking,
        }
    return _render(reports, ranking=ranking, preset=preset)


def _render(reports: list[dict], *, ranking: dict | None = None, preset: str | None = None) -> str:
    tickers = [r["ticker"] for r in reports]
    label_w = max(len(lbl) for lbl, _ in ROWS)
    cell_widths = [len(fn(r)) for _, fn in ROWS for r in reports]
    col_w = max(10, *(len(t) for t in tickers), *cell_widths)
    header = f"  {'Metric'.ljust(label_w)}   " + "   ".join(t.ljust(col_w) for t in tickers)
    title = "═══ Compare: " + " vs ".join(tickers) + " ═══"
    if preset:
        title = f"═══ Compare preset `{preset}`: " + " vs ".join(tickers) + " ═══"
    out = [
        title,
        "  " + " | ".join(f"{r['ticker']}: {source_line(r).replace('Source: ', '')}" for r in reports),
        "",
        header,
        f"  {'─' * (label_w + (col_w + 3) * len(tickers) + 1)}",
    ]
    for label, fn in ROWS:
        cells = "   ".join(fn(r).ljust(col_w) for r in reports)
        out.append(f"  {label.ljust(label_w)}   {cells}")
    if ranking:
        out += ["", *rank.render_ranking(ranking)]
    out += ["", *footer()]
    return "\n".join(out)


def main(argv: list[str]) -> int:
    args, flags = parse_argv(argv)
    if args and args[0].lower() == "list-presets":
        for name, tickers in peers.list_presets().items():
            print(f"{name:16s} {', '.join(tickers)}")
        return 0

    preset_name = flag_value(flags, "preset", "")
    preset_key = None
    if preset_name:
        resolved = peers.resolve_preset(preset_name)
        if resolved is None:
            print(
                f"unknown preset {preset_name!r}. Try: {', '.join(peers.list_presets())} "
                f"(or `compare list-presets`)",
                file=sys.stderr,
            )
            return 2
        preset_key, tickers = resolved[0], [t.upper() for t in resolved[1]]
        # Allow extra tickers after the preset flag's positionals.
        tickers = tickers + [a.upper() for a in args if a.upper() not in tickers]
    else:
        tickers = [a.upper() for a in args]

    if len(tickers) < 2:
        print(
            "usage: python scripts/compare.py <A> <B> [<C> ...] [--fixture] [--json]\n"
            "       python scripts/compare.py --preset=saas|ai-infra|semiconductor|megacap [--fixture]\n"
            "       python scripts/compare.py list-presets",
            file=sys.stderr,
        )
        return 2

    use_fixture = "--fixture" in flags
    reports = []
    unavailable = []
    for ticker in tickers:
        f = load_for_cli(ticker, use_fixture=use_fixture)
        rep = analyze.build_report(f)
        if rep.get("available", True):
            reports.append(rep)
        else:
            unavailable.append(ticker)

    if len(reports) < 2:
        print(f"Need at least two tickers with data; unavailable: {', '.join(unavailable) or '—'}", file=sys.stderr)
        return 1

    result = build_compare(reports, as_json="--json" in flags, preset=preset_key)
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
