"""framework — run a named analytical framework as a checklist, not a menu.

`/framework saas CRWD` runs the whole SaaS lens at once instead of making the
user pick metrics one at a time. Each framework is an ordered list of metrics;
for every metric we either compute it from the shared engine or, when it depends
on a *disclosed KPI that is not in the financial statements* (Magic Number, CAC
payback, NRR, backlog/RPO…), we say so and give the definition. We never
fabricate a number the filings don't support — an honest "needs disclosure" beats
a fake metric.

    python scripts/framework.py <framework> <TICKER> [--fixture] [--json]
    python scripts/framework.py list
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import analyze
from analyze import _fmt_money, _pct
from data import Fundamentals, get_fundamentals_or_fixture, load_fixture

# Each metric is (label, source-key, reader). `source` is either a callable that
# derives a line from the engine report, or a KPI string (definition) that the
# financials can't supply. Keeping them declarative makes frameworks easy to add.


def _rule40(r):
    x = r.get("rule40")
    if not x:
        return r.get("rule40_note", "n/a — needs growth and both margins.")
    return (f"judged {x['preferred_score']:.0f} vs {x['benchmark']:.0f} bar → "
            f"{'PASS' if x['passes'] else 'BELOW BAR'} "
            f"(EBITDA {x['score_ebitda']:.0f} / FCF {x['score_fcf']:.0f}, gap {x['capital_intensity_gap']:.0f})")


def _derived(key, fmt=_pct):
    return lambda r: fmt(r["derived"].get(key))


def _capex_adj(r):
    x = r.get("rule40")
    return "n/a" if not x else f"{x['capex_adjusted_score']:.0f} (FCF Rule-40 minus capex intensity)"


def _ev_ebitda(r):
    v = r["derived"].get("ev_ebitda")
    return "n/a (needs positive EBITDA and known net debt)" if v is None else f"{v}x"


# A KPI the income/cash/balance statements don't contain — definition only.
def kpi(definition):
    return ("__kpi__", definition)


FRAMEWORKS: dict[str, dict] = {
    "saas": {
        "title": "SaaS / software quality",
        "metrics": [
            ("Rule of 40", _rule40),
            ("Gross margin", _derived("gross_margin_pct")),
            ("FCF margin", _derived("fcf_margin_pct")),
            ("Revenue growth (YoY)", _derived("revenue_growth_pct")),
            ("EV/EBITDA", _ev_ebitda),
            ("Magic Number", kpi("net-new ARR ÷ prior-quarter S&M spend; >0.75 = efficient growth. Needs S&M + ARR disclosure.")),
            ("CAC payback", kpi("months of gross-margin-adjusted revenue to recover customer acquisition cost. Needs S&M + new-customer/ARR disclosure.")),
            ("Net revenue retention (NRR)", kpi("expansion − churn on existing customers; >120% is elite. A disclosed KPI, not in the financial statements.")),
        ],
    },
    "neocloud": {
        "title": "AI neocloud / GPU capex",
        "metrics": [
            ("Rule of 40 (capex-adjusted)", _rule40),
            ("Capex-adjusted score", _capex_adj),
            ("Capex intensity", _derived("capex_intensity_pct")),
            ("FCF margin", _derived("fcf_margin_pct")),
            ("Net debt / EBITDA", lambda r: f"{r['leverage']['net_debt_to_ebitda']}x" if "leverage" in r else "n/a"),
            ("Backlog / RPO", kpi("remaining performance obligations — the contracted revenue behind the capex. A disclosed KPI; check the 10-K/deck.")),
            ("Funding runway", kpi("cash + undrawn facilities ÷ quarterly burn. Needs the cash-burn and facility disclosures.")),
        ],
    },
    "semiconductor": {
        "title": "Semiconductor economics",
        "metrics": [
            ("Gross margin", _derived("gross_margin_pct")),
            ("EBITDA margin", _derived("ebitda_margin_pct")),
            ("Revenue growth (YoY)", _derived("revenue_growth_pct")),
            ("FCF margin", _derived("fcf_margin_pct")),
            ("EV/EBITDA", _ev_ebitda),
            ("R&D intensity", kpi("R&D ÷ revenue — the reinvestment rate that defends the node lead. Needs the R&D line (not in the summary financials here).")),
            ("Inventory days / cycle", kpi("inventory ÷ COGS × days — reads the cycle. Needs balance-sheet inventory detail.")),
        ],
    },
}

# Route sector/company hints to a framework so the agent can pick a sensible default.
ALIASES = {"software": "saas", "cloud": "neocloud", "ai-cloud": "neocloud",
           "gpu": "neocloud", "semis": "semiconductor", "semi": "semiconductor",
           "chips": "semiconductor"}


def resolve_framework(name: str) -> str | None:
    key = name.strip().lower()
    if key in FRAMEWORKS:
        return key
    return ALIASES.get(key)


def build_framework(name: str, f: Fundamentals, as_json: bool = False):
    fw = FRAMEWORKS[name]
    report = analyze.build_report(f, as_json=True)
    if isinstance(report, dict) and not report.get("available", True):
        return report if as_json else analyze.build_report(f, as_json=False)

    rows = []
    for label, src in fw["metrics"]:
        if isinstance(src, tuple) and src and src[0] == "__kpi__":
            rows.append({"metric": label, "value": None, "kpi": src[1]})
        else:
            rows.append({"metric": label, "value": src(report), "kpi": None})

    if as_json:
        return {"ticker": report["ticker"], "framework": name, "title": fw["title"], "rows": rows}
    return _render(report, name, fw["title"], rows)


def _render(r: dict, name: str, title: str, rows: list[dict]) -> str:
    out = [
        f"═══ {r['name'] or r['ticker']} ({r['ticker']}) — {title} framework ═══",
        f"Source: {r['source']} · as of {r['as_of']}"
        + ("  [SAMPLE DATA — not live]" if r["source"] == "fixture" else ""),
        "",
    ]
    width = max(len(row["metric"]) for row in rows)
    for row in rows:
        if row["kpi"]:
            out.append(f"  {row['metric'].ljust(width)}  ·  needs disclosed KPI")
            out.append(f"  {' '.ljust(width)}     ↳ {row['kpi']}")
        else:
            out.append(f"  {row['metric'].ljust(width)}  :  {row['value']}")
    out += [
        "",
        "Rows marked \"needs disclosed KPI\" aren't in the financial statements — check the "
        "company's 10-K / investor deck; they are not computed here rather than faked.",
        "─" * 60,
        "Read-only market analysis for research/education. Not investment advice; "
        "no trades are placed. Verify figures against primary filings before acting.",
    ]
    return "\n".join(out)


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}
    if args and args[0].lower() == "list":
        for key, fw in FRAMEWORKS.items():
            print(f"{key:14s} {fw['title']}")
        return 0
    if len(args) < 2:
        print("usage: python scripts/framework.py <framework> <TICKER> [--fixture] [--json]\n"
              "       python scripts/framework.py list", file=sys.stderr)
        return 2

    name = resolve_framework(args[0])
    if name is None:
        print(f"unknown framework: {args[0]}. Try: {', '.join(FRAMEWORKS)}", file=sys.stderr)
        return 2
    ticker = args[1].upper()
    if "--fixture" in flags:
        f = load_fixture(ticker) or Fundamentals(ticker=ticker, available=False, error="no fixture for this ticker")
    else:
        f = get_fundamentals_or_fixture(ticker)
    report = build_framework(name, f, as_json="--json" in flags)
    print(json.dumps(report, indent=2) if "--json" in flags else report)
    return 0 if f.available else 1  # surface unavailable/missing-fixture to callers


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
