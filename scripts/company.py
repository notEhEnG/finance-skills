"""company — the sequential, educational company walkthrough.

Renders one narrative that steps through a business the way an analyst reads it,
top to bottom, each stage flowing into the next:

    Business Model → Competitive Advantage → Revenue Drivers → Margins →
    Financial Health → Growth → Valuation → Risks → Verdict

Every number comes from the one shared engine (`analyze.build_report`), so this
never diverges from `analyze`, `valuation`, or `framework`. Risks come from
`redflags.flags_for` — the same policy as the redflags verb.

    python scripts/company.py <TICKER> [--fixture] [--json]
"""

from __future__ import annotations

import sys
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

if __package__:
    from finance_skills import analyze, metrics, redflags, report_schema
    from finance_skills.cli import run_single_ticker
    from finance_skills.data import Fundamentals
    from finance_skills.format import currency_for, fmt_money, footer, leverage_cell, pct, source_line
else:
    import analyze
    import metrics
    import redflags
    import report_schema
    from cli import run_single_ticker
    from data import Fundamentals
    from format import currency_for, fmt_money, footer, leverage_cell, pct, source_line

ARROW = "        ▼"

_REGIME_STORY = {
    metrics.REGIME_NEOCLOUD: "AI neocloud/hyperscaler — extreme growth funded by heavy GPU capex; "
                             "judged on cash burn and backlog, not headline EBITDA.",
    metrics.REGIME_HYPERGROWTH: "Hypergrowth — scaling fast with lighter capital needs; deep-negative "
                               "FCF is expected while it lands customers.",
    metrics.REGIME_EARLY: "Early stage — small revenue base; unit economics still unproven.",
    metrics.REGIME_TRADITIONAL: "Steady/mature — growth and margins matter together; judged on FCF-based "
                               "Rule of 40 against a mature bar.",
}


def _story(r: dict) -> list[tuple[str, list[str]]]:
    """Build the ordered (heading, lines) sections from an engine report dict."""
    d = r["derived"]
    rule = r.get("rule40")
    regime = rule["regime"] if rule else None
    sections: list[tuple[str, list[str]]] = []

    # 1. Business Model
    biz = [f"Sector: {r.get('sector') or 'n/a'} / {r.get('industry') or 'n/a'}"]
    if regime:
        biz.append(_REGIME_STORY.get(regime, regime.replace("_", " ")))
    sections.append(("Business Model", biz))

    # 2. Competitive Advantage
    gm, em = d.get("gross_margin_pct"), d.get("ebitda_margin_pct")
    edge: list[str] = []
    if gm is not None:
        edge.append(f"Gross margin {pct(gm)} — " + (
            "high; suggests pricing power or a software-like cost structure." if gm >= 60
            else "moderate; some differentiation but cost-exposed." if gm >= 40
            else "thin; competes closer to cost/commodity, or is capital-heavy."))
    if em is not None:
        edge.append(f"EBITDA margin {pct(em)} — operating leverage "
                    + ("already showing." if em >= 20 else "still building." if em >= 0 else "negative; not yet profitable at the operating line."))
    if not edge:
        edge.append("Margin data unavailable — can't read pricing power from the financials alone.")
    sections.append(("Competitive Advantage", edge))

    # 3. Revenue Drivers
    rev = [f"Revenue: {fmt_money(d.get('revenue'), currency_for(r, 'revenue'))}"]
    if d["revenue_growth_pct"] is None:
        rev.append("Growth: n/a (no comparable prior period in the data).")
    else:
        rev.append(f"Growth (YoY): {pct(d['revenue_growth_pct'])}.")
    sections.append(("Revenue Drivers", rev))

    # 4. Margins — never coerce None to 0
    fcf_m = d.get("fcf_margin_pct")
    if fcf_m is None:
        fcf_note = "FCF margin unavailable — can't judge self-funding from the fetched data."
    elif fcf_m > 0:
        fcf_note = "Positive free cash flow — self-funding."
    else:
        fcf_note = "Negative free cash flow — growth is consuming cash (normal for the regime, watch runway)."
    sections.append(("Margins", [
        f"Gross: {pct(gm)}   EBITDA: {pct(em)}   FCF: {pct(fcf_m)}",
        fcf_note,
    ]))

    # 5. Financial Health
    health: list[str] = []
    if d["net_debt"] is None:
        health.append("Net debt: n/a — debt or cash missing from the data; leverage left uncomputed rather than guessed.")
    else:
        health.append(f"Net debt: {fmt_money(d['net_debt'], currency_for(r))}"
                      + (" (net cash)" if d["net_debt"] < 0 else ""))
    lev = (r.get("leverage") or {}).get("net_debt_to_ebitda")
    if lev is not None:
        value, read = leverage_cell(lev)
        health.append(f"Net debt / EBITDA: {value} — {read}.")
    sections.append(("Financial Health", health))

    # 6. Growth
    growth = [f"Growth rate: {pct(d['revenue_growth_pct'])}"]
    if regime:
        growth.append(_REGIME_STORY.get(regime, "").split(" — ")[0] + " regime.")
    sections.append(("Growth", growth))

    # 7. Valuation
    val: list[str] = []
    if "dcf" in r:
        val.append(f"DCF intrinsic ≈ {fmt_money(r['dcf']['per_share'], currency_for(r))}/share "
                   f"vs price {fmt_money(r.get('price'), currency_for(r, 'price'))}.")
        if "dcf_basis" in r:
            val.append(r["dcf_basis"])
    elif "dcf_note" in r:
        val.append(f"DCF: {r['dcf_note']}")
    if d.get("ev_ebitda") is not None:
        val.append(f"EV/EBITDA: {d['ev_ebitda']}x.")
    sections.append(("Valuation", val))

    # 8. Risks — same policy as redflags verb
    flags = redflags.flags_for(r)
    if flags:
        risks = [f"{fl['severity']} {fl['flag']}: {fl['detail']}" for fl in flags]
    else:
        risks = [
            "No dominant financial red flag in the data; still verify qualitative risks "
            "(competition, regulation, concentration)."
        ]
    sections.append(("Risks", risks))

    # 9. Final Verdict
    sections.append(("Final Verdict", _verdict(r, regime)))
    return sections


