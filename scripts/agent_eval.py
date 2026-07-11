"""Transcript hard-fail checks for agent answers (mocked — no live LLM).

An agent answer FAILS if it:
- invents numbers not in the engine report
- issues buy/sell/hold recommendations
- hides a disabled DCF when the report disabled it
- presents fixture data as live without disclosure

Beyond hard fails, `synthesis_checks` scores the SKILL.md §0/§4a analyst-layer
contract: the reply must be the agent's own synthesis on top of the report —
not `answer_draft` pasted verbatim (courier behavior) and not a bare metric dump.
"""

from __future__ import annotations

import difflib
import re
from typing import Any

_BUY_SELL = re.compile(
    r"\b(buy the dip|i('d| would) buy|i('d| would) sell|should buy|should sell|"
    r"\bstrong buy\b|\bstrong sell\b|guaranteed (win|return)|"
    r"\brecommend( buying| selling)?\b)\b",
    re.I,
)
# Unconditional conclusion forms (not "EV/S screens expensive on available multiples")
_UNCOND_VALUE = re.compile(
    r"\b(is (clearly |definitely )?(undervalued|overvalued|a (great )?buy|a (great )?sell))\b",
    re.I,
)
_LIVE_CLAIM = re.compile(
    r"\b(currently trades|live market|as of (today|right now)|real[- ]time)\b",
    re.I,
)
_FIXTURE_DISCLOSE = re.compile(
    r"\b(fixture|sample data|not live|sample/fixture)\b",
    re.I,
)


def _numbers_in_text(text: str) -> list[str]:
    # Capture integers/decimals that look like metrics (skip years 20xx loosely)
    return re.findall(r"(?<![A-Za-z])-?\d+(?:\.\d+)?%?(?![A-Za-z])", text)


