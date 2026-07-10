"""Command routing — alias forgiveness + fuzzy matching + grouped help.

Pure and offline. Turns whatever the user typed (`val`, `r40`, `vluation`,
`semis`) into a canonical command, so casual users never hit an
"unknown command" wall. Also owns the help taxonomy (grouped by investor
question, not alphabetically), shared between the CLI and SKILL.md.

    python3 scripts/router.py vluation      # -> valuation (fuzzy)
    python3 scripts/router.py help          # grouped help
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from difflib import get_close_matches

# The advertised top-level verbs — the primary interface. `company` is the
# flagship sequential walkthrough; the rest are the most-reached lenses.
TOP_VERBS = ["company", "analyze", "valuation", "framework", "compare", "learn"]

# Help grouped by the investor question it answers (overview-2 "Help Command").
HELP_GROUPS: dict[str, list[str]] = {
    "Whole company":       ["company", "analyze", "framework"],
    "Is it cheap?":        ["valuation", "dcf", "rule40", "benchmark"],
    "Is it safe?":         ["risk", "redflags", "health"],
    "Will it grow?":       ["growth", "opportunities", "earnings"],
    "Does it have an edge?": ["moat", "fiveforces", "management"],
    "How does it compare?": ["compare", "competitors", "industry"],
    "Learn a concept":     ["learn"],
    "Sector-specific":     ["semiconductor", "ai-cloud", "banking", "reit", "insurance"],
    "Power tools":         ["screen", "rank", "portfolio", "watchlist", "export"],
}

# Full canonical command set = top verbs + everything referenced anywhere.
CANONICAL: set[str] = set(TOP_VERBS) | {
    "analyze", "company", "framework", "overview", "classify", "health",
    "profitability", "growth", "valuation", "dcf", "rule40", "ai-cloud",
    "semiconductor", "banking", "reit", "insurance", "marketplace", "industrial",
    "moat", "fiveforces", "industry", "management", "risk", "competitors",
    "compare", "benchmark", "redflags", "opportunities", "earnings", "news",
    "learn", "screen", "rank", "portfolio", "watchlist", "export", "help",
}

# Plain-English trigger phrases -> verb, for the TOP verbs only (the rest still
# resolve via an explicit token through `resolve`). Checked as substrings against
# the lowered question, LONGEST phrase first, so "is it a buy" beats "buy" and
# routing is deterministic. This is the "keywords section": it turns a natural
# question into a verb without the agent having to guess. Keep phrases specific —
# a phrase this loose would misfire (that's why "growth" here needs "growth rate"
# / "top line", not the bare word, which also appears inside "growth stock").
KEYWORDS: dict[str, list[str]] = {
    "valuation": ["is it a buy", "is it cheap", "is it expensive", "over valued",
                  "overvalued", "under valued", "undervalued", "fairly valued",
                  "fair value", "worth buying", "priced right", "too expensive",
                  "how cheap", "cheap or", "should i buy", "a buy", "a sell",
                  "buy or sell", "cheap"],
    "risk":      ["is it safe", "how risky", "how safe", "blow up", "go bankrupt",
                  "going bankrupt", "could it collapse", "is it a trap", "a value trap",
                  "downside risk", "too much debt", "risky"],
    "redflags":  ["red flag", "red flags", "warning sign", "anything wrong",
                  "accounting concern", "going concern", "shady", "smell right",
                  "anything to worry"],
    "health":    ["financial health", "balance sheet", "how healthy", "altman",
                  "piotroski", "bankruptcy risk", "cash runway", "solvency",
                  "self funding", "self-funding"],
    "growth":    ["growth rate", "top line", "how fast is it growing", "revenue trend",
                  "decelerating", "accelerating", "growing fast", "is it growing",
                  "still growing"],
    "moat":      ["a moat", "the moat", "competitive advantage", "pricing power",
                  "durable edge", "an edge", "defensible", "wide moat"],
    "dcf":       ["intrinsic value", "discounted cash flow", "fair price", "what is it worth",
                  "what's it worth", "dcf", "worth"],
    "rule40":    ["rule of 40", "rule of forty", "rule40", "r40", "40 rule"],
    "compare":   ["compare", " versus ", " vs ", "head to head", "head-to-head",
                  "better than", "which is better", "stack up against"],
    "company":   ["tell me about", "walk me through", "give me the full picture",
                  "overview of", "break it down", "deep dive"],
}

# Shorthand and common typos/spellings -> canonical (overview-2 "Alias Forgiveness").
ALIASES: dict[str, str] = {
    "val": "valuation", "valn": "valuation", "value": "valuation",
    "comp": "compare", "cmp": "compare", "vs": "compare",
    "semis": "semiconductor", "semi": "semiconductor",
    "mgmt": "management", "mgr": "management",
    "r40": "rule40", "rule-of-40": "rule40", "ruleof40": "rule40", "rule-40": "rule40",
    "rf": "redflags", "flags": "redflags", "red-flags": "redflags",
    "opp": "opportunities", "opps": "opportunities", "catalysts": "opportunities",
    "aicloud": "ai-cloud", "neocloud": "ai-cloud", "gpu": "ai-cloud",
    "analyse": "analyze", "report": "analyze",
    "grow": "growth", "risks": "risk", "moats": "moat",
    "comps": "competitors", "peers": "competitors",
    "co": "company", "companies": "company", "business": "company",
    "fw": "framework", "frameworks": "framework", "checklist": "framework",
    "dcf-value": "dcf", "intrinsic": "dcf", "intrinsic-value": "dcf",
    "5forces": "fiveforces", "five-forces": "fiveforces", "porter": "fiveforces",
    "learn-more": "learn", "teach": "learn", "explain": "learn", "what-is": "learn",
    "sector": "industry", "industries": "industry",
}


@dataclass
class Resolution:
    input: str
    command: str | None          # canonical command, or None if unresolved
    method: str                  # "exact" | "alias" | "fuzzy" | "unknown"
    suggestions: list[str]       # closest canonical commands (for unknown/fuzzy)

    @property
    def resolved(self) -> bool:
        return self.command is not None


def _canonicalize(token: str) -> str:
    return ALIASES.get(token, token)


def resolve(raw: str, fuzzy_cutoff: float = 0.72) -> Resolution:
    token = raw.strip().lower()
    if not token:
        return Resolution(raw, None, "unknown", TOP_VERBS.copy())

    if token in CANONICAL:
        return Resolution(raw, token, "exact", [])
    if token in ALIASES:
        return Resolution(raw, ALIASES[token], "alias", [])

    # Fuzzy: match against canonical commands AND alias keys, then canonicalize.
    # Sort the pools: CANONICAL is a set, so its iteration order varies per run —
    # unsorted, tied similarities would resolve the same typo differently across
    # runs. Sorting makes routing deterministic.
    pool = sorted(CANONICAL) + sorted(ALIASES.keys())
    close = get_close_matches(token, pool, n=3, cutoff=fuzzy_cutoff)
    if close:
        best = _canonicalize(close[0])
        suggestions = []
        for c in close:
            canon = _canonicalize(c)
            if canon not in suggestions:
                suggestions.append(canon)
        return Resolution(raw, best, "fuzzy", suggestions)

    # Nothing close enough — offer best-effort hints, don't error out.
    hints = get_close_matches(token, sorted(CANONICAL), n=3, cutoff=0.4)
    return Resolution(raw, None, "unknown", hints or TOP_VERBS.copy())


# Flat (phrase, verb) index, ordered longest-phrase-first then alphabetically, so
# a substring scan is deterministic regardless of dict iteration order. Ties on
# length break by phrase text, then verb — never by hash order.
_PHRASE_INDEX: list[tuple[str, str]] = sorted(
    ((phrase, verb) for verb, phrases in KEYWORDS.items() for phrase in phrases),
    key=lambda pv: (-len(pv[0]), pv[0], pv[1]),
)


@dataclass
class Route:
    text: str
    verb: str | None             # best-matching verb, or None if nothing triggered
    matched: list[tuple[str, str]]  # every (verb, phrase) hit, best first
    method: str                  # "keyword" | "verb" | "none"

    @property
    def resolved(self) -> bool:
        return self.verb is not None


def route(text: str) -> Route:
    """Map a natural-English question to a verb via the KEYWORDS index.

    Longest phrase wins (see `_PHRASE_INDEX`), so specific intents beat generic
    ones. Falls back to treating the first word as an explicit verb token (via
    `resolve`), so `route("valuation NBIS")` still lands on `valuation`. Returns
    verb=None when nothing triggers — the caller (agent) then uses judgment.
    """
    lowered = f" {text.strip().lower()} "
    matched: list[tuple[str, str]] = []
    seen: set[str] = set()
    for phrase, verb in _PHRASE_INDEX:
        if phrase in lowered and verb not in seen:
            matched.append((verb, phrase))
            seen.add(verb)
    if matched:
        return Route(text, matched[0][0], matched, "keyword")

    # No phrase hit — maybe the user led with an explicit verb token. Only trust
    # an *exact* or *alias* match here: a fuzzy hit on a leading English word
    # ("what", "how", "should") would hijack a plain question that has no verb.
    first = text.strip().split()
    if first:
        res = resolve(first[0])
        if res.method in ("exact", "alias"):
            return Route(text, res.command, [(res.command, first[0])], "verb")
    return Route(text, None, [], "none")


# --- Ticker extraction (front-door helper) --------------------------------
# The agent should also map company names it knows (Nvidia -> NVDA); this helper
# reliably catches explicit symbols in a free-text question like
# "Do you think NBIS is a buy?".

_COMMON_NAMES = {
    "nvidia": "NVDA", "amd": "AMD", "apple": "AAPL", "microsoft": "MSFT",
    "nebius": "NBIS", "coreweave": "CRWV", "palantir": "PLTR", "micron": "MU",
    "tesla": "TSLA", "meta": "META", "amazon": "AMZN", "google": "GOOGL",
    "alphabet": "GOOGL", "broadcom": "AVGO", "netflix": "NFLX", "snowflake": "SNOW",
}

# All-caps words that are NOT tickers (finance jargon / English).
_TICKER_STOPWORDS = {
    "A", "I", "AI", "AN", "AT", "BE", "BY", "DO", "GO", "IF", "IN", "IS", "IT",
    "ME", "MY", "NO", "OF", "ON", "OR", "SO", "TO", "UP", "US", "USA", "WE",
    "CEO", "CFO", "EPS", "FCF", "PE", "PEG", "ROE", "ROA", "ROIC", "GPU", "CPU",
    "ETF", "IPO", "YOY", "TTM", "DCF", "EV", "EBITDA", "SAAS", "ARR", "RPO",
    "Q1", "Q2", "Q3", "Q4", "YOLO", "OK", "VS", "AND", "THE", "FOR", "BUY",
}

# Symbols may carry a class/exchange suffix (BRK.B, RDS.A). For the bare-uppercase
# scan the base must be >=2 letters before a dot, so ordinary abbreviations like
# "U.S." don't read as tickers (their single-letter parts are length-filtered).
_EXPLICIT_TICKER_RE = re.compile(r"\$([A-Za-z]{1,5}(?:\.[A-Za-z]{1,2})?)\b")
_BARE_UPPER_RE = re.compile(r"\b([A-Z]{2,5}\.[A-Z]{1,2}|[A-Z]{1,5})\b")


def extract_tickers(text: str) -> list[str]:
    """Best-effort ticker extraction from a free-text question.

    Order of preference: $-prefixed symbols, then known company names, then
    bare uppercase tokens that aren't jargon. Returns de-duplicated symbols in
    first-seen order. The agent should still resolve names it recognises.
    """
    found: list[str] = []

    def add(sym: str):
        sym = sym.upper()
        if sym and sym not in found:
            found.append(sym)

    for m in _EXPLICIT_TICKER_RE.finditer(text):
        add(m.group(1))

    lowered = text.lower()
    for name, sym in _COMMON_NAMES.items():
        if re.search(rf"\b{re.escape(name)}\b", lowered):
            add(sym)

    # Also scan bare uppercase tokens (stopword-filtered) and merge — a strong
    # match elsewhere shouldn't hide a second symbol like "compare AMD and NVDA".
    for m in _BARE_UPPER_RE.finditer(text):
        tok = m.group(1)
        if tok not in _TICKER_STOPWORDS and len(tok) >= 2:
            add(tok)

    return found


def format_help() -> str:
    lines = [
        "finance-skills — ask in plain English, or use a verb.",
        "",
        "Top verbs:  " + "  ".join(TOP_VERBS),
        "",
        "By question:",
    ]
    width = max(len(q) for q in HELP_GROUPS)
    for question, cmds in HELP_GROUPS.items():
        lines.append(f"  {question.ljust(width)}  →  {', '.join(cmds)}")
    lines += [
        "",
        "Shorthand works too: val→valuation, r40→rule40, comp→compare, semis→semiconductor.",
        "Typos are tolerated (e.g. 'vluation' → valuation).",
        "Plain-English triggers a verb: `router.py route \"is NBIS a value trap?\"` → risk.",
    ]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if not argv or argv[0].lower() in ("help", "-h", "--help"):
        print(format_help())
        return 0
    if argv[0].lower() == "tickers":
        tickers = extract_tickers(" ".join(argv[1:]))
        print(" ".join(tickers) if tickers else "(no ticker found)")
        return 0 if tickers else 1
    if argv[0].lower() == "route":
        r = route(" ".join(argv[1:]))
        if r.verb is None:
            print("(no verb triggered — infer intent from the routing table)")
            return 1
        others = ", ".join(v for v, _ in r.matched[1:])
        extra = f"  (also matched: {others})" if others else ""
        print(f"{r.verb}  [{r.method}]{extra}")
        return 0
    res = resolve(argv[0])
    if res.method == "exact":
        print(f"{res.input} → {res.command}")
    elif res.method == "alias":
        print(f"{res.input} → {res.command} (alias)")
    elif res.method == "fuzzy":
        print(f"{res.input} → {res.command} (fuzzy; did you mean: {', '.join(res.suggestions)}?)")
    else:
        print(f"{res.input}: unknown. Closest: {', '.join(res.suggestions)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
