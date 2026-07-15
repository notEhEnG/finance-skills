"""One-shot ask: route → engine → answer_draft.

This is the **preferred agent path**. Running route + valuation separately is
still valid, but agents that only dump JSON fail the product. `ask` returns a
ready-to-send `answer_draft` so the skill actually answers the user.
"""

from __future__ import annotations

import inspect
import json
import sys
import traceback
from pathlib import Path
from typing import Any

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

if __package__:
    from finance_skills import answer_draft, learn, report_schema, router
    from finance_skills.data import load_for_cli
else:
    import answer_draft
    import learn
    import report_schema
    import router
    from data import load_for_cli

_SINGLE = frozenset({
    "brief", "valuation", "redflags", "health", "company", "analyze",
})


def _load_builder(command: str):
    return router.load_builder(command)


def _accepts_flags(build) -> bool:
    """True if a builder takes a `flags` keyword (brief, valuation)."""
    try:
        return "flags" in inspect.signature(build).parameters
    except (TypeError, ValueError):
        return False


def _run_single(intent: str, ticker: str, *, use_fixture: bool) -> dict[str, Any]:
    f = load_for_cli(ticker, use_fixture=use_fixture)
    if intent == "moat":
        # Numbers from brief; qualitative lens note added in draft path
        intent = "brief"
    build = _load_builder(intent if intent in router.BUILDERS else "brief")
    # Only pass --explain to builders that actually accept a `flags` kwarg
    # (brief, valuation). Feature-detect rather than catch-and-retry, so a real
    # TypeError raised *inside* a builder isn't silently swallowed.
    if _accepts_flags(build):
        report = build(f, True, flags={"--explain"})
    else:
        report = build(f, True)
    if isinstance(report, dict):
        return report
    return {"ticker": ticker, "available": f.available, "text": str(report)}


def _run_compare(tickers: list[str], *, use_fixture: bool) -> dict[str, Any]:
    analyze = router._load_module("analyze")
    compare = router._load_module("compare")
    reports = []
    unavailable: list[str] = []
    for t in tickers:
        f = load_for_cli(t, use_fixture=use_fixture)
        rep = analyze.build_report(f)
        if rep.get("available", True):
            reports.append(rep)
        else:
            unavailable.append(t)
    if len(reports) < 2:
        return {
            "available": False,
            "tickers": tickers,
            "unavailable": unavailable,
            "error": f"Need ≥2 tickers with data; unavailable: {', '.join(unavailable) or '—'}",
        }
    out = compare.build_compare(reports, as_json=True)
    out["unavailable"] = unavailable
    # Attach a light engine_report from the first available name for draft limits
    if reports and "engine_report" not in out:
        out = report_schema.attach_engine_report(
            out, reports[0], intent="compare",
        )
    return out


def _run_framework(name: str | None, ticker: str, *, use_fixture: bool) -> dict[str, Any]:
    framework = router._load_module("framework")
    f = load_for_cli(ticker, use_fixture=use_fixture)
    fw = name or "saas"
    return framework.build_framework(fw, f, as_json=True)