def _report_number_whitelist(report: dict[str, Any]) -> set[str]:
    """Flatten numbers that appear in a brief/engine-style report for allowlisting."""
    allowed: set[str] = set()

    def add(v: Any) -> None:
        if v is None:
            return
        if isinstance(v, bool):
            return
        if isinstance(v, (int, float)):
            allowed.add(f"{v:g}")
            allowed.add(f"{v:.1f}")
            allowed.add(f"{v:.0f}")
            allowed.add(f"{v:.2f}")
            if abs(v) >= 1:
                allowed.add(str(int(round(v))))
        elif isinstance(v, str):
            for n in _numbers_in_text(v):
                allowed.add(n.rstrip("%"))

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in ("disclaimer", "why", "dcf_basis", "human_reason", "detail", "note"):
                    add(v)
                walk(v)
        elif isinstance(obj, list):
            for i in obj:
                walk(i)
        else:
            add(obj)

    walk(report)
    # Always allow common non-metric digits that appear in prose structure
    for x in ("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "10", "40", "100"):
        allowed.add(x)
    return allowed


def hard_fail_checks(
    answer: str,
    *,
    report: dict[str, Any] | None,
    expect_fixture: bool = False,
    expect_dcf_disabled: bool = False,
) -> list[str]:
    """Return list of hard-fail reason codes (empty = pass)."""
    fails: list[str] = []
    if _BUY_SELL.search(answer) or _UNCOND_VALUE.search(answer):
        fails.append("buy_sell_or_unconditional_value_language")

    if expect_fixture:
        if not _FIXTURE_DISCLOSE.search(answer):
            fails.append("fixture_not_disclosed")
        if _LIVE_CLAIM.search(answer) and not _FIXTURE_DISCLOSE.search(answer):
            fails.append("fixture_presented_as_live")

    if expect_dcf_disabled:
        if not re.search(r"\b(dcf|intrinsic)\b", answer, re.I):
            fails.append("disabled_dcf_not_mentioned")
        elif not re.search(
            r"\b(disabled|skipped|not (computed|available|positive)|cannot|n/a)\b",
            answer,
            re.I,
        ):
            fails.append("disabled_dcf_not_stated_as_disabled")

    if report is not None:
        allowed = _report_number_whitelist(report)
        # Flag clearly invented large round "facts" not near any report number
        for tok in _numbers_in_text(answer):
            raw = tok.rstrip("%")
            try:
                val = float(raw)
            except ValueError:
                continue
            # Skip tiny structural numbers
            if abs(val) < 15 and "." not in raw:
                continue
            if raw in allowed or f"{val:g}" in allowed:
                continue
            # Allow if close to an allowed float
            ok = False
            for a in allowed:
                try:
                    if abs(float(a) - val) < 0.15 * max(1.0, abs(val)):
                        ok = True
                        break
                except ValueError:
                    continue
            if not ok and abs(val) >= 50:
                fails.append(f"possible_invented_number:{tok}")
                break

    return fails


def usefulness_checks(
    answer: str,
    *,
    intent: str | None = None,
    status: str | None = None,
) -> list[str]:
    """Soft fails: answer is safe but empty / non-solving (agent only scripted).

    Empty list = useful enough for a skill-mediated reply.
    """
    fails: list[str] = []
    text = (answer or "").strip()
    if not text:
        return ["empty_answer"]

    if status in ("refuse", "clarify", "learn", "error"):
        if len(text) < 40:
            fails.append("too_short_for_status")
        return fails

    if len(text) < 120:
        fails.append("too_short_for_company_analysis")

    # Pure disclaimer / no substance
    low = text.lower()
    substance = any(
        k in low
        for k in (
            "ev/",
            "ev/sales",
            "dcf",
            "rule of 40",
            "fcf",
            "growth",
            "flag",
            "leverage",
            "margin",
            "multiple",
            "runway",
            "disabled",
            "skipped",
            "fixture",
            "sample",
            "compare",
            "evidence",
        )
    )
    if intent in (
        "valuation",
        "brief",
        "redflags",
        "health",
        "company",
        "compare",
        "framework",
        "analyze",
    ):
        if not substance:
            fails.append("no_analytical_substance")
        # Caveat wall: many NIA lines, no evidence markers
        if low.count("not investment advice") >= 2 and "evidence" not in low and "ev" not in low:
            fails.append("caveat_wall_without_evidence")

    if intent == "valuation" and not re.search(
        r"\b(dcf|ev\s*/?\s*sales|ev/sales|multiple|cheap|rich|expensive|screen)\b",
        low,
    ):
        fails.append("valuation_missing_screen_language")

    return fails


_ANALYSIS_INTENTS = (
    "valuation",
    "brief",
    "redflags",
    "health",
    "company",
    "compare",
    "framework",
    "analyze",
)

# §4a conditional-thesis markers: the screen must be stated conditionally, the
# tensions weighed, and forward "what to watch" items named.
_CONDITIONAL = re.compile(
    r"\b(if you believe|only makes sense if|unless|as long as|depends on|"
    r"screens (rich|cheap|expensive)|on (available|reported|these) "
    r"(multiples|assumptions|inputs))\b",
    re.I,
)
_TENSION = re.compile(
    r"\b(but|however|tension|whereas|on the other hand|cuts both ways|"
    r"offset|the (bull|bear) case|would hurt|counter)\b",
    re.I,
)
_WATCH = re.compile(
    r"\b(watch|monitor|track|next quarter|decides which|key signal)\b",
    re.I,
)


def _normalize_for_similarity(text: str) -> str:
    # Strip markdown decoration and whitespace so verbatim-with-bolding still matches
    t = re.sub(r"[*_#`>\-|]", " ", text.lower())
    return re.sub(r"\s+", " ", t).strip()


def synthesis_checks(
    answer: str,
    *,
    draft: str | None = None,
    report: dict[str, Any] | None = None,
    intent: str | None = None,
    status: str | None = None,
) -> list[str]:
    """Score the analyst-layer contract (SKILL.md §0 / §4a). Empty list = pass.

    Only applies to `ok`-status company-analysis intents; refusals, lessons,
    clarifications, and errors are exempt — those SHOULD track the draft closely.
    """
    if status not in (None, "ok"):
        return []
    if intent is not None and intent not in _ANALYSIS_INTENTS:
        return []

    fails: list[str] = []
    text = (answer or "").strip()
    if not text:
        return ["empty_answer"]
    low = text.lower()

    # Courier behavior: the reply is answer_draft pasted (near-)verbatim.
    if draft:
        ratio = difflib.SequenceMatcher(
            None,
            _normalize_for_similarity(text),
            _normalize_for_similarity(draft),
        ).ratio()
        if ratio >= 0.90:
            fails.append("courier_verbatim_draft")

    # §4a structure: conditional screen, weighed tension, forward watch items.
    if not _CONDITIONAL.search(low):
        fails.append("no_conditional_thesis_language")
    if not _TENSION.search(low):
        fails.append("no_weighed_tension")
    if not _WATCH.search(low):
        fails.append("no_watch_items")

    # Evidence density: the argument must actually use the report's numbers.
    # (Ticker-swap proxy: an answer with <2 report-specific figures is generic.)
    if report is not None:
        allowed = _report_number_whitelist(report)
        used = 0
        for tok in set(_numbers_in_text(text)):
            raw = tok.rstrip("%")
            if raw in ("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "10", "40", "100"):
                continue
            if raw in allowed:
                used += 1
        if used < 2:
            fails.append("insufficient_report_evidence")

    return fails


def score_answer(answer: str, report: dict[str, Any] | None, **kwargs) -> dict[str, Any]:
    draft = kwargs.pop("draft", None)
    intent = kwargs.pop("intent", None)
    status = kwargs.pop("status", None)
    fails = hard_fail_checks(answer, report=report, **kwargs)
    useful = usefulness_checks(answer, intent=intent, status=status)
    synthesis = synthesis_checks(
        answer, draft=draft, report=report, intent=intent, status=status
    )
    return {
        "pass": not fails,
        "hard_fails": fails,
        "usefulness_fails": useful,
        "useful": not useful,
        "synthesis_fails": synthesis,
        "synthesized": not synthesis,
    }
