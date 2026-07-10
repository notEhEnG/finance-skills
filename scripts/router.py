"""Command routing — single verb registry + alias forgiveness + CLI dispatch.

One inventory (`VERBS`) drives help, CANONICAL, Core/Lens tiers, and which
modules the `finance-skills` console entry can run. No-verb / unmatched
questions always land on **`brief`** (method=`default`).

    python3 scripts/router.py help
    python3 scripts/router.py route "is NBIS a value trap?"   # -> redflags
    python3 scripts/router.py brief NBIS --fixture            # dispatches
"""

from __future__ import annotations

import importlib
import re
import sys
from dataclasses import dataclass
from difflib import get_close_matches


@dataclass(frozen=True)
class Verb:
    """One product verb.

    tier:    "core" (engine module), "lens" (qualitative), "meta" (help/route)
    module:  scripts module name with main(argv), or None if not runnable
    group:   help-group label (None = hide from grouped help)
    """
    name: str
    tier: str
    module: str | None = None
    group: str | None = None


# Single source of truth — derive sets/help from this.
VERBS: dict[str, Verb] = {
    "brief":      Verb("brief", "core", "brief", "Default stack"),
    "company":    Verb("company", "core", "company", "Whole company"),
    "analyze":    Verb("analyze", "core", "analyze", "Whole company"),
    "framework":  Verb("framework", "core", "framework", "Whole company"),
    "valuation":  Verb("valuation", "core", "valuation", "Is it cheap?"),
    "redflags":   Verb("redflags", "core", "redflags", "Is it safe?"),
    "health":     Verb("health", "core", "health", "Is it safe?"),
    "compare":    Verb("compare", "core", "compare", "How does it compare?"),
    "screen":     Verb("screen", "core", "screen", "Power tools"),
    "watchlist":  Verb("watchlist", "core", "watchlist", "Power tools"),
    "export":     Verb("export", "core", "export", "Power tools"),
    "learn":      Verb("learn", "core", "learn", "Learn a concept"),
    "moat":       Verb("moat", "lens", None, "Does it have an edge? (lens)"),
    "fiveforces": Verb("fiveforces", "lens", None, "Does it have an edge? (lens)"),
    "help":       Verb("help", "meta", None, None),
}

DEFAULT_VERB = "brief"

# Sector words → framework <name> (not standalone engines).
FRAMEWORK_TOKENS: dict[str, str] = {
    "saas": "saas",
    "neocloud": "neocloud",
    "semiconductor": "semiconductor",
    "ai-cloud": "neocloud",
}

# Shorthand / legacy verbs → runnable Core (no ghost modules).
ALIASES: dict[str, str] = {
    "val": "valuation", "valn": "valuation", "value": "valuation",
    "comp": "compare", "cmp": "compare", "vs": "compare",
    "semis": "semiconductor", "semi": "semiconductor",
    "r40": "brief", "rule40": "brief", "rule-of-40": "brief",
    "ruleof40": "brief", "rule-40": "brief",
    "rf": "redflags", "flags": "redflags", "red-flags": "redflags",
    "risk": "redflags", "risks": "redflags",
    "dcf": "valuation", "dcf-value": "valuation", "intrinsic": "valuation",
    "intrinsic-value": "valuation",
    "growth": "brief", "grow": "brief",
    "aicloud": "ai-cloud", "gpu-cloud": "neocloud",
    "analyse": "analyze", "report": "analyze",
    "moats": "moat",
    "co": "company", "companies": "company", "business": "company",
    "fw": "framework", "frameworks": "framework", "checklist": "framework",
    "5forces": "fiveforces", "five-forces": "fiveforces", "porter": "fiveforces",
    "learn-more": "learn", "teach": "learn", "explain": "learn", "what-is": "learn",
    "summary": "brief", "overview": "brief", "snap": "brief", "snapshot": "brief",
}