def run_ask(query: str, *, use_fixture: bool = False) -> dict[str, Any]:
    """Route + execute + draft. Pure orchestration; no LLM."""
    rr = router.route_request(query)
    route_dict = rr.to_dict()
    base: dict[str, Any] = {
        "schema_version": "ask.1",
        "query": query,
        "route": route_dict,
        "fixture": use_fixture,
    }

    if rr.intent == "refuse":
        draft = answer_draft.draft_refuse()
        return {**base, **draft, "report": None}

    if rr.intent == "help":
        help_text = router.format_help()
        draft = answer_draft._pack(
            status="ok",
            intent="help",
            tickers=[],
            answer=help_text + "\n\nPrefer: `finance-skills ask \"<question>\"` for a full answer.",
            report=None,
        )
        return {**base, **draft, "report": None}

    if rr.intent == "learn":
        concept = answer_draft.concept_key_from_query(query)
        if concept is None and rr.matched_terms:
            concept = answer_draft.concept_key_from_query(" ".join(rr.matched_terms))
        text = learn.explain(concept) if concept else None
        if text is None:
            # Fall back to first known concept list message
            text = learn.explain("rule40") or "See: finance-skills learn list"
            concept = concept or "rule40"
        draft = answer_draft.draft_learn(text, concept=concept)
        return {**base, **draft, "report": None}

    if rr.needs_clarification:
        draft = answer_draft.draft_clarify(
            rr.clarification_question or "Which public ticker should I analyze?",
            intent=rr.intent,
            tickers=rr.tickers,
        )
        return {**base, **draft, "report": None}

    intent = rr.intent
    tickers = list(rr.tickers)
    report: dict[str, Any] | None = None

    try:
        if intent == "compare":
            if len(tickers) < 2:
                draft = answer_draft.draft_clarify(
                    rr.clarification_question or "Which two (or more) tickers should I compare?",
                    intent=intent,
                    tickers=tickers,
                )
                return {**base, **draft, "report": None}
            report = _run_compare(tickers, use_fixture=use_fixture)
            if report.get("error") and not report.get("rows"):
                draft = answer_draft.draft_error(report["error"], intent=intent, tickers=tickers)
                return {**base, **draft, "report": report}

        elif intent == "framework":
            if not tickers:
                draft = answer_draft.draft_clarify(
                    "Which ticker for the sector framework?",
                    intent=intent,
                    tickers=tickers,
                )
                return {**base, **draft, "report": None}
            report = _run_framework(rr.framework, tickers[0], use_fixture=use_fixture)

        elif intent in _SINGLE or intent == "moat":
            if not tickers:
                draft = answer_draft.draft_clarify(
                    rr.clarification_question or "Which public ticker should I analyze?",
                    intent=intent,
                    tickers=tickers,
                )
                return {**base, **draft, "report": None}
            run_intent = "brief" if intent == "moat" else intent
            if run_intent not in router.BUILDERS:
                run_intent = "brief"
            report = _run_single(run_intent, tickers[0], use_fixture=use_fixture)
            if intent == "moat" and isinstance(report, dict):
                report = dict(report)
                report["verdict"] = (
                    (report.get("verdict") or "")
                    + " Moat is a qualitative lens: use engine numbers as evidence only; "
                    "do not invent a moat score."
                ).strip()

        elif intent == "screen":
            draft = answer_draft.draft_error(
                "Screen requires an explicit ticker list via `screen` CLI; "
                "ask with a single-company or compare question instead.",
                intent=intent,
                tickers=tickers,
            )
            return {**base, **draft, "report": None}

        else:
            # analyze aliases etc.
            if tickers and intent in router.BUILDERS:
                report = _run_single(intent, tickers[0], use_fixture=use_fixture)
            elif tickers:
                report = _run_single("brief", tickers[0], use_fixture=use_fixture)
            else:
                draft = answer_draft.draft_clarify(
                    "Which public ticker should I analyze?",
                    intent=intent,
                    tickers=tickers,
                )
                return {**base, **draft, "report": None}

    except Exception as exc:  # noqa: BLE001 — never crash the agent…
        # …but make an unexpected code error debuggable: print the traceback to
        # stderr and tag the draft with the exception type, so a KeyError/bug is
        # distinguishable from a legitimate "data unavailable".
        traceback.print_exc(file=sys.stderr)
        draft = answer_draft.draft_error(f"{type(exc).__name__}: {exc}", intent=intent, tickers=tickers)
        return {**base, **draft, "report": None}

    if not report:
        draft = answer_draft.draft_error("Empty engine report.", intent=intent, tickers=tickers)
        return {**base, **draft, "report": None}

    if report.get("available") is False and not report.get("rows") and not report.get("engine_report"):
        err = report.get("error") or "Ticker data unavailable."
        draft = answer_draft.draft_error(str(err), intent=intent, tickers=tickers)
        return {**base, **draft, "report": report}

    draft = answer_draft.draft_from_report(
        query=query,
        intent=intent,
        tickers=tickers or report.get("tickers") or ([report.get("ticker")] if report.get("ticker") else []),
        report=report,
        secondary_intents=rr.secondary_intents,
    )
    # Agent-facing: include report under `report` for verification, draft is primary
    return {
        **base,
        **draft,
        "report": report,
    }


