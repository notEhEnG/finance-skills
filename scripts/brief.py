"""brief — the default answer-shaped stack over the shared engine.

The no-verb / bare-ticker path and the explicit `brief` verb both land here.
Spine (fixed; no second math path):

  identity → regime + dual/preferred Rule of 40 + capital-intensity gap
           → valuation (EV/S, EV/EBITDA, DCF if allowed)
           → solvency (net debt, FCF margin, dilution)
           → top red flags (severity-sorted, max 3)
           → gaps[] (missing fields + what unlocks them)
           → disclaimer

    python scripts/brief.py <TICKER> [--fixture|--json]
    finance-skills brief NBIS --fixture
    finance-skills NBIS --fixture          # same default

Prefer `--json` when an agent composes an answer-first reply.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:  # installed as the `finance_skills` package…
    from finance_skills import analyze, redflags
    from finance_skills.analyze import _fmt_money, _pct
    from finance_skills.data import Fundamentals, load_for_cli
except ImportError:  # …or run directly via `python3 scripts/brief.py` (skill path)
    import analyze
    import redflags
    from analyze import _fmt_money, _pct
    from data import Fundamentals, load_for_cli


def _mult(v) -> str:
    return "n/a" if v is None else f"{v}x"


def _gaps(r: dict) -> list[dict[str, str]]:
    """Fail-closed guided gaps: never invent; name what disclosure unlocks."""
    d = r.get("derived") or {}
    gaps: list[dict[str, str]] = []

    def add(field: str, why: str, unlocks: str) -> None:
        gaps.append({"field": field, "why": why, "unlocks": unlocks})

    if d.get("net_debt") is None:
        add("net_debt", "debt or cash missing from the fetch",
            "balance sheet total debt + cash (10-K/10-Q)")
    if d.get("revenue_growth_pct") is None:
        add("revenue_growth", "need current and prior revenue",
            "income statement two periods, or disclosed YoY growth")
    if d.get("fcf_margin_pct") is None:
        add("fcf_margin", "free cash flow or revenue missing",
            "cash flow statement FCF + revenue")
    if d.get("ebitda_margin_pct") is None:
        add("ebitda_margin", "EBITDA or revenue missing",
            "income statement EBITDA (or operating income proxy) + revenue")
    if "rule40" not in r:
        add("rule40", r.get("rule40_note") or "insufficient inputs for dual-margin Rule of 40",
            "revenue growth + EBITDA margin + FCF margin")
    if "dcf" not in r:
        note = r.get("dcf_note") or "DCF not computed"
        if "not positive" in note.lower() or "negative" in note.lower():
            add("dcf", "FCF not positive — intrinsic DCF skipped by design",
                "sustainable positive FCF (or a disclosed FCF outlook); until then use multiples")
        else:
            add("dcf", note, "positive FCF, shares outstanding, and net debt")

    rule = r.get("rule40") or {}
    if rule.get("regime") in ("ai_neocloud", "hypergrowth"):
        add("backlog_rpo", "not in summary financials (yfinance)",
            "disclosed revenue backlog / RPO from earnings release or 10-Q")

    return gaps


def build_brief(f: Fundamentals, as_json: bool = False):
    """Build the standard brief spine over `analyze.build_report`."""
    report = analyze.build_report(f, as_json=True)
    if isinstance(report, dict) and report.get("available") is False:
        if as_json:
            return report
        # Text path for unavailable — reuse the string form without a second compute.
        err = report.get("error") or "unavailable"
        return (
            f"Live data for {report.get('ticker', '?')} is unavailable ({err}).\n"
            "Try `--fixture` if a sample exists, or run where yfinance + network work.\n"
            f"{analyze.DISCLAIMER}"
        )

    d = report["derived"]
    rule = report.get("rule40")
    flags = redflags.flags_for(report, limit=3)
    gaps = _gaps(report)

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
        },
        "solvency": {
            "net_debt": d.get("net_debt"),
            "fcf_margin_pct": d.get("fcf_margin_pct"),
            "share_dilution_pct": d.get("share_dilution_pct"),
            "net_debt_to_ebitda": (report.get("leverage") or {}).get("net_debt_to_ebitda"),
            "capex_intensity_pct": d.get("capex_intensity_pct"),
            "revenue_growth_pct": d.get("revenue_growth_pct"),
        },
        "redflags": flags,
        "gaps": gaps,
        "disclaimer": analyze.DISCLAIMER,
    }
    if as_json:
        return payload
    return _render(payload)


def _render(b: dict) -> str:
    out = [
        f"═══ {b.get('name') or b['ticker']} ({b['ticker']}) — brief ═══",
        analyze._source_line(b),
        f"Sector: {b.get('sector') or 'n/a'} / {b.get('industry') or 'n/a'}",
        f"Price: {_fmt_money(b.get('price'))}   Market cap: {_fmt_money(b.get('market_cap'))}",
        "",
    ]

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
    out.append(f"  EV / Sales:   {_mult(v.get('ev_sales'))}")
    out.append(f"  EV / EBITDA:  {_mult(v.get('ev_ebitda'))}")
    if v.get("dcf_per_share") is not None:
        out.append(f"  DCF / share:  {_fmt_money(v.get('dcf_per_share'))}  (heuristic)")
    else:
        out.append(f"  DCF / share:  n/a — {v.get('dcf_note') or 'not computed'}")
    out.append("")

    s = b.get("solvency") or {}
    out.append("Solvency / quality")
    out.append(f"  Revenue growth: {_pct(s.get('revenue_growth_pct'))}")
    out.append(f"  FCF margin:     {_pct(s.get('fcf_margin_pct'))}")
    out.append(f"  Capex intensity: {_pct(s.get('capex_intensity_pct'))}")
    out.append(f"  Dilution:       {_pct(s.get('share_dilution_pct'))}")
    out.append(f"  Net debt:       {_fmt_money(s.get('net_debt'))}")
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

    gaps = b.get("gaps") or []
    if gaps:
        out.append("Gaps (not invented — what would unlock them)")
        for g in gaps:
            out.append(f"  · {g['field']}: {g['why']}")
            out.append(f"      unlocks via: {g['unlocks']}")
    else:
        out.append("Gaps: none on the core fetched set")

    out += ["", *analyze._footer()]
    return "\n".join(out)


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}
    if not args:
        print("usage: python scripts/brief.py <TICKER> [--fixture] [--json]", file=sys.stderr)
        return 2

    f = load_for_cli(args[0], use_fixture="--fixture" in flags)
    report = build_brief(f, as_json="--json" in flags)
    print(json.dumps(report, indent=2) if "--json" in flags else report)
    return 0 if f.available else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