def _verdict(r: dict, regime: str | None) -> list[str]:
    rule = r.get("rule40")
    parts: list[str] = []
    if regime == metrics.REGIME_NEOCLOUD:
        parts.append("A capital-intensive neocloud: the story is backlog and funding runway, not this quarter's margin.")
    elif regime in (metrics.REGIME_HYPERGROWTH, metrics.REGIME_EARLY):
        parts.append("A high-growth, pre-profit business: reward is optionality, risk is the cash runway.")
    elif regime == metrics.REGIME_TRADITIONAL:
        parts.append("A steadier compounder: judge it on durable FCF and a defensible margin.")
    if rule:
        parts.append("Clears its Rule-of-40 bar." if rule.get("passes")
                     else "Falls short of its Rule-of-40 bar today.")
    if "dcf" in r:
        parts.append(f"DCF anchors fair value near {fmt_money(r['dcf']['per_share'], currency_for(r))}/share — a heuristic, not a target.")
    elif "dcf_note" in r:
        parts.append("Automatic DCF is disabled; use aligned multiples and Rule-of-40, or supply and disclose assumptions separately.")
    parts.append("Not a recommendation — verify against primary filings before acting.")
    return parts


def build_company(f: Fundamentals, as_json: bool = False):
    report = analyze.build_report(f)
    if not report.get("available", True):
        if as_json:
            return report_schema.enrich_report_for_agent(f, report, dict(report), intent="company")
        return analyze.format_report(report)
    if as_json:
        payload = {"ticker": report["ticker"], "sections": [
            {"heading": h, "lines": ls} for h, ls in _story(report)]}
        return report_schema.enrich_report_for_agent(f, report, payload, intent="company")
    return _render(report, _story(report))


def _render(r: dict, sections: list[tuple[str, list[str]]]) -> str:
    out = [
        f"═══ {r['name'] or r['ticker']} ({r['ticker']}) — company walkthrough ═══",
        source_line(r),
        f"Price: {fmt_money(r.get('price'), currency_for(r, 'price'))}   "
        f"Market cap: {fmt_money(r.get('market_cap'), currency_for(r, 'market_cap'))}",
        "",
    ]
    for i, (heading, lines) in enumerate(sections):
        out.append(f"■ {heading}")
        for ln in lines:
            out.append(f"    {ln}")
        if i < len(sections) - 1:
            out.append(ARROW)
    out += ["", *footer()]
    return "\n".join(out)


def main(argv: list[str]) -> int:
    return run_single_ticker(
        argv,
        usage="usage: python scripts/company.py <TICKER> [--fixture] [--json]",
        build=build_company,
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
