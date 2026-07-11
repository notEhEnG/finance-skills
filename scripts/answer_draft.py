"""Deterministic user-facing answer drafts from engine reports.

Agents should **send** `answer_draft` (light polish OK). Numbers and conclusions
must come from the report only — this module exists so the skill leads to a
usable analysis, not a raw JSON dump or empty caveat wall.
"""

from __future__ import annotations

import re
from typing import Any

# Keep in sync with agent-policy refuse template.
REFUSE_DRAFT = (
    "I can't give personalized investment advice (including what you should buy, "
    "sell, or allocate).\n\n"
    "If you want a **company-level** analysis of a public ticker, name the ticker "
    "and I can run finance-skills for valuation, risk, or a brief on the engine's "
    "data only. That is research, not a recommendation."
)

NIA = (
    "Read-only market research from available fundamentals — "
    "not investment advice; verify 10-K/10-Q."
)

_AGENT_INSTRUCTIONS = [
    "answer_draft is your evidence floor: keep its material facts and limits, "
    "but write your own analyst synthesis on top (weigh tensions, build the "
    "conditional thesis per SKILL.md section 4a).",
    "Do NOT invent numbers or fill missing metrics from memory.",
    "Do NOT add buy/sell/hold recommendations or personal portfolio advice.",
    "Do NOT dump raw JSON unless the user asks for debug output.",
    "If status is clarify/refuse/error, do not run more company engines until resolved.",
]


def _source_state(report: dict[str, Any] | None) -> str | None:
    if not report:
        return None
    er = report.get("engine_report") or {}
    src = er.get("source") or {}
    if isinstance(src, dict) and src.get("data_state"):
        return src["data_state"]
    raw = report.get("source")
    if raw == "fixture":
        return "fixture"
    if raw == "yfinance":
        return "live"
    return None


