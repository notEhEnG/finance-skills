"""redflags — scan the shared engine report for warning signs, as a table.

A focused "what could go wrong here?" view. Every flag is derived from the SAME
`analyze.build_report` numbers the other verbs use, so a red flag here can never
contradict the valuation or company walkthrough. Each flag carries a severity
(⛔ high / ⚠ medium / • low) and a plain-English "why it matters". When the data
needed to judge a flag is missing, we say so rather than assume the company is
clean — an absent balance sheet is not a green light.

    python scripts/redflags.py <TICKER> [--fixture|--json]
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
except ImportError:  # …or run directly via `python3 scripts/redflags.py` (skill path)
    import analyze
    from analyze import _fmt_money, _pct
    from data import Fundamentals, get_fundamentals_or_fixture, load_fixture

HIGH, MED, LOW = "⛔", "⚠", "•"


def _flags(r: dict) -> list[dict]:
    """Return a list of {severity, flag, detail} — empty means nothing tripped."""
    d = r["derived"]
    out: list[dict] = []

    def add(sev, flag, detail):
        out.append({"severity": sev, "flag": flag, "detail": detail})

    # Cash burn — negative FCF is the headline solvency question for growth names.
    fcf_m = d.get("fcf_margin_pct")
    if fcf_m is not None and fcf_m < 0:
        sev = HIGH if fcf_m < -50 else MED
        add(sev, "Cash burn", f"FCF margin {_pct(fcf_m)} — spends more cash than it earns; depends on funding.")

    # Shrinking top line.
    g = d.get("revenue_growth_pct")
    if g is not None and g < 0:
        add(HIGH, "Revenue shrinking", f"Revenue down {_pct(g)} YoY — the story is contraction, not growth.")

    # Dilution — revenue 'bought' with equity erodes per-share value.
    dil = d.get("share_dilution_pct")
    if dil is not None and dil > 5:
        sev = HIGH if dil > 15 else MED
        add(sev, "Heavy dilution", f"Share count up {_pct(dil)} YoY — existing holders are being diluted.")

    # Leverage.
    lev = r.get("leverage", {}).get("net_debt_to_ebitda")
    if lev is not None and lev >= 3:
        sev = HIGH if lev >= 5 else MED
        add(sev, "Elevated leverage", f"Net debt / EBITDA = {lev}x — refinancing risk if rates or growth turn.")

    # Capital-intensity gap — EBITDA looks healthy but cash doesn't.
    rule = r.get("rule40")
    if rule and rule.get("capital_intensity_gap", 0) > 40:
        add(MED, "Capital-intensity gap",
            f"EBITDA Rule-40 beats FCF Rule-40 by {rule['capital_intensity_gap']:.0f} pts — "
            "growth is capex-funded, not organically profitable.")

    # Distorted EBITDA — non-operating items inflating the multiple.
    em = d.get("ebitda_margin_pct")
    if em is not None and em > 100:
        add(MED, "Distorted EBITDA", f"EBITDA margin {_pct(em)} (>100%) — non-operating items inflate it; trust EV/Sales.")

    # No intrinsic anchor.
    if "dcf" not in r and d.get("ev_sales") is not None and d.get("ev_sales") >= 20:
        add(MED, "Priced on hope", f"No positive-FCF DCF and EV/Sales {d['ev_sales']}x — a growth bet, not cash-flow-backed.")

    # Missing data we would need to clear a flag — call it out, don't assume clean.
    if d.get("net_debt") is None:
        add(LOW, "Net debt unknown", "Debt or cash not disclosed in the fetched data — leverage can't be judged; check the balance sheet.")

    return out


def build_redflags(f: Fundamentals, as_json: bool = False):
    report = analyze.build_report(f, as_json=True)
    if isinstance(report, dict) and not report.get("available", True):
        return report if as_json else analyze.build_report(f, as_json=False)
    flags = _flags(report)
    if as_json:
        return {"ticker": report["ticker"], "flag_count": len(flags), "flags": flags}
    return _render(report, flags)


def _render(r: dict, flags: list[dict]) -> str:
    out = [
        f"═══ {r['name'] or r['ticker']} ({r['ticker']}) — red flags ═══",
        analyze._source_line(r),
        "",
    ]
    if not flags:
        out += ["  ✓ No red flags tripped on the fetched fundamentals.",
                "    (Absence of a flag is not a clean bill of health — qualitative and",
                "     disclosed-KPI risks aren't visible in the summary financials.)"]
        out += ["", *analyze._footer()]
        return "\n".join(out)

    width = max(len(x["flag"]) for x in flags)
    for x in flags:
        out.append(f"  {x['severity']} {x['flag'].ljust(width)}   {x['detail']}")
    highs = sum(1 for x in flags if x["severity"] == HIGH)
    out += ["", f"{len(flags)} flag(s), {highs} high-severity. ⛔ high · ⚠ medium · • watch.", *analyze._footer()]
    return "\n".join(out)


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}
    if not args:
        print("usage: python scripts/redflags.py <TICKER> [--fixture] [--json]", file=sys.stderr)
        return 2
    ticker = args[0].upper()
    if "--fixture" in flags:
        f = load_fixture(ticker) or Fundamentals(ticker=ticker, available=False, error="no fixture for this ticker")
    else:
        f = get_fundamentals_or_fixture(ticker)
    report = build_redflags(f, as_json="--json" in flags)
    print(json.dumps(report, indent=2) if "--json" in flags else report)
    return 0 if f.available else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
