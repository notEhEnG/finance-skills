"""company — the sequential, educational company walkthrough.

Renders one narrative that steps through a business the way an analyst reads it,
top to bottom, each stage flowing into the next:

    Business Model → Competitive Advantage → Revenue Drivers → Margins →
    Financial Health → Growth → Valuation → Risks → Verdict

Every number comes from the one shared engine (`analyze.build_report`), so this
never diverges from `analyze`, `valuation`, `rule40`, or `framework`. It adds no
new math — it *sequences and narrates* the engine's output, and is explicit about
anything the data can't support rather than guessing.

    python scripts/company.py <TICKER> [--fixture] [--json]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import analyze
import metrics
from analyze import _fmt_money, _pct
from data import Fundamentals, get_fundamentals_or_fixture, load_fixture

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

    # 1. Business Model — what it is and which regime it plays in.
    biz = [f"Sector: {r.get('sector') or 'n/a'} / {r.get('industry') or 'n/a'}"]
    if regime:
        biz.append(_REGIME_STORY.get(regime, regime.replace("_", " ")))
    sections.append(("Business Model", biz))

    # 2. Competitive Advantage — margins are the fingerprint of pricing power.
    gm, em = d.get("gross_margin_pct"), d.get("ebitda_margin_pct")
    edge: list[str] = []
    if gm is not None:
        edge.append(f"Gross margin {_pct(gm)} — " + (
            "high; suggests pricing power or a software-like cost structure." if gm >= 60
            else "moderate; some differentiation but cost-exposed." if gm >= 40
            else "thin; competes closer to cost/commodity, or is capital-heavy."))
    if em is not None:
        edge.append(f"EBITDA margin {_pct(em)} — operating leverage "
                    + ("already showing." if em >= 20 else "still building." if em >= 0 else "negative; not yet profitable at the operating line."))
    if not edge:
        edge.append("Margin data unavailable — can't read pricing power from the financials alone.")
    sections.append(("Competitive Advantage", edge))

    # 3. Revenue Drivers — scale and how fast it compounds.
    rev = [f"Revenue: {_fmt_money(d.get('revenue'))}"]
    if d["revenue_growth_pct"] is None:
        rev.append("Growth: n/a (no comparable prior period in the data).")
    else:
        rev.append(f"Growth (YoY): {_pct(d['revenue_growth_pct'])}.")
    sections.append(("Revenue Drivers", rev))

    # 4. Margins — the full stack, top to bottom.
    sections.append(("Margins", [
        f"Gross: {_pct(gm)}   EBITDA: {_pct(em)}   FCF: {_pct(d['fcf_margin_pct'])}",
        ("Positive free cash flow — self-funding." if (d['fcf_margin_pct'] or 0) > 0
         else "Negative free cash flow — growth is consuming cash (normal for the regime, watch runway)."),
    ]))

    # 5. Financial Health — leverage and the cash position.
    health: list[str] = []
    if d["net_debt"] is None:
        health.append("Net debt: n/a — debt or cash missing from the data; leverage left uncomputed rather than guessed.")
    else:
        health.append(f"Net debt: {_fmt_money(d['net_debt'])}"
                      + (" (net cash)" if d["net_debt"] < 0 else ""))
    if "leverage" in r:
        health.append(f"Net debt / EBITDA: {r['leverage']['net_debt_to_ebitda']}x "
                      + ("— comfortable." if r['leverage']['net_debt_to_ebitda'] < 3
                         else "— elevated; watch refinancing and covenants."))
    sections.append(("Financial Health", health))

    # 6. Growth — the regime read on the growth rate.
    growth = [f"Growth rate: {_pct(d['revenue_growth_pct'])}"]
    if regime:
        growth.append(_REGIME_STORY.get(regime, "").split(" — ")[0] + " regime.")
    sections.append(("Growth", growth))

    # 7. Valuation — DCF where FCF supports it, plus the EV/EBITDA multiple.
    val: list[str] = []
    if "dcf" in r:
        val.append(f"DCF intrinsic ≈ {_fmt_money(r['dcf']['per_share'])}/share "
                   f"vs price {_fmt_money(r.get('price'))}.")
        if "dcf_basis" in r:
            val.append(r["dcf_basis"])
    elif "dcf_note" in r:
        val.append(f"DCF: {r['dcf_note']}")
    if d.get("ev_ebitda") is not None:
        note = " (net debt unknown, so EV ≈ market cap)" if d["net_debt"] is None else ""
        val.append(f"EV/EBITDA: {d['ev_ebitda']}x{note}.")
    sections.append(("Valuation", val))

    # 8. Risks — pull the honest negatives together, including data gaps.
    risks: list[str] = []
    if rule:
        if rule.get("capital_intensity_gap", 0) > 50:
            risks.append(f"Capital-intensity gap {rule['capital_intensity_gap']:.0f} pts — growth is capex-funded, not organically profitable.")
        if not rule.get("passes", True):
            risks.append(f"Below its Rule-of-40 bar (judged {rule['preferred_score']:.0f} vs {rule['benchmark']:.0f}).")
    if (d["share_dilution_pct"] or 0) > 5:
        risks.append(f"Share dilution {_pct(d['share_dilution_pct'])} YoY — growth partly 'bought' with equity.")
    if (d["fcf_margin_pct"] or 0) < 0:
        risks.append("Cash burn — depends on continued access to funding.")
    gaps = [name for name, val_ in (("gross margin", gm), ("net debt", d["net_debt"])) if val_ is None]
    if gaps:
        risks.append("Data gaps: " + ", ".join(gaps) + " unavailable — verify against filings.")
    if not risks:
        risks.append("No dominant financial red flag in the data; still verify qualitative risks (competition, regulation, concentration).")
    sections.append(("Risks", risks))

    # 9. Final Verdict — synthesise, do not advise.
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
        parts.append(f"DCF anchors fair value near {_fmt_money(r['dcf']['per_share'])}/share — a heuristic, not a target.")
    elif "dcf_note" in r:
        parts.append("No DCF (FCF not positive), so lean on Rule-of-40 and multiples instead of intrinsic value.")
    parts.append("Not a recommendation — verify against primary filings before acting.")
    return parts


def build_company(f: Fundamentals, as_json: bool = False):
    report = analyze.build_report(f, as_json=True)
    if isinstance(report, dict) and not report.get("available", True):
        # Reuse analyze's graceful unavailable message.
        return report if as_json else analyze.build_report(f, as_json=False)
    if as_json:
        return {"ticker": report["ticker"], "sections": [
            {"heading": h, "lines": ls} for h, ls in _story(report)]}
    return _render(report, _story(report))


def _render(r: dict, sections: list[tuple[str, list[str]]]) -> str:
    out = [
        f"═══ {r['name'] or r['ticker']} ({r['ticker']}) — company walkthrough ═══",
        f"Source: {r['source']} · as of {r['as_of']}"
        + ("  [SAMPLE DATA — not live]" if r["source"] == "fixture" else ""),
        f"Price: {_fmt_money(r.get('price'))}   Market cap: {_fmt_money(r.get('market_cap'))}",
        "",
    ]
    for i, (heading, lines) in enumerate(sections):
        out.append(f"■ {heading}")
        for ln in lines:
            out.append(f"    {ln}")
        if i < len(sections) - 1:
            out.append(ARROW)
    out += [
        "",
        "─" * 60,
        "Read-only market analysis for research/education. Not investment advice; "
        "no trades are placed. Verify figures against primary filings before acting.",
    ]
    return "\n".join(out)


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}
    if not args:
        print("usage: python scripts/company.py <TICKER> [--fixture] [--json]", file=sys.stderr)
        return 2
    ticker = args[0].upper()
    if "--fixture" in flags:
        f = load_fixture(ticker) or Fundamentals(ticker=ticker, available=False, error="no fixture for this ticker")
    else:
        f = get_fundamentals_or_fixture(ticker)
    report = build_company(f, as_json="--json" in flags)
    print(json.dumps(report, indent=2) if "--json" in flags else report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
