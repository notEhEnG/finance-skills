"""Command routing — single verb registry + alias forgiveness + CLI dispatch.

One inventory (`VERBS`) drives help, CANONICAL, Core/Lens tiers, and which
modules the `finance-skills` console entry can run. No-verb / unmatched
questions always land on **`brief`** (method=`default`).

    python3 scripts/router.py help
    python3 scripts/router.py route "is NBIS a value trap?"   # -> redflags
    python3 scripts/router.py brief NBIS --fixture            # dispatches
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from difflib import get_close_matches
from pathlib import Path


@dataclass(frozen=True)
class Verb:
    """One product verb.

    tier:     "core" (engine module), "lens" (qualitative), "meta" (help/route)
    module:   scripts module name with main(argv), or None if not runnable
    group:    help-group label (None = hide from grouped help)
    builder:  single-ticker build(Fundamentals, as_json) name on `module`, if any
    """
    name: str
    tier: str
    module: str | None = None
    group: str | None = None
    builder: str | None = None


# Single source of truth — derive sets/help/export/watchlist from this.
VERBS: dict[str, Verb] = {
    "context":    Verb("context", "core", "context", "Project context"),
    "brief":      Verb("brief", "core", "brief", "Default stack", "build_brief"),
    "company":    Verb("company", "core", "company", "Whole company", "build_company"),
    "analyze":    Verb("analyze", "core", "analyze", "Whole company", "build_report_view"),
    "framework":  Verb("framework", "core", "framework", "Whole company"),
    "valuation":  Verb("valuation", "core", "valuation", "Is it cheap?", "build_valuation"),
    "redflags":   Verb("redflags", "core", "redflags", "Is it safe?", "build_redflags"),
    "health":     Verb("health", "core", "health", "Is it safe?", "build_health"),
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
                  "expensive", "richly valued", "rich valuation",
                  "how cheap", "cheap or", "should i buy", "whether to buy", "to buy",
                  "a buy", "a sell", "buy or sell", "cheap", "intrinsic value",
                  "discounted cash flow", "fair price", "what is it worth",
                  "what's it worth", "dcf", "worth"],
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
                  "better than", "which is better", "which is safer", "which is riskier",
                  "stack up against"],
    "company":   ["tell me about", "walk me through", "give me the full picture",
                  "overview of", "break it down", "deep dive"],
}

# --- derived views (no second hand-maintained lists) ---------------------

CANONICAL: set[str] = set(VERBS) | set(FRAMEWORK_TOKENS)
CORE_VERBS: set[str] = {n for n, v in VERBS.items() if v.tier == "core"}
LENS_VERBS: set[str] = {n for n, v in VERBS.items() if v.tier == "lens"}
TOP_VERBS: list[str] = ["brief", "company", "analyze", "valuation", "framework", "compare", "learn"]
RUNNABLE: dict[str, str] = {n: v.module for n, v in VERBS.items() if v.module}
# Single-ticker builders — export + watchlist read this; no second registry.
BUILDERS: dict[str, str] = {n: v.builder for n, v in VERBS.items() if v.builder}
EXPORTABLE: set[str] = set(BUILDERS)
WATCHLIST_VERBS: set[str] = set(BUILDERS)


def _help_groups() -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    order = [
        "Project context", "Default stack", "Whole company", "Is it cheap?", "Is it safe?",
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

# Concept education (no company). Wins only when no ticker is extracted.
_LEARN_PHRASES = (
    "explain rule of 40", "explain the rule of 40", "what is rule of 40",
    "what is the rule of 40", "what's the rule of 40", "what is a rule of 40",
    "define rule of 40", "teach me rule of 40",
    "explain dcf", "what is dcf", "what is a dcf", "what is discounted cash flow",
    "explain free cash flow", "what is free cash flow", "what is fcf",
    "explain magic number", "what is magic number", "what is nrr",
    "explain nrr", "what is net revenue retention", "explain ev/ebitda",
    "what is enterprise value", "what is capex intensity", "explain altman",
    "what is a moat", "explain moat", "what are five forces", "explain five forces",
)

# Personalized advice / execution — never run company analysis as advice.
_REFUSE_PHRASES = (
    "sell everything", "should i sell everything", "should i buy everything",
    "what should i buy", "what should i sell", "pick stocks for me",
    "allocate my", "my 401k", "my portfolio", "rebalance my",
    "place an order", "execute a trade", "place a trade", "buy me some",
    "how much should i invest", "where should i put my money",
)

_RISK_MODIFIERS = (
    "safer", "safer?", "riskier", "more safe", "less risky", "more risky",
    "which is safer", "which is riskier", "stronger balance sheet",
    "weaker balance sheet", "more leverage", "less leverage",
)

_COMPANY_INTENTS = frozenset({
    "brief", "valuation", "redflags", "health", "company", "framework", "moat", "analyze",
})

ROUTE_SCHEMA_VERSION = "1.0.0"

# Agent-facing intent taxonomy (analyze maps to company-class; still runnable).
AGENT_INTENTS = frozenset({
    "brief", "valuation", "redflags", "health", "company", "compare", "framework",
    "screen", "learn", "moat", "help", "refuse", "analyze", "context",
})

FINANCE_WORKFLOWS = frozenset({
    "init", "screen", "underwrite", "audit", "compare", "challenge",
    "stress", "track", "refresh", "explain",
})


@dataclass
class Route:
    text: str
    verb: str                    # always set — DEFAULT_VERB when nothing matched
    matched: list[tuple[str, str]]
    method: str                  # keyword | verb | default | refuse | learn
    framework: str | None = None

    @property
    def resolved(self) -> bool:
        return True


@dataclass
class RouteResult:
    """Machine-readable routing for agents (deterministic; no LLM)."""
    schema_version: str
    original_query: str
    intent: str
    secondary_intents: list[str] = field(default_factory=list)
    tickers: list[str] = field(default_factory=list)
    confidence: float = 0.0
    matched_terms: list[str] = field(default_factory=list)
    ambiguity_flags: list[str] = field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: str | None = None
    refusal_category: str | None = None
    allowed_next_actions: list[str] = field(default_factory=list)
    framework: str | None = None
    method: str = "default"

    def to_dict(self) -> dict:
        return asdict(self)


def _lower_pad(text: str) -> str:
    return f" {text.strip().lower()} "


def route_request(text: str) -> RouteResult:
    """Deterministic NL → intent + tickers for agent middleware.

    Never calls an LLM. Original wording is metadata only (stored in original_query).
    """
    original = text
    lowered = _lower_pad(text)
    tickers = extract_tickers(text)
    matched_terms: list[str] = []
    ambiguity: list[str] = []
    secondary: list[str] = []
    framework: str | None = None
    method = "default"
    intent = DEFAULT_VERB
    confidence = 0.35
    refusal_category: str | None = None

    # --- refuse (personal advice / execution) ---
    for phrase in _REFUSE_PHRASES:
        if phrase in lowered:
            matched_terms.append(phrase)
            return RouteResult(
                schema_version=ROUTE_SCHEMA_VERSION,
                original_query=original,
                intent="refuse",
                tickers=tickers,
                confidence=0.95,
                matched_terms=matched_terms,
                method="refuse",
                refusal_category="personalized_investment_advice",
                allowed_next_actions=[
                    "refuse_personal_advice",
                    "offer_company_analysis_if_ticker_named",
                ],
            )

    # --- learn (concept education). Prefer when a learn phrase matches and there
    # is no *company* ticker. Concept tokens (RULE from "Rule of 40", FREE/CASH
    # from "free cash flow") are stripped so pedagogy does not block learn.
    def _learn_hit() -> str | None:
        for phrase in _LEARN_PHRASES:
            if phrase in lowered:
                return phrase
        for phrase in ("rule of 40", "rule of forty", "rule40"):
            if phrase in lowered or lowered.strip() in ("r40", "rule40"):
                return phrase
        return None

    learn_phrase = _learn_hit()
    if learn_phrase is not None:
        concept_words = {w.upper() for w in re.findall(r"[A-Za-z]+", learn_phrase)}
        company_tickers = [t for t in tickers if t not in concept_words]
        if not company_tickers:
            matched_terms.append(learn_phrase.strip())
            return RouteResult(
                schema_version=ROUTE_SCHEMA_VERSION,
                original_query=original,
                intent="learn",
                tickers=[],
                confidence=0.92,
                matched_terms=matched_terms,
                method="learn",
                allowed_next_actions=["run_learn", "no_ticker_required"],
            )
        # e.g. "rule of 40 for CRM" — keep CRM and fall through to brief keyword
        tickers = company_tickers

    # --- keyword index (longest phrase first) ---
    keyword_hits: list[tuple[str, str]] = []
    seen_verbs: set[str] = set()
    for phrase, verb in _PHRASE_INDEX:
        if phrase in lowered and verb not in seen_verbs:
            keyword_hits.append((verb, phrase))
            seen_verbs.add(verb)

    if keyword_hits:
        intent = keyword_hits[0][0]
        method = "keyword"
        confidence = 0.85
        matched_terms.extend(p for _, p in keyword_hits)
        # Two tickers + riskier/safer without "compare" still means compare
        if intent != "compare" and len(tickers) >= 2:
            for mod in _RISK_MODIFIERS:
                if mod in lowered:
                    intent = "compare"
                    secondary = ["redflags", "health"]
                    matched_terms.append(mod)
                    ambiguity.append("safety_requires_redflags_or_health_evidence")
                    break

        # Secondary intents for compare + risk modifiers
        if intent == "compare" or any(v == "compare" for v, _ in keyword_hits):
            intent = "compare"
            for mod in _RISK_MODIFIERS:
                if mod in lowered:
                    if "redflags" not in secondary:
                        secondary = ["redflags", "health"]
                    matched_terms.append(mod)
                    if "safety_requires_redflags_or_health_evidence" not in ambiguity:
                        ambiguity.append("safety_requires_redflags_or_health_evidence")
                    break
            if any(v == "valuation" for v, _ in keyword_hits[1:]):
                if "valuation" not in secondary:
                    secondary.append("valuation")
        elif len(keyword_hits) > 1:
            for v, _ in keyword_hits[1:]:
                if v != intent and v not in secondary:
                    secondary.append(v)
            if secondary:
                ambiguity.append("multiple_keyword_intents")

    # --- leading verb / framework token ---
    first = text.strip().split()
    if first and method == "default":
        res = resolve(first[0])
        if res.method in ("exact", "alias") and res.command is not None:
            intent = res.command
            method = "verb" if res.method == "exact" else "alias"
            confidence = 0.9 if res.method == "exact" else 0.8
            matched_terms.append(first[0])
            framework = res.framework
            if intent == "framework" and framework:
                matched_terms.append(framework)

    # help
    if text.strip().lower() in ("help", "-h", "--help") or lowered.strip() == "help":
        intent, method, confidence = "help", "verb", 0.99
        matched_terms.append("help")

    # Map analyze stays analyze (runnable); agent taxonomy allows it
    if intent == "risk":  # should not happen — alias maps to redflags
        intent = "redflags"

    # Company intent without ticker → clarify (except we already handled learn/refuse)
    needs_clarification = False
    clarification_question = None
    if intent in _COMPANY_INTENTS and not tickers:
        needs_clarification = True
        clarification_question = (
            "Which public company ticker should I analyze "
            "(for example NVDA or BRK.B)?"
        )
        ambiguity.append("missing_ticker")
        confidence = min(confidence, 0.55)
    if intent == "compare" and len(tickers) < 2:
        needs_clarification = True
        clarification_question = (
            "Which two or more public tickers should I compare?"
        )
        ambiguity.append("compare_needs_two_tickers")
        confidence = min(confidence, 0.55)

    # Default path
    if method == "default" and intent == DEFAULT_VERB and not keyword_hits:
        if not tickers and not first:
            confidence = 0.2
        elif tickers and not keyword_hits:
            confidence = 0.5  # bare ticker → brief is intentional
            method = "default"
        else:
            confidence = 0.35

    actions: list[str] = []
    if intent == "refuse":
        actions = ["refuse_personal_advice"]
    elif intent == "learn":
        actions = ["run_learn"]
    elif intent == "help":
        actions = ["show_help"]
    elif needs_clarification:
        actions = ["ask_clarification"]
    else:
        actions = [f"run_{intent}"]
        if secondary:
            actions.append("attach_secondary_intents")
        actions.append("compose_from_engine_report_only")

    return RouteResult(
        schema_version=ROUTE_SCHEMA_VERSION,
        original_query=original,
        intent=intent,
        secondary_intents=secondary,
        tickers=tickers,
        confidence=confidence,
        matched_terms=matched_terms,
        ambiguity_flags=ambiguity,
        needs_clarification=needs_clarification,
        clarification_question=clarification_question,
        refusal_category=refusal_category,
        allowed_next_actions=actions,
        framework=framework,
        method=method,
    )


def route_finance_request(text: str) -> RouteResult:
    """Route the redesigned `/finance` namespace without changing legacy routes."""
    original = text.strip()
    legacy = route_request(original)
    if legacy.intent == "refuse":
        return legacy
    tickers = extract_tickers(original)
    lowered = f" {original.lower()} "
    first = original.split(maxsplit=1)[0].lower() if original else ""
    if first in FINANCE_WORKFLOWS:
        intent = first
        method = "verb"
        confidence = 0.99
    elif any(phrase in lowered for phrase in (" deep dive", " underwrite", " full thesis")):
        intent, method, confidence = "underwrite", "keyword", 0.9
    elif any(phrase in lowered for phrase in (" audit", " accounting", " verify numbers", " red flag")):
        intent, method, confidence = "audit", "keyword", 0.9
    elif any(phrase in lowered for phrase in (" compare", " vs ", " versus ")):
        intent, method, confidence = "compare", "keyword", 0.9
    elif any(phrase in lowered for phrase in (" challenge", " roast", " argue against")):
        intent, method, confidence = "challenge", "keyword", 0.9
    elif any(phrase in lowered for phrase in (" stress", " scenario", " sensitivity")):
        intent, method, confidence = "stress", "keyword", 0.9
    elif any(phrase in lowered for phrase in (" track", " save research")):
        intent, method, confidence = "track", "keyword", 0.9
    elif any(phrase in lowered for phrase in (" refresh", " update thesis", " new results")):
        intent, method, confidence = "refresh", "keyword", 0.9
    elif any(phrase in lowered for phrase in (" explain", " what is ", " define ")):
        intent, method, confidence = "explain", "keyword", 0.85
    elif not original:
        intent, method, confidence = "init", "context", 0.7
    else:
        intent, method, confidence = "screen", "default", 0.75

    needs_clarification = False
    clarification = None
    if intent == "compare" and len(tickers) < 2:
        needs_clarification = True
        clarification = "Which two or more public tickers should I compare?"
    elif intent not in {"init", "explain"} and not tickers:
        needs_clarification = True
        clarification = "Which public company ticker should I use?"
    return RouteResult(
        schema_version="2.0.0",
        original_query=text,
        intent=intent,
        tickers=tickers,
        confidence=confidence,
        matched_terms=[first] if method == "verb" else [],
        ambiguity_flags=["missing_ticker"] if needs_clarification else [],
        needs_clarification=needs_clarification,
        clarification_question=clarification,
        allowed_next_actions=(
            ["ask_clarification"]
            if needs_clarification
            else ["load_context", f"load_reference_{intent}", f"run_{intent}"]
        ),
        method=method,
    )


def route(text: str, *, apply_default: bool = True) -> Route:
    """Map natural language to a verb (backward-compatible wrapper).

    With `apply_default=True` (product path) a no-match lands on **`brief`**.
    With `apply_default=False` a genuine no-match returns `method="none"`.
    """
    rr = route_request(text)
    if rr.intent == "refuse":
        # Compat: callers expecting a verb still see brief, but method marks refuse
        return Route(text, DEFAULT_VERB, [(t, t) for t in rr.matched_terms], "refuse")
    if rr.intent == "learn":
        return Route(text, "learn", [(t, t) for t in rr.matched_terms], "learn")
    if not apply_default and rr.method == "default" and not rr.matched_terms and not rr.tickers:
        return Route(text, DEFAULT_VERB, [], "none")
    # Rebuild matched as (verb, phrase) when possible
    matched_pairs: list[tuple[str, str]] = []
    lowered = _lower_pad(text)
    for phrase, verb in _PHRASE_INDEX:
        if phrase in lowered:
            matched_pairs.append((verb, phrase))
    if not matched_pairs and rr.matched_terms:
        matched_pairs = [(rr.intent, t) for t in rr.matched_terms]
    return Route(
        text,
        rr.intent if rr.intent != "refuse" else DEFAULT_VERB,
        matched_pairs,
        rr.method if rr.method != "default" or apply_default else "none",
        framework=rr.framework,
    )


# --- Ticker extraction ---------------------------------------------------

_COMMON_NAMES = {
    "nvidia": "NVDA", "amd": "AMD", "apple": "AAPL", "microsoft": "MSFT",
    "nebius": "NBIS", "coreweave": "CRWV", "palantir": "PLTR", "micron": "MU",
    "tesla": "TSLA", "meta": "META", "amazon": "AMZN", "google": "GOOGL",
    "alphabet": "GOOGL", "broadcom": "AVGO", "netflix": "NFLX", "snowflake": "SNOW",
    "ford": "F", "intel": "INTC", "reddit": "RDDT", "shopify": "SHOP",
    "salesforce": "CRM", "crowdstrike": "CRWD", "berkshire": "BRK.B",
}

# Lowercase bare-symbol support is deliberately finite. Treating every short
# English word as a ticker made company names such as Ford resolve to the
# nonexistent FORD. Unknown symbols remain available via standard ALL-CAPS or
# explicit $ticker syntax.
_KNOWN_BARE_SYMBOLS = frozenset({
    *_COMMON_NAMES.values(),
    "ARM", "ASML", "AVGO", "BRK.B", "CAVA", "CRM", "CRWD", "GOOG", "INTC", "MU",
    "NOW", "ORCL", "PANW", "QCOM", "RDDT", "SHOP", "SMCI", "TSM", "UBER", "LYFT",
})

_TICKER_STOPWORDS = {
    "A", "I", "AI", "AN", "AT", "BE", "BY", "DO", "GO", "IF", "IN", "IS", "IT",
    "ME", "MY", "NO", "OF", "ON", "OR", "SO", "TO", "UP", "US", "USA", "WE",
    "CEO", "CFO", "EPS", "FCF", "PE", "PEG", "ROE", "ROA", "ROIC", "GPU", "CPU",
    "ETF", "IPO", "YOY", "TTM", "DCF", "EV", "EBITDA", "SAAS", "ARR", "RPO",
    "Q1", "Q2", "Q3", "Q4", "YOLO", "OK", "VS", "AND", "THE", "FOR", "BUY",
    # Common English (case-insensitive bare scan would otherwise treat as tickers)
    "SELL", "HOLD", "ALL", "ANY", "ARE", "BUT", "CAN", "DID", "GET", "HAS",
    "HER", "HIM", "HIS", "HOW", "ITS", "LET", "MAY", "NEW", "NOT", "NOW",
    "OLD", "OUR", "OUT", "OWN", "SAY", "SHE", "TOO", "USE", "WHO", "WHY",
    "YOU", "BAD", "BIG", "FEW", "FAR", "LOW", "TOP", "RUN", "SET", "TRY",
    "WAY", "YET", "ALSO", "BACK", "BEST", "BOTH", "CALL", "CAME", "COME",
    "EACH", "EVEN", "EVER", "FIND", "FROM", "GIVE", "GOOD", "HAVE", "HERE",
    "HIGH", "INTO", "JUST", "KNOW", "LAST", "LIKE", "LONG", "LOOK", "MADE",
    "MAKE", "MANY", "MORE", "MOST", "MUCH", "MUST", "NAME", "NEED", "NEXT",
    "ONLY", "OVER", "PART", "REAL", "SAME", "SEEM", "SHOW", "SOME", "SUCH",
    "SURE", "TAKE", "TELL", "THAN", "THAT", "THEM", "THEN", "THEY", "THIS",
    "TIME", "TRUE", "VERY", "WANT", "WELL", "WERE", "WHAT", "WHEN", "WILL",
    "WITH", "YEAR", "YOUR", "ABOUT", "AFTER", "AGAIN", "BEING", "COULD",
    "DOING", "EVERY", "FIRST", "FOUND", "GREAT", "MIGHT", "OTHER", "RIGHT",
    "SHALL", "SINCE", "STILL", "THEIR", "THERE", "THESE", "THING", "THINK",
    "THOSE", "THREE", "UNDER", "UNTIL", "VALUE", "WHERE", "WHICH", "WHILE",
    "WORLD", "WOULD", "WRITE", "YEARS", "CHEAP", "PRICE", "STOCK", "SHARE",
    "MARKET", "TRADE", "RISKY", "SAFER", "QUICK", "BRIEF", "LEARN", "HELP",
    "RISKS", "FLAGS", "GROW", "GROWN", "FAIR", "RICH", "SAFE", "TRAP",
    # Pedagogy / concept words (case-insensitive bare scan)
    "STORY", "RULE", "FORTY", "FREE", "CASH", "FLOW", "MAGIC", "NUMBER",
    "EXPLAIN", "DEFINE", "TEACH", "MOAT", "FORCE", "FORCES", "ALTMAN",
    "CAPEX", "NRR", "WORTH", "EDGE",
}

_EXPLICIT_TICKER_RE = re.compile(r"\$([A-Za-z]{1,5}(?:\.[A-Za-z]{1,2})?)\b")
# Uppercase-only (legacy) and case-insensitive bare symbols (user often types "nbis").
_BARE_UPPER_RE = re.compile(r"\b([A-Z]{2,5}\.[A-Z]{1,2}|[A-Z]{1,5})\b")
_BARE_TICKER_CI_RE = re.compile(r"\b([A-Za-z]{2,5}(?:\.[A-Za-z]{1,2})?)\b")
# Unknown lowercase symbols are accepted only in strong ticker contexts. This
# retains natural prompts such as "analyze sofi" and "compare sofi and hood"
# without treating arbitrary Title Case company-like words as tickers.
_CONTEXTUAL_LOWER_RE = re.compile(
    r"\b(?:analyze|brief|value|valuation|risk|health|company|stock|ticker|compare|vs|versus|and|is|on|for)\s+"
    r"([a-z]{1,5}(?:\.[a-z]{1,2})?)\b"
)
_TICKER_SHAPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,15}$")


def extract_tickers(text: str) -> list[str]:
    found: list[str] = []

    def add(sym: str):
        sym = sym.upper()
        if sym and sym not in found and sym not in _TICKER_STOPWORDS:
            found.append(sym)

    for m in _EXPLICIT_TICKER_RE.finditer(text):
        add(m.group(1))
    lowered = text.lower()
    for name, sym in _COMMON_NAMES.items():
        if re.search(rf"\b{re.escape(name)}\b", lowered):
            add(sym)
    # Prefer explicit ALL-CAPS tokens (classic ticker orthography).
    for m in _BARE_UPPER_RE.finditer(text):
        add(m.group(1))
    # Case-insensitive bare tokens: "nbis", "aapl", "Brk.B" — stopwords filter noise.
    for m in _BARE_TICKER_CI_RE.finditer(text):
        candidate = m.group(1).upper()
        if candidate in _KNOWN_BARE_SYMBOLS:
            add(candidate)
    for m in _CONTEXTUAL_LOWER_RE.finditer(text):
        add(m.group(1))
    stripped = text.strip()
    if stripped == stripped.lower() and _looks_like_ticker(stripped):
        add(stripped)
    return found


def _looks_like_ticker(token: str) -> bool:
    return bool(_TICKER_SHAPE.fullmatch(token.strip())) and token.strip().upper() not in _TICKER_STOPWORDS


def format_help() -> str:
    lines = [
        "finance-skills — ask in plain English, or use a Core verb.",
        "",
        "Preferred (agents):  finance-skills ask \"<question>\" [--fixture] [--json]",
        "  → route + engine + answer_draft (send answer_draft to the user; stop scripting).",
        "Diagnostics:         finance-skills doctor [--json]",
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
        "Redesigned namespace:",
        "  finance context --format json",
        "  finance screen --ticker NVDA --format json",
        "  finance underwrite --ticker NVDA --format json",
        "  finance snapshot create --ticker NVDA --format json",
        "  finance diff --ticker NVDA --format json",
        "",
        "CLI: finance-skills ask \"is NBIS a buy?\" --fixture",
        "     finance-skills <verb> <TICKER> [--fixture|--json]",
        "     finance-skills NBIS --fixture          # same as brief",
        "     finance-skills semiconductor CRWV --fixture  # → framework semiconductor",
        "Sector words → framework <name>. Legacy: r40/rule40/growth→brief, dcf→valuation, risk→redflags.",
        "Shorthand: val→valuation, comp→compare, snap→brief, semis→framework semiconductor.",
    ]
    return "\n".join(lines)


def _load_module(name: str):
    """Load a sibling module from the same directory as this file.

    Prefer co-located sources over a possibly-stale site-packages install: when
    tests/skill path put `scripts/` on sys.path, `import finance_skills.X` can
    still resolve to an older installed copy. Loading by file path keeps
    dispatch and builders on the same tree as this router.
    """
    import importlib.util

    path = Path(__file__).resolve().parent / f"{name}.py"
    if path.is_file():
        for mod in sys.modules.values():
            mod_file = getattr(mod, "__file__", None)
            if mod_file and Path(mod_file).resolve() == path:
                return mod
        # Unique name so we don't collide with a different on-disk copy already loaded.
        unique = f"_finance_skills_colocal.{name}"
        spec = importlib.util.spec_from_file_location(unique, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {path}")
        mod = importlib.util.module_from_spec(spec)
        # Force skill-path imports (not a stale site-packages finance_skills).
        mod.__package__ = None
        sys.modules[unique] = mod
        spec.loader.exec_module(mod)
        return mod
    try:
        return importlib.import_module(f"finance_skills.{name}")
    except ImportError:
        return importlib.import_module(name)


def load_builder(command: str):
    """Return build(Fundamentals, as_json) for a registered single-ticker verb."""
    builder = BUILDERS.get(command)
    if not builder:
        raise KeyError(f"no single-ticker builder for {command!r}")
    mod = _load_module(RUNNABLE[command])
    return getattr(mod, builder)


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

    # Redesigned exact workflow grammar. Legacy screen/compare/explain forms
    # remain available unless their new named arguments are present.
    redesigned = {
        "init", "underwrite", "audit", "challenge", "stress", "track",
        "refresh", "snapshot", "diff",
    }
    uses_redesigned_grammar = (
        head in redesigned
        or (head == "screen" and any(arg == "--ticker" or arg.startswith("--ticker=") for arg in argv[1:]))
        or (head == "compare" and any(arg == "--tickers" or arg.startswith("--tickers=") for arg in argv[1:]))
        or (head == "explain" and any(arg == "--topic" or arg.startswith("--topic=") for arg in argv[1:]))
    )
    if uses_redesigned_grammar:
        workflow_cli = _load_module("workflow_cli")
        return int(workflow_cli.main(argv))

    # Preferred agent path: one-shot route → engine → answer_draft
    if head in ("ask", "doctor"):
        ask_mod = _load_module("ask")
        return int(ask_mod.main(argv if head == "doctor" else argv[1:]))

    if head == "tickers":
        tickers = extract_tickers(" ".join(argv[1:]))
        print(" ".join(tickers) if tickers else "(no ticker found)")
        return 0 if tickers else 1

    if head == "route":
        rest = argv[1:]
        as_json = "--json" in rest
        query = " ".join(a for a in rest if a != "--json")
        if as_json:
            print(json.dumps(route_request(query).to_dict(), indent=2))
            return 0
        r = route(query)
        rr = route_request(query)
        if rr.intent == "refuse":
            print(f"refuse  [refuse]  category={rr.refusal_category}")
            return 0
        extra = f"  framework={r.framework}" if r.framework else ""
        others = ", ".join(v for v, _ in r.matched[1:])
        also = f"  (also matched: {others})" if others else ""
        sec = f"  secondary={rr.secondary_intents}" if rr.secondary_intents else ""
        print(f"{rr.intent}  [{rr.method}]{extra}{sec}{also}")
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
