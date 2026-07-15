"""compare — put two (or more) tickers side by side, one column each.

Runs the shared engine for every ticker and lays the metrics out as a **table**
with emoji/bold leaders so contrasts are obvious (for agents and humans). Purely
a view over `analyze.build_report`, so a number here always equals the same
number in that ticker's own `valuation` / `company` output.

    python scripts/compare.py <A> <B> [<C> ...] [--fixture|--json]
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

if __package__:
    from finance_skills import analyze, peers, rank, report_schema
    from finance_skills.cli import flag_value, parse_argv
    from finance_skills.data import load_for_cli
    from finance_skills.format import currency_for, fmt_money, footer, leverage_cell, mult, pct, source_line
else:
    import analyze
    import peers
    import rank
    import report_schema
    from cli import flag_value, parse_argv
    from data import load_for_cli
    from format import currency_for, fmt_money, footer, leverage_cell, mult, pct, source_line


def _rule40_cell(r: dict) -> str:
    x = r.get("rule40")
    if not x:
        return "n/a"
    return f"{x['preferred_score']:.0f} vs project heuristic {x['benchmark']:.0f} {'✓' if x['passes'] else '✗'}"


def _dcf_cell(r: dict) -> str:
    if "dcf" not in r or r["dcf"].get("per_share") is None:
        return "n/a"
    ps, price = r["dcf"]["per_share"], r.get("price")
    tag = "" if price is None else (" (cheap)" if ps >= price else " (rich)")
    return f"{fmt_money(ps, currency_for(r))}{tag}"


def _lev_cell(r: dict) -> str:
    v = (r.get("leverage") or {}).get("net_debt_to_ebitda")
    value, _ = leverage_cell(v)
    return value


def _raw_rule40(r: dict) -> float | None:
    x = r.get("rule40")
    if not x:
        return None
    v = x.get("preferred_score")
    return float(v) if v is not None else None


def _raw_dcf(r: dict) -> float | None:
    if "dcf" not in r or r["dcf"].get("per_share") is None:
        return None
    return float(r["dcf"]["per_share"])


def _raw_lev(r: dict) -> float | None:
    v = (r.get("leverage") or {}).get("net_debt_to_ebitda")
    return float(v) if v is not None else None


# (label, display_fn, raw_fn, higher_is_better)
# higher_is_better: True = bold/🏆 max; False = bold/🏆 min; None = no leader
RowSpec = tuple[str, Callable[[dict], str], Callable[[dict], float | None], bool | None]

ROWS: list[RowSpec] = [
    ("Price",              lambda r: fmt_money(r.get("price"), currency_for(r, "price")),
     lambda r: r.get("price"), None),
    ("Market cap",         lambda r: fmt_money(r.get("market_cap"), currency_for(r, "market_cap")),
     lambda r: r.get("market_cap"), None),
    ("Revenue growth",     lambda r: pct(r["derived"].get("revenue_growth_pct")),
     lambda r: r["derived"].get("revenue_growth_pct"), True),
    ("Gross margin",       lambda r: pct(r["derived"].get("gross_margin_pct")),
     lambda r: r["derived"].get("gross_margin_pct"), True),
    ("EBITDA margin",      lambda r: pct(r["derived"].get("ebitda_margin_pct")),
     lambda r: r["derived"].get("ebitda_margin_pct"), True),
    ("FCF margin",         lambda r: pct(r["derived"].get("fcf_margin_pct")),
     lambda r: r["derived"].get("fcf_margin_pct"), True),
    ("Rule of 40",         _rule40_cell, _raw_rule40, True),
    ("EV / Sales",         lambda r: mult(r["derived"].get("ev_sales")),
     lambda r: r["derived"].get("ev_sales"), False),
    ("EV / EBITDA",        lambda r: mult(r["derived"].get("ev_ebitda")),
     lambda r: r["derived"].get("ev_ebitda"), False),
    ("Net debt / EBITDA",  _lev_cell, _raw_lev, False),
    ("DCF / share",        _dcf_cell, _raw_dcf, True),  # higher intrinsic vs peers (heuristic)
]

# Emoji legend for leaders / warnings
_LEADER = "🏆"
_WARN = "⚠️"
# Metrics where the *worst* value is also worth flagging
_WARN_ON_WORST = frozenset({"FCF margin", "Net debt / EBITDA"})


def _pick_leader(
    raw: dict[str, float | None],
    *,
    higher_is_better: bool | None,
) -> str | None:
    if higher_is_better is None:
        return None
    scored = [(t, v) for t, v in raw.items() if v is not None]
    if len(scored) < 2:
        return None
    # All equal → no leader
    vals = [v for _, v in scored]
    if max(vals) == min(vals):
        return None
    scored.sort(key=lambda x: x[1], reverse=higher_is_better)
    return scored[0][0]


def _pick_worst(
    raw: dict[str, float | None],
    *,
    higher_is_better: bool | None,
) -> str | None:
    """Opposite of leader (for ⚠️ on concerning metrics)."""
    if higher_is_better is None:
        return None
    scored = [(t, v) for t, v in raw.items() if v is not None]
    if len(scored) < 2:
        return None
    vals = [v for _, v in scored]
    if max(vals) == min(vals):
        return None
    scored.sort(key=lambda x: x[1], reverse=not higher_is_better)
    return scored[0][0]


def _decorate_cell(
    display: str,
    ticker: str,
    *,
    leader: str | None,
    worst: str | None,
    warn_worst: bool,
) -> str:
    """Bold + emoji for scannable comparison cells."""
    if ticker == leader:
        return f"{_LEADER} **{display}**"
    if warn_worst and ticker == worst and worst != leader:
        return f"{_WARN} {display}"
    return display


def _build_row_payloads(reports: list[dict]) -> list[dict[str, Any]]:
    tickers = [r["ticker"] for r in reports]
    out: list[dict[str, Any]] = []
    for label, disp_fn, raw_fn, hib in ROWS:
        values = {r["ticker"]: disp_fn(r) for r in reports}
        raw: dict[str, float | None] = {}
        for r in reports:
            try:
                v = raw_fn(r)
                raw[r["ticker"]] = float(v) if v is not None else None
            except (TypeError, ValueError, KeyError):
                raw[r["ticker"]] = None
        leader = _pick_leader(raw, higher_is_better=hib)
        worst = _pick_worst(raw, higher_is_better=hib)
        warn = label in _WARN_ON_WORST
        highlighted = {
            t: _decorate_cell(
                values[t], t, leader=leader, worst=worst, warn_worst=warn,
            )
            for t in tickers
        }
        out.append({
            "metric": label,
            "values": values,
            "raw": raw,
            "higher_is_better": hib,
            "leader": leader,
            "worst": worst if warn else None,
            "highlighted": highlighted,
        })
    return out


def render_markdown_table(
    tickers: list[str],
    row_payloads: list[dict[str, Any]],
    *,
    use_highlight: bool = True,
) -> str:
    """GitHub-flavored markdown table (agents + rich terminals)."""
    header = "| **Metric** | " + " | ".join(f"**{t}**" for t in tickers) + " |"
    sep = "| :--- | " + " | ".join([":---:"] * len(tickers)) + " |"
    lines = [header, sep]
    for row in row_payloads:
        cells = []
        for t in tickers:
            if use_highlight:
                cells.append(row["highlighted"].get(t) or row["values"].get(t, "n/a"))
            else:
                cells.append(row["values"].get(t, "n/a"))
        lines.append(f"| **{row['metric']}** | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def render_ascii_table(
    tickers: list[str],
    row_payloads: list[dict[str, Any]],
    *,
    use_highlight: bool = True,
) -> str:
    """Monospace table for plain CLI (emoji/bold markers still embedded)."""
    # Strip markdown bold for width calc but keep emoji
    def plain(s: str) -> str:
        return s.replace("**", "")

    cells_matrix: list[list[str]] = []
    for row in row_payloads:
        cells_matrix.append([
            plain(row["highlighted"][t] if use_highlight else row["values"][t])
            for t in tickers
        ])
    label_w = max(len("Metric"), max(len(r["metric"]) for r in row_payloads))
    col_ws = [
        max(len(t), max((len(cells_matrix[i][j]) for i in range(len(row_payloads))), default=0))
        for j, t in enumerate(tickers)
    ]
    col_ws = [max(10, w) for w in col_ws]

    header = f"  {'Metric'.ljust(label_w)}   " + "   ".join(
        t.ljust(col_ws[i]) for i, t in enumerate(tickers)
    )
    rule = f"  {'─' * (label_w + sum(col_ws) + 3 * len(tickers) + 1)}"
    lines = [header, rule]
    for row, cells in zip(row_payloads, cells_matrix, strict=True):
        body = "   ".join(cells[i].ljust(col_ws[i]) for i in range(len(tickers)))
        lines.append(f"  {row['metric'].ljust(label_w)}   {body}")
    return "\n".join(lines)


def _verdict_from_ranking(ranking: dict[str, Any], tickers: list[str]) -> str:
    """One scannable line of leaders (not a buy/sell call)."""
    bits: list[str] = []
    mapping = [
        ("best_growth", "📈 growth"),
        ("cheapest_ev_sales", "💰 cheapest EV/S"),
        ("strongest_rule40", "📏 Rule of 40"),
        ("highest_burn", "🔥 worst FCF burn"),
        ("worst_dilution", "⚠️ dilution"),
    ]
    for key, label in mapping:
        hit = ranking.get(key)
        if hit and hit.get("ticker"):
            bits.append(f"{label}: **{hit['ticker']}**")
    if not bits:
        return f"Side-by-side for {' vs '.join(tickers)} — see table (no ranking leaders)."
    return "Leaders at a glance — " + " · ".join(bits) + "."


def build_compare(reports: list[dict], as_json: bool = False, *, preset: str | None = None):
    ranking = rank.rank_reports(reports)
    tickers = [r["ticker"] for r in reports]
    row_payloads = _build_row_payloads(reports)
    md = render_markdown_table(tickers, row_payloads, use_highlight=True)
    ascii_tbl = render_ascii_table(tickers, row_payloads, use_highlight=True)
    ranking_lines = rank.render_ranking(ranking)
    verdict = _verdict_from_ranking(ranking, tickers)

    if as_json:
        payload = {
            "tickers": tickers,
            "preset": preset,
            "verdict": verdict,
            "rows": [
                {
                    "metric": r["metric"],
                    "values": r["values"],
                    "raw": r["raw"],
                    "higher_is_better": r["higher_is_better"],
                    "leader": r["leader"],
                    "worst": r["worst"],
                    "highlighted": r["highlighted"],
                }
                for r in row_payloads
            ],
            "markdown_table": md,
            "text_table": ascii_tbl,
            "ranking": ranking,
            "ranking_lines": ranking_lines,
            "legend": {
                "leader": f"{_LEADER} **bold** = best on that row (higher or lower as marked)",
                "warn": f"{_WARN} = worst on concerning rows (FCF burn, leverage)",
            },
            "sources": [
                {
                    "ticker": r.get("ticker"),
                    "provider": r.get("source"),
                    "data_state": r.get("data_state"),
                    "as_of": r.get("as_of"),
                    "retrieved_at": r.get("retrieved_at"),
                    "currency": r.get("currency"),
                    "source_url": r.get("source_url"),
                }
                for r in reports
            ],
        }
        out = report_schema.attach_engine_report(
            payload,
            reports[0],
            route={"intent": "compare", "tickers": tickers},
        )
        out["engine_reports"] = [
            report_schema.envelope_from_build_report(
                report, route={"intent": "compare", "tickers": tickers}
            )
            for report in reports
        ]
        return out
    return _render(
        reports,
        ranking=ranking,
        ranking_lines=ranking_lines,
        preset=preset,
        markdown_table=md,
        ascii_table=ascii_tbl,
        verdict=verdict,
    )


def _render(
    reports: list[dict],
    *,
    ranking: dict | None = None,
    ranking_lines: list[str] | None = None,
    preset: str | None = None,
    markdown_table: str,
    ascii_table: str,
    verdict: str,
) -> str:
    tickers = [r["ticker"] for r in reports]
    title = "═══ Compare: " + " vs ".join(tickers) + " ═══"
    if preset:
        title = f"═══ Compare preset `{preset}`: " + " vs ".join(tickers) + " ═══"
    out = [
        title,
        "  " + " | ".join(
            f"{r['ticker']}: {source_line(r).replace('Source: ', '')}" for r in reports
        ),
        "",
        verdict,
        "",
        "Legend: 🏆 **bold** = leader on that metric · ⚠️ = worst on burn/leverage rows",
        "",
        # Prefer markdown table (renders in agents / GH / many UIs)
        markdown_table,
        "",
        # Monospace fallback for plain terminals
        "ASCII view:",
        ascii_table,
    ]
    if ranking_lines:
        out += ["", *ranking_lines]
    elif ranking:
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
        print(
            f"Need at least two tickers with data; unavailable: {', '.join(unavailable) or '—'}",
            file=sys.stderr,
        )
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
