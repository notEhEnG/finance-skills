"""Shared presentation helpers for engine reports and view tables.

Public API — views import from here, not from private `analyze._*` names.
Formatting only; no math and no network.
"""

from __future__ import annotations

from typing import Any

DISCLAIMER = (
    "Read-only market analysis for research/education. Not investment advice; "
    "no trades are placed. Verify figures against primary filings before acting."
)


def fmt_money(v: Any) -> str:
    if v is None:
        return "n/a"
    a = abs(v)
    for unit, scale in (("T", 1e12), ("B", 1e9), ("M", 1e6)):
        if a >= scale:
            return f"${v / scale:.2f}{unit}"
    return f"${v:,.0f}"


def pct(v: Any) -> str:
    return "n/a" if v is None else f"{v:.1f}%"


def mult(v: Any) -> str:
    return "n/a" if v is None else f"{v}x"


def source_line(r: dict) -> str:
    """'Source: … · as of … [SAMPLE DATA]' subheader shared by every report view."""
    return (
        f"Source: {r['source']} · as of {r['as_of']}"
        + ("  [SAMPLE DATA — not live]" if r.get("source") == "fixture" else "")
    )


def footer() -> list[str]:
    """Rule + not-advice disclaimer that closes every report view."""
    return ["─" * 60, DISCLAIMER]


def leverage_cell(nd_ebitda: float | None) -> tuple[str, str]:
    """(value, read) for net debt / EBITDA, including net-cash positions."""
    if nd_ebitda is None:
        return "n/a", "not computable"
    if nd_ebitda < 0:
        return f"net cash ({abs(nd_ebitda)}x)", "net cash — no leverage risk"
    if nd_ebitda < 3:
        return f"{nd_ebitda}x", "low leverage"
    if nd_ebitda < 5:
        return f"{nd_ebitda}x", "elevated — watch refinancing"
    return f"{nd_ebitda}x", "high — stress on any downturn"


def render_metric_table(
    title_lines: list[str],
    rows: list[tuple[str, str, str]],
    *,
    verdict: str | None = None,
    extra_lines: list[str] | None = None,
    with_footer: bool = True,
) -> str:
    """Metric | Value | Read table used by valuation and health."""
    mw = max(len(m) for m, _, _ in rows)
    vw = max(len(v) for _, v, _ in rows)
    out = [
        *title_lines,
        "",
        f"  {'Metric'.ljust(mw)}   {'Value'.ljust(vw)}   Read",
        f"  {'─' * (mw + vw + 40)}",
    ]
    for m, v, rd in rows:
        out.append(f"  {m.ljust(mw)}   {v.ljust(vw)}   {rd}")
    if verdict is not None:
        out += ["", f"Verdict: {verdict}"]
    if extra_lines:
        out += ["", *extra_lines]
    if with_footer:
        out += ["", *footer()]
    return "\n".join(out)
