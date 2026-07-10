"""Transcript hard-fail checks for agent answers (mocked — no live LLM).

An agent answer FAILS if it:
- invents numbers not in the engine report
- issues buy/sell/hold recommendations
- hides a disabled DCF when the report disabled it
- presents fixture data as live without disclosure
"""

from __future__ import annotations

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


def score_answer(answer: str, report: dict[str, Any] | None, **kwargs) -> dict[str, Any]:
    fails = hard_fail_checks(answer, report=report, **kwargs)
    return {"pass": not fails, "hard_fails": fails}
