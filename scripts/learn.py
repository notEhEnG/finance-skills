"""learn — a plain-English explainer for the concepts this skill uses.

`/learn dcf` teaches the idea, how it's computed here, how to read it, and the
trap to avoid — so the tool is educational, not just a metric dispenser. Pure and
offline: static reference text, no data fetch. Keys line up with the verbs and
framework rows, so "what is a Magic Number?" has an answer even though the skill
can't compute it from filings.

    python scripts/learn.py <concept>
    python scripts/learn.py list
"""

from __future__ import annotations

import sys
from difflib import get_close_matches

# Each entry: (one-line definition, how it's computed / read, the common trap).
CONCEPTS: dict[str, tuple[str, str, str]] = {
    "rule40": (
        "Rule of 40: a SaaS health check — growth% + profit-margin% should clear ~40.",
        "This skill is segment-aware: it computes both EBITDA-based and FCF-based scores, "
        "shows the broader EBITDA-to-FCF gap between them, and compares against a clearly "
        "labelled project heuristic (not a peer percentile).",
        "40 is not universal. A neocloud posts a huge EBITDA score that's meaningless — judge "
        "pair it with FCF margin and capex intensity instead.",
    ),
    "dcf": (
        "Discounted cash flow: a company is worth the present value of its future free cash flow.",
        "Two-stage model: grow FCF for N years, discount each year back, add a Gordon terminal "
        "value, subtract net debt, divide by shares. The automatic company path disables DCF; "
        "callers of the pure helper must supply all growth, discount, terminal and horizon assumptions.",
        "Output is only as good as the assumptions — tiny changes in growth/discount swing it "
        "wildly. Treat it as a rough anchor, and note it's skipped when FCF is negative.",
    ),
    "fcf": (
        "Free cash flow: operating cash flow minus capital expenditure — the cash a business "
        "actually throws off.",
        "FCF margin = FCF ÷ revenue. Positive means self-funding; negative means growth is "
        "consuming cash and depends on outside funding.",
        "Heavy-capex growth names (neoclouds) show deeply negative FCF by design — read it "
        "against backlog and runway, not in isolation.",
    ),
    "gross-margin": (
        "Gross margin: revenue minus the direct cost of delivering it, as a percent of revenue.",
        "Gross profit ÷ revenue. High (60%+) points to software-like economics or pricing "
        "power; thin margins mean the business competes closer to cost.",
        "Depreciation policy and what's classified as COGS vary — compare within an industry, "
        "not across.",
    ),
    "magic-number": (
        "Magic Number: how efficiently sales & marketing spend converts into new recurring "
        "revenue.",
        "Net-new ARR in a quarter ÷ prior-quarter S&M spend. Above ~0.75 is efficient growth; "
        "below ~0.5 says growth is expensive.",
        "It needs ARR and S&M disclosures — it is NOT in the financial statements this skill "
        "fetches, so the skill flags it rather than fabricating it.",
    ),
    "cac-payback": (
        "CAC payback: how many months of gross profit it takes to earn back the cost of "
        "acquiring a customer.",
        "CAC ÷ (monthly revenue per customer × gross margin). Under ~12 months is strong for "
        "SMB, under ~24 for enterprise.",
        "Requires S&M and new-customer/ARR disclosure — a KPI, not a statement line; the skill "
        "marks it 'needs disclosure'.",
    ),
    "nrr": (
        "Net revenue retention: what last year's customers spend this year — expansion minus "
        "churn and contraction.",
        "Above 100% means the existing base grows by itself; 120%+ is elite. A disclosed KPI "
        "companies report in decks/filings.",
        "Not derivable from the income statement — the skill won't invent it; find it in the "
        "company's disclosures.",
    ),
    "moat": (
        "Moat: a durable structural advantage that protects returns from competition.",
        "Read it from the fingerprints: high, stable gross/EBITDA margins vs peers, pricing "
        "power, and low churn. The engine cannot infer a moat; verify retention, pricing and peer evidence.",
        "Margins alone can be a temporary lead, not a moat — corroborate with switching costs, "
        "network effects, scale, or IP.",
    ),
    "five-forces": (
        "Porter's Five Forces: an industry's profitability is set by rivalry, buyer power, "
        "supplier power, threat of entry, and substitutes.",
        "It's a qualitative lens: score each force, then ask whether the company's economics "
        "(margins, growth) are consistent with a favourable or hostile structure.",
        "It's not computable from financials — use the engine's margins/growth as evidence, but "
        "the force ratings are judgment, not a formula.",
    ),
    "ev-ebitda": (
        "EV/EBITDA: enterprise value (market cap + net debt) per dollar of EBITDA — a "
        "capital-structure-neutral valuation multiple.",
        "Lets you compare firms with different debt loads. Lower can mean cheaper — or slower "
        "growth / worse quality.",
        "Meaningless when EBITDA is near zero or negative; the skill returns n/a there instead "
        "of a nonsense multiple.",
    ),
    "capex-intensity": (
        "Capex intensity: capital expenditure as a percent of revenue — how much the business "
        "must spend to grow.",
        "High intensity (neoclouds) means growth is bought with hardware, so EBITDA overstates "
        "real profitability; the skill shows an EBITDA-minus-capex proxy separately and never "
        "subtracts capex from FCF twice.",
        "A big EBITDA-to-FCF gap can include capex, working capital, cash taxes and interest; "
        "inspect the cash-flow statement before attributing it to one cause.",
    ),
    "altman-z": (
        "Altman Z-Score: a bankruptcy-risk score for public manufacturers.",
        "Weighted mix of working capital, retained earnings, EBIT, equity/liabilities, and "
        "asset turnover. >2.99 safe, 1.81–2.99 grey, <1.81 distress.",
        "Calibrated for manufacturers — don't apply it literally to banks, software, or "
        "asset-light models.",
    ),
}

