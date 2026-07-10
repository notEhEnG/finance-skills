"""valuation — the "is it cheap?" view, rendered as a table.

Leads with the valuation slice of the shared engine (DCF, EV/Sales, EV/EBITDA,
Rule of 40 vs benchmark) laid out as a scannable Metric | Value | Read table, so
the takeaway is obvious at a glance. Reuses `analyze.build_report`, so the numbers
never diverge from `analyze`, `company`, or `framework`.

    python scripts/valuation.py <TICKER> [--fixture|--json]
"""

from __future__ import annotations

import sys
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

if __package__:
    from finance_skills import analyze, explain
    from finance_skills.cli import has_flag, run_single_ticker
    from finance_skills.data import Fundamentals
    from finance_skills.format import fmt_money, leverage_cell, mult, pct, render_metric_table, source_line
else:
    import analyze
    import explain
    from cli import has_flag, run_single_ticker
    from data import Fundamentals
    from format import fmt_money, leverage_cell, mult, pct, render_metric_table, source_line


def _rows(r: dict) -> list[tuple[str, str, str]]:
    """Build (metric, value, read) rows for the valuation table."""
    d = r["derived"]
    rows: list[tuple[str, str, str]] = [
        ("Price", fmt_money(r.get("price")), "—"),
        ("Market cap", fmt_money(r.get("market_cap")), "—"),
    ]

    ev = d.get("enterprise_value")
    rows.append(("Enterprise value", fmt_money(ev) if ev is not None else "n/a",
                 "market cap + net debt" if ev is not None else "net debt unknown"))

    evs = d.get("ev_sales")
    rows.append(("EV / Sales", mult(evs), _ev_sales_read(evs)))

    eve, em = d.get("ev_ebitda"), d.get("ebitda_margin_pct")
    if em is not None and em > 100 and eve is not None:
        eve_read = "⚠ distorted — EBITDA margin >100% (non-operating items); trust EV/Sales more"
    elif eve is None:
        eve_read = "net debt unknown" if ev is None else "needs positive EBITDA"
    else:
        eve_read = _ev_ebitda_read(eve)
    rows.append(("EV / EBITDA", mult(eve), eve_read))

    if "dcf" in r:
        ps = r["dcf"].get("per_share")
        rows.append(("DCF / share", fmt_money(ps), _dcf_read(ps, r.get("price"))))
    else:
        note = r.get("dcf_note", "not computed")
        if "not positive" in note:
            short = "FCF negative — DCF skipped"
        elif "net debt unknown" in note.lower():
            short = "net debt unknown — DCF skipped"
        else:
            short = note
        rows.append(("DCF / share", "n/a", short))

    rule = r.get("rule40")
    if rule:
        verdict = "PASS" if rule["passes"] else "BELOW BAR"
        rows.append(("Rule of 40", f"{rule['preferred_score']:.0f} vs {rule['benchmark']:.0f}",
                     f"{verdict} ({rule['regime'].replace('_', ' ')})"))
    elif "rule40_note" in r:
        rows.append(("Rule of 40", "n/a", "insufficient margin data"))

    rows.append(("Revenue growth", pct(d.get("revenue_growth_pct")), _growth_read(d.get("revenue_growth_pct"))))
    rows.append(("FCF margin", pct(d.get("fcf_margin_pct")), _fcf_read(d.get("fcf_margin_pct"))))
    if "leverage" in r:
        value, read = leverage_cell(r["leverage"]["net_debt_to_ebitda"])
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
        return f"above price {fmt_money(price)} → cheap on this DCF (heuristic)"
    return f"below price {fmt_money(price)} → rich on this DCF (heuristic)"


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
        return f"{stance} vs a heuristic DCF near {fmt_money(ps)}/share; corroborate with the multiples above."
    evs = d.get("ev_sales")
    if evs is None:
        return ("No positive-FCF DCF and EV/Sales isn't computable (net debt or revenue "
                "unknown), so there isn't enough data to call it cheap or expensive.")
    note = r.get("dcf_note") or ""
    if "net debt unknown" in note.lower():
        return (f"No equity DCF (net debt unknown) — expensive on EV/Sales {evs}x only if EV "
                "itself is known; verify debt/cash before anchoring on multiples.")
    return (f"No DCF (FCF not positive), so it can't be anchored to intrinsic value — "
            f"expensive on EV/Sales {evs}x; a growth/backlog bet, not supported by current cash flows.")


def _scenario_lines(report: dict) -> list[str]:
    sc = report.get("dcf_scenarios")
    if not sc:
        note = report.get("dcf_note")
        return [f"Scenarios: n/a — {note}"] if note else []
    lines = ["Scenarios (heuristic DCF — not a target price)"]
    lines.append("  Growth (bear / base / bull):")
    for name, row in (sc.get("growth") or {}).items():
        vs = row.get("vs_price_pct")
        vs_s = f" ({vs:+.1f}% vs price)" if vs is not None else ""
        lines.append(
            f"    {name:4s}  {fmt_money(row['per_share'])}/sh  "
            f"g={row['growth_rate']}%  r={row['discount_rate']}%{vs_s}"
        )
    lines.append("  Discount-rate sensitivity (base growth):")
    for label, row in (sc.get("discount_rate") or {}).items():
        lines.append(f"    {label:8s}  {fmt_money(row['per_share'])}/sh")
    lines.append("  FCF conversion (×0.8 / ×1.0 / ×1.2 on starting FCF):")
    for label, row in (sc.get("fcf_conversion") or {}).items():
        lines.append(f"    {label:8s}  {fmt_money(row['per_share'])}/sh")
    return lines


def build_valuation(f: Fundamentals, as_json: bool = False, flags: set[str] | None = None):
    flags = flags or set()
    report = analyze.build_report(f)
    if not report.get("available", True):
        return report if as_json else analyze.format_report(report)
    rows = _rows(report)
    why = explain.why_lines_for_report(report) if has_flag(flags, "explain") else []
    if as_json:
        return {
            "ticker": report["ticker"],
            "verdict": _verdict(report),
            "rows": [{"metric": m, "value": v, "read": rd} for m, v, rd in rows],
            "dcf_scenarios": report.get("dcf_scenarios"),
            "dcf_note": report.get("dcf_note"),
            "why": why,
        }
    title = [
        f"═══ {report['name'] or report['ticker']} ({report['ticker']}) — valuation ═══",
        source_line(report),
    ]
    extra: list[str] = []
    sc_lines = _scenario_lines(report)
    if sc_lines:
        extra += sc_lines
    if why:
        if extra:
            extra.append("")
        extra += explain.render_why(why)
    return render_metric_table(title, rows, verdict=_verdict(report), extra_lines=extra or None)


def main(argv: list[str]) -> int:
    return run_single_ticker(
        argv,
        usage="usage: python scripts/valuation.py <TICKER> [--fixture] [--json] [--explain]",
        build=build_valuation,
        pass_flags=True,
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