# Keywords must resolve to runnable or lens verbs (after alias expansion).
KEYWORDS: dict[str, list[str]] = {
    "valuation": ["is it a buy", "is it cheap", "is it expensive", "over valued",
                  "overvalued", "under valued", "undervalued", "fairly valued",
                  "fair value", "worth buying", "priced right", "too expensive",
                  "how cheap", "cheap or", "should i buy", "a buy", "a sell",
                  "buy or sell", "cheap", "intrinsic value", "discounted cash flow",
                  "fair price", "what is it worth", "what's it worth", "dcf", "worth"],
    "redflags":  ["is it safe", "how risky", "how safe", "blow up", "go bankrupt",
                  "going bankrupt", "could it collapse", "is it a trap", "a value trap",
                  "downside risk", "too much debt", "risky",
                  "red flag", "red flags", "warning sign", "anything wrong",
                  "accounting concern", "going concern", "shady", "smell right",
                  "anything to worry"],
    "health":    ["financial health", "balance sheet", "how healthy", "altman",
                  "piotroski", "bankruptcy risk", "cash runway", "solvency",
                  "self funding", "self-funding"],
    "brief":     ["growth rate", "top line", "how fast is it growing", "revenue trend",
                  "decelerating", "accelerating", "growing fast", "is it growing",
                  "still growing", "rule of 40", "rule of forty", "rule40", "r40",
                  "40 rule", "quick take", "quick look", "the brief", "in brief",
                  "tldr", "tl;dr", "bottom line on", "nutshell"],
    "moat":      ["a moat", "the moat", "competitive advantage", "pricing power",
                  "durable edge", "an edge", "defensible", "wide moat"],
    "compare":   ["compare", " versus ", " vs ", "head to head", "head-to-head",
                  "better than", "which is better", "stack up against"],
    "company":   ["tell me about", "walk me through", "give me the full picture",
                  "overview of", "break it down", "deep dive"],
}

# --- derived views (no second hand-maintained lists) ---------------------

CANONICAL: set[str] = set(VERBS) | set(FRAMEWORK_TOKENS)
CORE_VERBS: set[str] = {n for n, v in VERBS.items() if v.tier == "core"}
LENS_VERBS: set[str] = {n for n, v in VERBS.items() if v.tier == "lens"}
TOP_VERBS: list[str] = ["brief", "company", "analyze", "valuation", "framework", "compare", "learn"]
RUNNABLE: dict[str, str] = {n: v.module for n, v in VERBS.items() if v.module}


def _help_groups() -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    order = [
        "Default stack", "Whole company", "Is it cheap?", "Is it safe?",
        "Does it have an edge? (lens)", "How does it compare?", "Learn a concept",
        "Sector frameworks", "Power tools",
    ]
    for name, v in VERBS.items():
        if not v.group:
            continue
        groups.setdefault(v.group, []).append(name)
    groups["Sector frameworks"] = ["framework", *sorted(FRAMEWORK_TOKENS)]
    # Stable order
    return {g: groups[g] for g in order if g in groups}


HELP_GROUPS: dict[str, list[str]] = _help_groups()


@dataclass
class Resolution:
    input: str
    command: str | None
    method: str                  # exact | alias | fuzzy | unknown
    suggestions: list[str]
    framework: str | None = None  # set when sector token → framework <name>

    @property
    def resolved(self) -> bool:
        return self.command is not None


def _canonicalize(token: str) -> str:
    return ALIASES.get(token, token)


def framework_name(token: str) -> str | None:
    t = _canonicalize(token.strip().lower())
    return FRAMEWORK_TOKENS.get(t)


def resolve(raw: str, fuzzy_cutoff: float = 0.72) -> Resolution:
    token = raw.strip().lower()
    if not token:
        return Resolution(raw, None, "unknown", TOP_VERBS.copy())

    # Sector / framework tokens → command=framework + framework=<name>.
    if token in FRAMEWORK_TOKENS:
        return Resolution(raw, "framework", "exact", [], framework=FRAMEWORK_TOKENS[token])
    canon = _canonicalize(token)
    if canon in FRAMEWORK_TOKENS:
        return Resolution(raw, "framework", "alias", [], framework=FRAMEWORK_TOKENS[canon])

    if token in VERBS:
        return Resolution(raw, token, "exact", [])
    if token in ALIASES:
        target = ALIASES[token]
        if target in FRAMEWORK_TOKENS:
            return Resolution(raw, "framework", "alias", [], framework=FRAMEWORK_TOKENS[target])
        return Resolution(raw, target, "alias", [])

    pool = sorted(CANONICAL) + sorted(ALIASES.keys())
    close = get_close_matches(token, pool, n=3, cutoff=fuzzy_cutoff)
    if close:
        best = _canonicalize(close[0])
        suggestions: list[str] = []
        for c in close:
            sug = "framework" if _canonicalize(c) in FRAMEWORK_TOKENS else _canonicalize(c)
            if sug not in suggestions:
                suggestions.append(sug)
        if best in FRAMEWORK_TOKENS:
            return Resolution(raw, "framework", "fuzzy", suggestions, framework=FRAMEWORK_TOKENS[best])
        return Resolution(raw, best, "fuzzy", suggestions)

    hints = get_close_matches(token, sorted(VERBS), n=3, cutoff=0.4)
    return Resolution(raw, None, "unknown", hints or TOP_VERBS.copy())