def _disabled(report: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not report:
        return []
    er = report.get("engine_report") or {}
    disabled = er.get("disabled_analyses") or report.get("disabled") or []
    return list(disabled) if isinstance(disabled, list) else []


def _flags(report: dict[str, Any] | None, limit: int = 3) -> list[dict[str, Any]]:
    if not report:
        return []
    er = report.get("engine_report") or {}
    flags = er.get("flags") or report.get("flags") or report.get("redflags") or []
    if not isinstance(flags, list):
        return []
    return flags[:limit]


def _fmt_mult(v: Any) -> str | None:
    if v is None:
        return None
    try:
        return f"{float(v):.1f}x"
    except (TypeError, ValueError):
        return str(v)


def _fmt_pct(v: Any) -> str | None:
    if v is None:
        return None
    try:
        return f"{float(v):.1f}%"
    except (TypeError, ValueError):
        return str(v)


def _limit_lead(report: dict[str, Any] | None, intent: str | None) -> list[str]:
    """Material limitations that must lead the answer."""
    leads: list[str] = []
    state = _source_state(report)
    if state == "fixture":
        leads.append("**Sample/fixture data (not live market data).**")
    elif state == "unavailable":
        leads.append("**Company data unavailable** from the engine.")
    for d in _disabled(report):
        analysis = (d.get("analysis") or "analysis").upper()
        reason = d.get("human_reason") or d.get("reason") or "disabled"
        if analysis.lower() == "dcf" or intent == "valuation":
            leads.append(f"**{analysis} disabled:** {reason}")
        elif analysis.lower() in ("rule40", "rule of 40", "ev", "net_debt"):
            leads.append(f"**{analysis} disabled:** {reason}")
    # Cap so we don't bury the answer
    return leads[:4]


def _compare_table_block(report: dict[str, Any]) -> list[str]:
    """Prefer engine markdown_table; rebuild if missing."""
    lines: list[str] = []
    legend = report.get("legend") or {}
    if legend.get("leader") or legend.get("warn"):
        lines.append(
            f"_Legend: {legend.get('leader', '🏆 = leader')} · "
            f"{legend.get('warn', '⚠️ = worst on burn/leverage')}_"
        )
    md = report.get("markdown_table")
    if not md and report.get("rows") and report.get("tickers"):
        # Rebuild a simple highlighted table from row payloads
        tickers = list(report["tickers"])
        header = "| **Metric** | " + " | ".join(f"**{t}**" for t in tickers) + " |"
        sep = "| :--- | " + " | ".join([":---:"] * len(tickers)) + " |"
        body = [header, sep]
        for row in report["rows"]:
            if not isinstance(row, dict):
                continue
            hi = row.get("highlighted") or row.get("values") or {}
            cells = [str(hi.get(t, "n/a")) for t in tickers]
            body.append(f"| **{row.get('metric', '?')}** | " + " | ".join(cells) + " |")
        md = "\n".join(body)
    if md:
        lines.append(md)
    for rl in report.get("ranking_lines") or []:
        lines.append(rl)
    return lines


def _table_from_cells(cells: list[tuple[str, str, str]]) -> list[str]:
    """Render (metric, value, read) triples as a scannable markdown table."""
    if not cells:
        return []
    lines = ["| Metric | Value | Read |", "| --- | --- | --- |"]
    for m, v, rd in cells:
        lines.append(f"| **{m}** | {v} | {rd or '—'} |")
    return lines


def _evidence_lines(report: dict[str, Any], intent: str) -> list[str]:
    # Compare: full markdown table (not dict dumps)
    if intent == "compare" and (report.get("markdown_table") or report.get("tickers")):
        return _compare_table_block(report)

    cells: list[tuple[str, str, str]] = []

    # Valuation / health style rows
    for row in report.get("rows") or []:
        if not isinstance(row, dict):
            continue
        # Skip compare-shaped rows ({metric, values})
        if "values" in row and "value" not in row:
            continue
        m, v, rd = row.get("metric"), row.get("value"), row.get("read")
        if m and v is not None:
            cells.append((str(m), str(v), str(rd) if rd else "—"))
        if len(cells) >= 6:
            break

    # Brief-style structured fields
    if not cells:
        rule = report.get("rule40") or {}
        if rule.get("preferred_score") is not None:
            bar = rule.get("benchmark")
            tag = "PASS" if rule.get("passes") else "BELOW BAR"
            cells.append(
                ("Rule of 40", f"preferred {rule['preferred_score']:.0f}", f"vs bar {bar} → {tag}")
            )
        val = report.get("valuation") or {}
        if val.get("ev_sales") is not None:
            cells.append(("EV/Sales", _fmt_mult(val["ev_sales"]) or "—", "—"))
        if val.get("ev_ebitda") is not None:
            cells.append(("EV/EBITDA", _fmt_mult(val["ev_ebitda"]) or "—", "—"))
        if val.get("dcf_per_share") is not None:
            cells.append(("DCF/share", str(val["dcf_per_share"]), "heuristic"))
        elif val.get("dcf_note"):
            cells.append(("DCF", "n/a", str(val["dcf_note"])))
        sol = report.get("solvency") or {}
        if sol.get("revenue_growth_pct") is not None:
            cells.append(("Revenue growth", _fmt_pct(sol["revenue_growth_pct"]) or "—", "—"))
        if sol.get("fcf_margin_pct") is not None:
            cells.append(("FCF margin", _fmt_pct(sol["fcf_margin_pct"]) or "—", "—"))

    lines = _table_from_cells(cells)

    # Flags are prose-shaped: keep as bullets beneath the table
    flag_lines = []
    for fl in _flags(report):
        name = fl.get("flag") or fl.get("name") or "flag"
        detail = fl.get("detail") or ""
        flag_lines.append(f"- **Flag — {name}:** {detail}")
    if flag_lines:
        if lines:
            lines.append("")
        lines.extend(flag_lines)

    return lines[:20]


def _headline(report: dict[str, Any] | None, intent: str, tickers: list[str]) -> str:
    if not report:
        return ""
    if report.get("verdict"):
        return str(report["verdict"]).strip()
    rule = report.get("rule40") or {}
    if rule.get("verdict"):
        return str(rule["verdict"]).strip()
    if intent == "redflags":
        n = report.get("flag_count")
        if n is None:
            n = len(report.get("flags") or report.get("redflags") or [])
        if n == 0:
            return (
                f"No engine red-flag rules tripped for {', '.join(tickers) or 'this ticker'} "
                "on available fundamentals (absence of flags is not a clean bill of health)."
            )
        return (
            f"{n} red-flag signal(s) on available fundamentals for "
            f"{', '.join(tickers) or 'this ticker'} — see evidence below."
        )
    name = report.get("name") or (tickers[0] if tickers else "Company")
    if intent == "company":
        return f"{name}: walkthrough from engine metrics only (see evidence)."
    if intent == "brief":
        regime = (report.get("regime") or "unknown").replace("_", " ")
        return f"{name}: {regime} regime snapshot from the engine default stack."
    return f"Analysis for {', '.join(tickers) or name} from the engine report."


def _question_frame(query: str, intent: str) -> str | None:
    """One line that ties the draft back to what the user asked."""
    q = query.strip()
    if not q:
        return None
    low = q.lower()
    if intent == "valuation" and any(
        x in low for x in ("buy", "cheap", "expensive", "overvalued", "undervalued", "worth", "dcf")
    ):
        return (
            "Reframing your question as a **valuation/risk screen** "
            "(not a buy/sell recommendation):"
        )
    if intent == "redflags" or intent == "health":
        return "Risk/health view from engine flags and solvency metrics only:"
    if intent == "compare":
        return "Side-by-side comparison from engine metrics only:"
    if intent == "learn":
        return "Concept lesson (no company recommendation):"
    return None


def draft_refuse() -> dict[str, Any]:
    return _pack(
        status="refuse",
        intent="refuse",
        tickers=[],
        answer=REFUSE_DRAFT,
        report=None,
    )


def draft_clarify(question: str, *, intent: str, tickers: list[str]) -> dict[str, Any]:
    q = question or "Which public ticker should I analyze?"
    text = (
        f"{q}\n\n"
        "I need a ticker (or company name the router can map) before running "
        "valuation, risk, or a brief. Example: `is NBIS a buy?` or `brief CRWV`."
    )
    return _pack(status="clarify", intent=intent, tickers=tickers, answer=text, report=None)


def draft_learn(learn_text: str, *, concept: str | None = None) -> dict[str, Any]:
    body = learn_text.strip() if learn_text else "No lesson text available."
    header = f"**Concept:** {concept}\n\n" if concept else ""
    answer = f"{header}{body}\n\n{NIA}"
    return _pack(
        status="learn",
        intent="learn",
        tickers=[],
        answer=answer,
        report=None,
        extra={"concept": concept},
    )


def draft_from_report(
    *,
    query: str,
    intent: str,
    tickers: list[str],
    report: dict[str, Any],
    secondary_intents: list[str] | None = None,
) -> dict[str, Any]:
    """Build a complete answer_draft for a company engine report."""
    parts: list[str] = []

    frame = _question_frame(query, intent)
    if frame:
        parts.append(frame)

    leads = _limit_lead(report, intent)
    if leads:
        parts.append(" ".join(leads))

    headline = _headline(report, intent, tickers)
    if headline:
        parts.append(headline)

    evidence = _evidence_lines(report, intent)
    if evidence:
        if intent == "compare":
            parts.append("**Comparison table** (🏆 leader · ⚠️ worst on burn/leverage)")
        else:
            parts.append("**Evidence (engine only)**")
        # Single-newline join: table rows / bullets must stay adjacent lines,
        # or the markdown table breaks when parts are joined with blank lines.
        parts.append("\n".join(evidence))

    # Secondary risk note for compare+safer style
    if secondary_intents:
        parts.append(
            f"**Also requested:** {', '.join(secondary_intents)} — "
            "only interpret if those fields appear in the report; otherwise safety "
            "cannot be established from this run alone."
        )

    # Filing checklist (short)
    er = report.get("engine_report") or {}
    checklist = er.get("filing_verification_checklist") or report.get("filing_checklist") or []
    if checklist:
        items = []
        for c in checklist[:4]:
            if isinstance(c, dict):
                items.append(c.get("item") or c.get("field") or str(c))
            else:
                items.append(str(c))
        if items:
            parts.append("**Verify in filings:** " + "; ".join(items) + ".")

    parts.append(NIA)
    answer = "\n\n".join(p for p in parts if p)
    return _pack(
        status="ok",
        intent=intent,
        tickers=tickers,
        answer=answer,
        report=report,
        extra={"secondary_intents": list(secondary_intents or [])},
    )


def draft_error(message: str, *, intent: str = "error", tickers: list[str] | None = None) -> dict[str, Any]:
    text = (
        f"**Could not complete analysis.** {message}\n\n"
        "Try a known public ticker, `--fixture` for sample CRWV/NBIS demos, "
        "or `finance-skills doctor` to check the install."
    )
    return _pack(status="error", intent=intent, tickers=tickers or [], answer=text, report=None)


def _pack(
    *,
    status: str,
    intent: str,
    tickers: list[str],
    answer: str,
    report: dict[str, Any] | None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "status": status,
        "intent": intent,
        "tickers": list(tickers),
        "answer_draft": answer.strip(),
        "agent_instructions": list(_AGENT_INSTRUCTIONS),
        "user_visible": True,
        # Signal: agents should stop scripting and respond
        "stop_tool_loop": True,
        "next_action": "respond_with_synthesis",
    }
    if report is not None:
        out["has_engine_report"] = "engine_report" in report or "schema_version" in report
    if extra:
        out.update(extra)
    return out


def concept_key_from_query(query: str) -> str | None:
    """Map NL learn questions to learn.py concept keys."""
    q = f" {query.strip().lower()} "
    mapping = [
        ("rule of 40", "rule40"),
        ("rule of forty", "rule40"),
        ("rule40", "rule40"),
        ("free cash flow", "fcf"),
        (" fcf ", "fcf"),
        ("magic number", "magic-number"),
        ("discounted cash flow", "dcf"),
        (" dcf ", "dcf"),
        ("enterprise value", "ev-ebitda"),
        ("ev/ebitda", "ev-ebitda"),
        ("net revenue retention", "nrr"),
        (" nrr ", "nrr"),
        ("five forces", "five-forces"),
        (" moat ", "moat"),
        ("altman", "altman-z"),
        ("capex", "capex-intensity"),
        ("gross margin", "gross-margin"),
    ]
    for phrase, key in mapping:
        if phrase in q:
            return key
    for tok in re.findall(r"[a-z0-9/-]+", query.lower()):
        if tok in ("dcf", "fcf", "nrr", "moat", "rule40"):
            return tok
    return None