ALIASES = {
    "rule-of-40": "rule40", "r40": "rule40", "40": "rule40",
    "discounted-cash-flow": "dcf", "intrinsic": "dcf", "intrinsic-value": "dcf",
    "free-cash-flow": "fcf", "fcf-margin": "fcf",
    "gross": "gross-margin", "grossmargin": "gross-margin",
    "magic": "magic-number", "magicnumber": "magic-number",
    "cac": "cac-payback", "payback": "cac-payback",
    "net-revenue-retention": "nrr", "retention": "nrr",
    "porter": "five-forces", "fiveforces": "five-forces", "5forces": "five-forces",
    "ev/ebitda": "ev-ebitda", "evebitda": "ev-ebitda", "multiple": "ev-ebitda",
    "capex": "capex-intensity", "capital-intensity": "capex-intensity",
    "z-score": "altman-z", "altman": "altman-z",
}


def resolve(name: str) -> str | None:
    key = name.strip().lower()
    if key in CONCEPTS:
        return key
    if key in ALIASES:
        return ALIASES[key]
    close = get_close_matches(key, sorted(list(CONCEPTS) + list(ALIASES)), n=1, cutoff=0.7)
    if close:
        return ALIASES.get(close[0], close[0])
    return None


def explain(name: str) -> str | None:
    key = resolve(name)
    if key is None:
        return None
    definition, how, trap = CONCEPTS[key]
    return "\n".join([
        f"═══ {key} ═══",
        definition,
        "",
        f"How to compute / read it:\n  {how}",
        "",
        f"Common trap:\n  {trap}",
    ])


def main(argv: list[str]) -> int:
    if not argv or argv[0].lower() == "list":
        print("Concepts you can /learn:")
        for key in CONCEPTS:
            print(f"  {key}")
        return 0
    text = explain(" ".join(argv))
    if text is None:
        print(f"No lesson for '{' '.join(argv)}'. Try: {', '.join(CONCEPTS)}", file=sys.stderr)
        return 1
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
