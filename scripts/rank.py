"""Rank a set of engine reports into decision-support summaries.

Used by screen and watchlist. Pure over report dicts — no network.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def _num(report: dict, getter: Callable[[dict], float | None]) -> float | None:
    try:
        return getter(report)
    except (KeyError, TypeError):
        return None


def _growth(r: dict) -> float | None:
    return (r.get("derived") or {}).get("revenue_growth_pct")


def _dilution(r: dict) -> float | None:
    return (r.get("derived") or {}).get("share_dilution_pct")


def _fcf_margin(r: dict) -> float | None:
    return (r.get("derived") or {}).get("fcf_margin_pct")


def _ev_sales(r: dict) -> float | None:
    return (r.get("derived") or {}).get("ev_sales")


def _rule40(r: dict) -> float | None:
    return (r.get("rule40") or {}).get("preferred_score")


def _pick(
    reports: list[dict],
    getter: Callable[[dict], float | None],
    *,
    higher_is_better: bool,
) -> dict[str, Any] | None:
    scored: list[tuple[float, dict]] = []
    for r in reports:
        v = getter(r)
        if v is None:
            continue
        scored.append((v, r))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=higher_is_better)
    v, r = scored[0]
    return {"ticker": r["ticker"], "value": v}


def rank_reports(reports: list[dict]) -> dict[str, Any]:
    """Return named leaders across common decision dimensions."""
    available = [r for r in reports if r.get("available", True) and "derived" in r]
    return {
        "n": len(available),
        "best_growth": _pick(available, _growth, higher_is_better=True),
        "worst_dilution": _pick(available, _dilution, higher_is_better=True),
        "highest_burn": _pick(available, _fcf_margin, higher_is_better=False),  # most negative
        "cheapest_ev_sales": _pick(available, _ev_sales, higher_is_better=False),
        "strongest_rule40": _pick(available, _rule40, higher_is_better=True),
    }


def render_ranking(ranking: dict[str, Any]) -> list[str]:
    labels = [
        ("best_growth", "Best growth (YoY revenue)"),
        ("worst_dilution", "Worst dilution (share count YoY)"),
        ("highest_burn", "Highest cash burn (lowest FCF margin)"),
        ("cheapest_ev_sales", "Cheapest EV/Sales"),
        ("strongest_rule40", "Strongest Rule of 40 (preferred)"),
    ]
    lines = [f"Ranking summary ({ranking.get('n', 0)} tickers with data)"]
    for key, label in labels:
        hit = ranking.get(key)
        if not hit:
            lines.append(f"  · {label}: n/a")
            continue
        val = hit["value"]
        if isinstance(val, float):
            shown = f"{val:g}"
        else:
            shown = str(val)
        lines.append(f"  · {label}: {hit['ticker']} ({shown})")
    return lines
