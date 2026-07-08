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