_PHRASE_INDEX: list[tuple[str, str]] = sorted(
    ((phrase, verb) for verb, phrases in KEYWORDS.items() for phrase in phrases),
    key=lambda pv: (-len(pv[0]), pv[0], pv[1]),
)


@dataclass
class Route:
    text: str
    verb: str                    # always set — DEFAULT_VERB when nothing matched
    matched: list[tuple[str, str]]
    method: str                  # keyword | verb | default
    framework: str | None = None

    @property
    def resolved(self) -> bool:
        return True


def effective_verb(r: Route) -> str:
    """Always the verb to run (Route.verb is never empty)."""
    return r.verb


def route(text: str, *, apply_default: bool = True) -> Route:
    """Map natural language to a verb.

    With `apply_default=True` (product path) a no-match lands on **`brief`**
    (method=`default`). With `apply_default=False` a genuine no-match returns
    `method="none"` (verb still populated with DEFAULT_VERB so callers never see
    a dead name) — the escape hatch the CLI/agent uses to detect "nothing matched".
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

    first = text.strip().split()
    if first:
        res = resolve(first[0])
        if res.method in ("exact", "alias") and res.command is not None:
            return Route(text, res.command, [(res.command, first[0])], "verb", framework=res.framework)

    method = "default" if apply_default else "none"
    return Route(text, DEFAULT_VERB, [], method)


# --- Ticker extraction ---------------------------------------------------

_COMMON_NAMES = {
    "nvidia": "NVDA", "amd": "AMD", "apple": "AAPL", "microsoft": "MSFT",
    "nebius": "NBIS", "coreweave": "CRWV", "palantir": "PLTR", "micron": "MU",
    "tesla": "TSLA", "meta": "META", "amazon": "AMZN", "google": "GOOGL",
    "alphabet": "GOOGL", "broadcom": "AVGO", "netflix": "NFLX", "snowflake": "SNOW",
}

_TICKER_STOPWORDS = {
    "A", "I", "AI", "AN", "AT", "BE", "BY", "DO", "GO", "IF", "IN", "IS", "IT",
    "ME", "MY", "NO", "OF", "ON", "OR", "SO", "TO", "UP", "US", "USA", "WE",
    "CEO", "CFO", "EPS", "FCF", "PE", "PEG", "ROE", "ROA", "ROIC", "GPU", "CPU",
    "ETF", "IPO", "YOY", "TTM", "DCF", "EV", "EBITDA", "SAAS", "ARR", "RPO",
    "Q1", "Q2", "Q3", "Q4", "YOLO", "OK", "VS", "AND", "THE", "FOR", "BUY",
}

_EXPLICIT_TICKER_RE = re.compile(r"\$([A-Za-z]{1,5}(?:\.[A-Za-z]{1,2})?)\b")
_BARE_UPPER_RE = re.compile(r"\b([A-Z]{2,5}\.[A-Z]{1,2}|[A-Z]{1,5})\b")
_TICKER_SHAPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,15}$")


def extract_tickers(text: str) -> list[str]:
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
    for m in _BARE_UPPER_RE.finditer(text):
        tok = m.group(1)
        if tok not in _TICKER_STOPWORDS and len(tok) >= 2:
            add(tok)
    return found


def _looks_like_ticker(token: str) -> bool:
    return bool(_TICKER_SHAPE.fullmatch(token.strip())) and token.strip().upper() not in _TICKER_STOPWORDS


def format_help() -> str:
    lines = [
        "finance-skills — ask in plain English, or use a Core verb.",
        "",
        "Top verbs:  " + "  ".join(TOP_VERBS),
        f"Default (no verb / bare ticker):  {DEFAULT_VERB}",
        "",
        "Core (engine module) vs Lens (qualitative — not computed scores):",
        f"  Core: {', '.join(sorted(CORE_VERBS - {'help'}))}",
        f"  Lens: {', '.join(sorted(LENS_VERBS))}",
        "",
        "By question:",
    ]
    width = max(len(q) for q in HELP_GROUPS)
    for question, cmds in HELP_GROUPS.items():
        lines.append(f"  {question.ljust(width)}  →  {', '.join(cmds)}")
    lines += [
        "",
        "CLI: finance-skills <verb> <TICKER> [--fixture|--json]",
        "     finance-skills NBIS --fixture          # same as brief",
        "     finance-skills semiconductor CRWV --fixture  # → framework neocloud? semiconductor",
        "Sector words → framework <name>. Legacy: r40/rule40/growth→brief, dcf→valuation, risk→redflags.",
        "Shorthand: val→valuation, comp→compare, snap→brief, semis→framework semiconductor.",
    ]
    return "\n".join(lines)


def _load_module(name: str):
    try:
        return importlib.import_module(f"finance_skills.{name}")
    except ImportError:
        return importlib.import_module(name)


def dispatch(command: str, argv: list[str], framework: str | None = None) -> int:
    """Run a Core module's main(argv)."""
    if command == "framework" and framework:
        argv = [framework, *argv]
    mod_name = RUNNABLE.get(command)
    if not mod_name:
        print(f"'{command}' is a Lens/meta verb — no engine module to run.", file=sys.stderr)
        return 2
    mod = _load_module(mod_name)
    return int(mod.main(argv))


