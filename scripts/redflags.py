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

import sys
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

if __package__:
    from finance_skills import analyze
    from finance_skills.cli import run_single_ticker
    from finance_skills.data import Fundamentals
    from finance_skills.format import footer, pct, source_line
else:
    import analyze
    from cli import run_single_ticker
    from data import Fundamentals
    from format import footer, pct, source_line

HIGH, MED, LOW = "⛔", "⚠", "•"
_SEV_RANK = {HIGH: 0, MED: 1, LOW: 2}


def flags_for(report: dict, *, limit: int | None = None) -> list[dict]:
    """Public flag list for a `build_report` dict — sorted high→low severity.

    Used by `redflags`, `brief`, and `company`. Prefer this over private
    helpers so the default path doesn't depend on underscore APIs.
    """
    d = report["derived"]
    out: list[dict] = []

    def add(sev, flag, detail):
        out.append({"severity": sev, "flag": flag, "detail": detail})

    fcf_m = d.get("fcf_margin_pct")
    if fcf_m is not None and fcf_m < 0:
        sev = HIGH if fcf_m < -50 else MED
        add(sev, "Cash burn", f"FCF margin {pct(fcf_m)} — spends more cash than it earns; depends on funding.")

    g = d.get("revenue_growth_pct")
    if g is not None and g < 0:
        add(HIGH, "Revenue shrinking", f"Revenue down {pct(g)} YoY — the story is contraction, not growth.")

    dil = d.get("share_dilution_pct")
    if dil is not None and dil > 5:
        sev = HIGH if dil > 15 else MED
        add(sev, "Heavy dilution", f"Share count up {pct(dil)} YoY — existing holders are being diluted.")

    lev = (report.get("leverage") or {}).get("net_debt_to_ebitda")
    if lev is not None and lev >= 3:
        sev = HIGH if lev >= 5 else MED
        add(sev, "Elevated leverage", f"Net debt / EBITDA = {lev}x — refinancing risk if rates or growth turn.")

    rule = report.get("rule40")
    if rule and rule.get("capital_intensity_gap", 0) > 40:
        add(MED, "Capital-intensity gap",
            f"EBITDA Rule-40 beats FCF Rule-40 by {rule['capital_intensity_gap']:.0f} pts — "
            "growth is capex-funded, not organically profitable.")

    em = d.get("ebitda_margin_pct")
    if em is not None and em > 100:
        add(MED, "Distorted EBITDA", f"EBITDA margin {pct(em)} (>100%) — non-operating items inflate it; trust EV/Sales.")

    if "dcf" not in report and d.get("ev_sales") is not None and d.get("ev_sales") >= 20:
        add(MED, "Priced on hope", f"No positive-FCF DCF and EV/Sales {d['ev_sales']}x — a growth bet, not cash-flow-backed.")

    if d.get("net_debt") is None:
        add(LOW, "Net debt unknown", "Debt or cash not disclosed in the fetched data — leverage can't be judged; check the balance sheet.")

    out.sort(key=lambda x: _SEV_RANK.get(x["severity"], 9))
    if limit is not None:
        return out[:limit]
    return out


def build_redflags(f: Fundamentals, as_json: bool = False):
    report = analyze.build_report(f)
    if not report.get("available", True):
        return report if as_json else analyze.format_report(report)
    flags = flags_for(report)
    if as_json:
        return {"ticker": report["ticker"], "flag_count": len(flags), "flags": flags}
    return _render(report, flags)


def _render(r: dict, flags: list[dict]) -> str:
    out = [
        f"═══ {r['name'] or r['ticker']} ({r['ticker']}) — red flags ═══",
        source_line(r),
        "",
    ]
    if not flags:
        out += ["  ✓ No red flags tripped on the fetched fundamentals.",
                "    (Absence of a flag is not a clean bill of health — qualitative and",
                "     disclosed-KPI risks aren't visible in the summary financials.)"]
        out += ["", *footer()]
        return "\n".join(out)

    width = max(len(x["flag"]) for x in flags)
    for x in flags:
        out.append(f"  {x['severity']} {x['flag'].ljust(width)}   {x['detail']}")
    highs = sum(1 for x in flags if x["severity"] == HIGH)
    out += ["", f"{len(flags)} flag(s), {highs} high-severity. ⛔ high · ⚠ medium · • watch.", *footer()]
    return "\n".join(out)


def main(argv: list[str]) -> int:
    return run_single_ticker(
        argv,
        usage="usage: python scripts/redflags.py <TICKER> [--fixture] [--json]",
        build=build_redflags,
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
