"""Command routing — alias forgiveness + fuzzy matching + grouped help.

Pure and offline. Turns whatever the user typed (`val`, `r40`, `vluation`,
`semis`) into a canonical command, so casual users never hit an
"unknown command" wall. Also owns the help taxonomy (grouped by investor
question, not alphabetically), shared between the CLI and SKILL.md.

    python3 scripts/router.py vluation      # -> valuation (fuzzy)
    python3 scripts/router.py help          # grouped help
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from difflib import get_close_matches

# The 5 advertised top-level verbs (overview-2 "Layer 2").
TOP_VERBS = ["analyze", "valuation", "growth", "risk", "moat"]

# Help grouped by the investor question it answers (overview-2 "Help Command").
HELP_GROUPS: dict[str, list[str]] = {
    "Is it cheap?": ["valuation", "rule40", "benchmark"],
    "Is it safe?": ["risk", "redflags", "health"],
    "Will it grow?": ["growth", "opportunities", "earnings"],
    "Does it have an edge?": ["moat", "management", "classify"],
    "How does it compare?": ["compare", "competitors", "benchmark"],
    "What's happening now?": ["news", "earnings"],
    "Sector-specific": ["semiconductor", "ai-cloud", "banking", "reit", "insurance"],
    "Power tools": ["screen", "rank", "portfolio", "watchlist", "export"],
}

# Full canonical command set = top verbs + everything referenced anywhere.
CANONICAL: set[str] = set(TOP_VERBS) | {
    "analyze", "overview", "classify", "health", "profitability", "growth",
    "valuation", "rule40", "ai-cloud", "semiconductor", "banking", "reit",
    "insurance", "marketplace", "industrial", "moat", "management", "risk",
    "competitors", "compare", "benchmark", "redflags", "opportunities",
    "earnings", "news", "screen", "rank", "portfolio", "watchlist", "export",
    "help",
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
    pool = list(CANONICAL) + list(ALIASES.keys())
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
    hints = get_close_matches(token, list(CANONICAL), n=3, cutoff=0.4)
    return Resolution(raw, None, "unknown", hints or TOP_VERBS.copy())


def format_help() -> str:
    lines = [
        "financial-skills — ask in plain English, or use a verb.",
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