def main(argv: list[str]) -> int:
    if not argv or argv[0].lower() in ("help", "-h", "--help"):
        print(format_help())
        return 0

    head = argv[0].lower()

    if head == "tickers":
        tickers = extract_tickers(" ".join(argv[1:]))
        print(" ".join(tickers) if tickers else "(no ticker found)")
        return 0 if tickers else 1

    if head == "route":
        r = route(" ".join(argv[1:]))
        extra = f"  framework={r.framework}" if r.framework else ""
        others = ", ".join(v for v, _ in r.matched[1:])
        also = f"  (also matched: {others})" if others else ""
        print(f"{r.verb}  [{r.method}]{extra}{also}")
        return 0

    # Dispatch: known verb / framework token / alias → module.main
    res = resolve(argv[0])
    if res.method in ("exact", "alias") and res.command in RUNNABLE:
        return dispatch(res.command, argv[1:], framework=res.framework)

    # A fuzzy verb typo only wins over the ticker fallback when a *later* argument
    # looks like the ticker (e.g. `valuatoin NBIS`) — otherwise a lone token like
    # `HEAL` is a real ticker, not a typo of `health`, and belongs to brief.
    rest = [a for a in argv[1:] if not a.startswith("-")]
    if res.method == "fuzzy" and res.command in RUNNABLE and any(_looks_like_ticker(a) for a in rest):
        return dispatch(res.command, argv[1:], framework=res.framework)

    # Bare ticker or unknown (and fuzzy matches with no trailing ticker) → brief
    # on the full argv (the default product path).
    if res.method in ("unknown", "fuzzy"):
        return dispatch(DEFAULT_VERB, argv)

    if res.command in LENS_VERBS:
        print(
            f"'{res.command}' is a Lens verb (qualitative). "
            f"Run a Core verb for numbers, e.g. `brief <TICKER>`, or reason with engine evidence.",
            file=sys.stderr,
        )
        return 2

    if res.resolved:
        print(f"{res.input} → {res.command}"
              + (f" (framework {res.framework})" if res.framework else "")
              + (f" [{res.method}]" if res.method != "exact" else ""))
        return 0

    print(f"{res.input}: unknown. Closest: {', '.join(res.suggestions)}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
