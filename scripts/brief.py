"""brief — the default answer-shaped stack over the shared engine.

Spine (fixed; no second math path):

  identity → regime + dual/preferred Rule of 40 + capital-intensity gap
           → valuation (EV/S, EV/EBITDA, DCF if allowed)
           → solvency (net debt, FCF margin, dilution)
           → top red flags (severity-sorted, max 3)
           → disabled analyses (precise missing inputs)
           → gaps[] + filing checklist
           → optional: --style=value|growth|quality|risk emphasis
           → optional: --explain (why metrics matter)
           → disclaimer

    python scripts/brief.py <TICKER> [--fixture|--json] [--style=value] [--explain]
    finance-skills brief NBIS --fixture --style=risk --explain
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

if __package__:
    from finance_skills import analyze, diagnostics, explain, redflags
    from finance_skills import style as style_mod
    from finance_skills.cli import flag_value, has_flag, run_single_ticker
    from finance_skills.data import Fundamentals
    from finance_skills.format import DISCLAIMER, fmt_money, footer, mult, pct, source_line
else:
    import analyze
    import diagnostics
    import explain
    import redflags
    import style as style_mod
    from cli import flag_value, has_flag, run_single_ticker
    from data import Fundamentals
    from format import DISCLAIMER, fmt_money, footer, mult, pct, source_line


def _gaps(r: dict) -> list[dict[str, str]]:
    """Fail-closed guided gaps from disabled diagnostics + neocloud extras."""
    gaps: list[dict[str, str]] = []
    for d in r.get("disabled") or []:
        miss = ", ".join(d.get("missing_inputs") or [])
        gaps.append({
            "field": d["analysis"],
            "why": d["reason"],
            "unlocks": d["unlocks"],
            "missing_inputs": miss,
        })
    rule = r.get("rule40") or {}
    if rule.get("regime") in ("ai_neocloud", "hypergrowth"):
        gaps.append({
            "field": "backlog_rpo",
            "why": "not in summary financials (yfinance)",
            "unlocks": "disclosed revenue backlog / RPO from earnings release or 10-Q",
            "missing_inputs": "backlog/RPO disclosure",
        })
    return gaps


def build_brief(f: Fundamentals, as_json: bool = False, flags: set[str] | None = None):
    """Build the standard brief spine over `analyze.build_report`."""
    flags = flags or set()
    report = analyze.build_report(f)
    if not report.get("available", True):
        if as_json:
            return report
        err = report.get("error") or "unavailable"
        return (
            f"Live data for {report.get('ticker', '?')} is unavailable ({err}).\n"
            "Try `--fixture` if a sample exists, or run where yfinance + network work.\n"
            f"{DISCLAIMER}"
        )

    style_name = style_mod.normalize_style(flag_value(flags, "style", ""))
    want_explain = has_flag(flags, "explain")

    disabled = diagnostics.disabled_analyses(f, report)
    report_for_gaps = {**report, "disabled": disabled}
    gaps = _gaps(report_for_gaps)
    checklist = diagnostics.filing_checklist({"disabled": disabled, "gaps": gaps})
    why = explain.why_lines_for_report(report) if want_explain else []

    d = report["derived"]
    rule = report.get("rule40")
    flags_list = redflags.flags_for(report, limit=3)

    payload: dict[str, Any] = {
        "ticker": report["ticker"],
        "name": report.get("name"),
        "source": report.get("source"),
        "as_of": report.get("as_of"),
        "sector": report.get("sector"),
        "industry": report.get("industry"),
        "price": report.get("price"),
        "market_cap": report.get("market_cap"),
        "regime": (rule or {}).get("regime"),
        "style": style_name,
        "rule40": {
            "preferred_score": (rule or {}).get("preferred_score"),
            "benchmark": (rule or {}).get("benchmark"),
            "passes": (rule or {}).get("passes"),
            "score_ebitda": (rule or {}).get("score_ebitda"),
            "score_fcf": (rule or {}).get("score_fcf"),
            "capital_intensity_gap": (rule or {}).get("capital_intensity_gap"),
            "capex_adjusted_score": (rule or {}).get("capex_adjusted_score"),
            "verdict": (rule or {}).get("verdict"),
            "note": report.get("rule40_note"),
        } if rule or report.get("rule40_note") else None,
        "valuation": {
            "ev_sales": d.get("ev_sales"),
            "ev_ebitda": d.get("ev_ebitda"),
            "enterprise_value": d.get("enterprise_value"),
            "dcf_per_share": (report.get("dcf") or {}).get("per_share"),
            "dcf_note": report.get("dcf_note"),
            "dcf_scenarios": report.get("dcf_scenarios"),
        },
        "solvency": {
            "net_debt": d.get("net_debt"),
            "fcf_margin_pct": d.get("fcf_margin_pct"),
            "share_dilution_pct": d.get("share_dilution_pct"),
            "net_debt_to_ebitda": (report.get("leverage") or {}).get("net_debt_to_ebitda"),
            "capex_intensity_pct": d.get("capex_intensity_pct"),
            "revenue_growth_pct": d.get("revenue_growth_pct"),
        },
        "redflags": flags_list,
        "disabled": disabled,
        "gaps": gaps,
        "filing_checklist": checklist,
        "why": why,
        "disclaimer": DISCLAIMER,
    }
    if as_json:
        return payload
    return _render(payload)


def _render(b: dict) -> str:
    out = [
        f"═══ {b.get('name') or b['ticker']} ({b['ticker']}) — brief ═══",
        source_line(b),
        f"Sector: {b.get('sector') or 'n/a'} / {b.get('industry') or 'n/a'}",
        f"Price: {fmt_money(b.get('price'))}   Market cap: {fmt_money(b.get('market_cap'))}",
        "",
    ]

    if b.get("style"):
        out += style_mod.style_focus(b["style"], b)
        out.append("")

    rule = b.get("rule40")
    regime = (b.get("regime") or "unknown").replace("_", " ")
    out.append(f"Regime: {regime}")
    if rule and rule.get("preferred_score") is not None:
        verdict = "PASS" if rule.get("passes") else "BELOW BAR"
        out.append(
            f"Rule of 40: preferred {rule['preferred_score']:.0f} vs bar {rule['benchmark']:.0f} → {verdict}"
        )
        out.append(
            f"  EBITDA-based {rule['score_ebitda']:.0f} · FCF-based {rule['score_fcf']:.0f} · "
            f"capital-intensity gap {rule['capital_intensity_gap']:.0f}"
        )
        if rule.get("capex_adjusted_score") is not None:
            out.append(f"  Capex-adjusted {rule['capex_adjusted_score']:.0f}")
        if rule.get("verdict"):
            out.append(f"  {rule['verdict']}")
    elif rule and rule.get("note"):
        out.append(f"Rule of 40: {rule['note']}")
    else:
        out.append("Rule of 40: n/a")
    out.append("")

    v = b.get("valuation") or {}
    out.append("Valuation")
    out.append(f"  EV / Sales:   {mult(v.get('ev_sales'))}")
    out.append(f"  EV / EBITDA:  {mult(v.get('ev_ebitda'))}")
    if v.get("dcf_per_share") is not None:
        out.append(f"  DCF / share:  {fmt_money(v.get('dcf_per_share'))}  (heuristic)")
        sc = (v.get("dcf_scenarios") or {}).get("growth") or {}
        if sc:
            bits = []
            for name in ("bear", "base", "bull"):
                row = sc.get(name)
                if row and row.get("per_share") is not None:
                    bits.append(f"{name} {fmt_money(row['per_share'])}")
            if bits:
                out.append(f"  DCF scenarios: {' · '.join(bits)}")
    else:
        out.append(f"  DCF / share:  n/a — {v.get('dcf_note') or 'not computed'}")
    out.append("")

    s = b.get("solvency") or {}
    out.append("Solvency / quality")
    out.append(f"  Revenue growth: {pct(s.get('revenue_growth_pct'))}")
    out.append(f"  FCF margin:     {pct(s.get('fcf_margin_pct'))}")
    out.append(f"  Capex intensity: {pct(s.get('capex_intensity_pct'))}")
    out.append(f"  Dilution:       {pct(s.get('share_dilution_pct'))}")
    out.append(f"  Net debt:       {fmt_money(s.get('net_debt'))}")
    lev = s.get("net_debt_to_ebitda")
    if lev is not None:
        if lev < 0:
            out.append(f"  Net debt/EBITDA: net cash ({abs(lev)}x)")
        else:
            out.append(f"  Net debt/EBITDA: {lev}x")
    out.append("")

    flags = b.get("redflags") or []
    out.append("Top red flags" if flags else "Top red flags: none tripped on fetched fundamentals")
    for fl in flags:
        out.append(f"  {fl.get('severity', '•')} {fl.get('flag')}: {fl.get('detail')}")
    out.append("")

    out += diagnostics.render_disabled(b.get("disabled") or [])
    out.append("")
    out += diagnostics.render_filing_checklist(b.get("filing_checklist") or [])

    if b.get("why"):
        out.append("")
        out += explain.render_why(b["why"])

    out += ["", *footer()]
    return "\n".join(out)


def main(argv: list[str]) -> int:
    return run_single_ticker(
        argv,
        usage=(
            "usage: python scripts/brief.py <TICKER> [--fixture] [--json] "
            "[--style=value|growth|quality|risk] [--explain]"
        ),
        build=build_brief,
        pass_flags=True,
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