def doctor() -> dict[str, Any]:
    """Install / path diagnostics for agents and humans."""
    import importlib.util

    scripts_dir = Path(__file__).resolve().parent
    info: dict[str, Any] = {
        "skill_scripts_dir": str(scripts_dir),
        "colocal_version_file": None,
        "importable_finance_skills": None,
        "importable_version": None,
        "version_mismatch": False,
        "yfinance": False,
        "fixtures": [],
        "sample_ask_ok": False,
        "hints": [],
    }
    # Colocal version
    init_path = scripts_dir / "__init__.py"
    if init_path.is_file():
        text = init_path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith("__version__"):
                info["colocal_version_file"] = line.split("=", 1)[1].strip().strip("\"'")
                break
    try:
        import finance_skills as fs

        info["importable_finance_skills"] = getattr(fs, "__file__", None)
        info["importable_version"] = getattr(fs, "__version__", None)
        if (
            info["colocal_version_file"]
            and info["importable_version"]
            and info["colocal_version_file"] != info["importable_version"]
        ):
            info["version_mismatch"] = True
            info["hints"].append(
                f"Stale install: site-packages is {info['importable_version']} but "
                f"skill scripts are {info['colocal_version_file']}. "
                "Prefer `python3 scripts/ask.py` from the skill dir, or "
                "`pip install -U finance-skills` / editable install from this repo."
            )
    except ImportError:
        info["hints"].append("Package not importable as finance_skills (OK for skill-path-only use).")

    info["yfinance"] = importlib.util.find_spec("yfinance") is not None
    if not info["yfinance"]:
        info["hints"].append("yfinance not installed — live pulls fail; use --fixture or: pip install yfinance")

    fix_dir = scripts_dir.parent / "fixtures"
    if not fix_dir.is_dir():
        fix_dir = scripts_dir / "fixtures"
    # fixtures live next to package data (guarded like the module's top imports,
    # so this doesn't rely on sibling modules polluting sys.path when installed)
    if __package__:
        from finance_skills.data import load_fixture
    else:
        from data import load_fixture

    for t in ("CRWV", "NBIS"):
        try:
            f = load_fixture(t)
            info["fixtures"].append({"ticker": t, "available": f.available})
        except Exception as exc:  # noqa: BLE001
            info["fixtures"].append({"ticker": t, "error": str(exc)})

    try:
        sample = run_ask("is nbis a buy?", use_fixture=True)
        info["sample_ask_ok"] = sample.get("status") == "ok" and bool(sample.get("answer_draft"))
        info["sample_intent"] = sample.get("intent")
        info["sample_tickers"] = sample.get("tickers")
        if not info["sample_ask_ok"]:
            info["hints"].append(f"sample ask failed: status={sample.get('status')}")
    except Exception as exc:  # noqa: BLE001
        info["hints"].append(f"sample ask error: {exc}")

    if not info["hints"]:
        info["hints"].append("OK — use: python3 scripts/ask.py \"is CRWV a buy?\" --fixture")
    return info


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv or argv[0] in ("-h", "--help"):
        print(
            "usage: python scripts/ask.py \"<question>\" [--fixture] [--json]\n"
            "       python scripts/ask.py doctor [--json]\n"
            "\n"
            "One-shot: route → engine → answer_draft. Agents should send answer_draft."
        )
        return 0

    if argv[0].lower() == "doctor":
        as_json = "--json" in argv
        info = doctor()
        if as_json:
            print(json.dumps(info, indent=2))
        else:
            print("finance-skills doctor")
            for k, v in info.items():
                if k == "hints":
                    continue
                print(f"  {k}: {v}")
            print("hints:")
            for h in info.get("hints") or []:
                print(f"  - {h}")
        return 0 if info.get("sample_ask_ok") else 1

    flags = {a for a in argv if a.startswith("--")}
    query_parts = [a for a in argv if not a.startswith("--")]
    query = " ".join(query_parts).strip()
    if not query:
        print("usage: python scripts/ask.py \"<question>\" [--fixture] [--json]", file=sys.stderr)
        return 2

    use_fixture = "--fixture" in flags
    as_json = "--json" in flags
    result = run_ask(query, use_fixture=use_fixture)

    if as_json:
        # Compact report optional: full JSON for agents that want evidence
        print(json.dumps(result, indent=2, default=str))
    else:
        # Human / agent-default: print the draft only (what the user should see)
        print(result.get("answer_draft") or "(no draft)")
        if result.get("status") not in ("ok", "learn", "refuse", "clarify"):
            return 1
    # Exit 0 when we produced a user-visible draft (including refuse/clarify)
    return 0 if result.get("answer_draft") else 1


if __name__ == "__main__":
    raise SystemExit(main())
