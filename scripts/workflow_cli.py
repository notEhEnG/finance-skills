"""Exact CLI for the redesigned `/finance` workflows."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

if __package__:
    from finance_skills import context, provider_orchestrator, state, workflows
    from finance_skills.data import normalize_ticker
else:
    import context
    import provider_orchestrator
    import state
    import workflows
    from data import normalize_ticker

COMMANDS = frozenset(
    {
        "init",
        "screen",
        "underwrite",
        "audit",
        "compare",
        "challenge",
        "stress",
        "track",
        "refresh",
        "snapshot",
        "diff",
        "explain",
    }
)


def _single_report(
    ticker: str,
    *,
    fixture: bool,
    include_estimates: bool = False,
) -> dict[str, Any]:
    return provider_orchestrator.build_reconciled_report(
        normalize_ticker(ticker),
        use_fixture=fixture,
        include_estimates=include_estimates,
    )


def _format_output(payload: dict[str, Any], output_format: str) -> str:
    if output_format == "json":
        return json.dumps(payload, indent=2, sort_keys=True)
    workflow = payload.get("workflow") or payload.get("operation") or "finance"
    status = payload.get("status")
    subject = payload.get("ticker") or ", ".join(payload.get("tickers") or [])
    headline = (
        payload.get("bottom_line")
        or payload.get("thesis")
        or payload.get("audit_conclusion")
        or payload.get("conditional_conclusion")
        or (payload.get("failure") or {}).get("message")
        or ""
    )
    return f"{workflow}: {subject} [{status}]\n{headline}".strip()


def _exit_code(payload: dict[str, Any]) -> int:
    return 0 if payload.get("status") in {"success", "partial"} else 1


def _add_common(parser: argparse.ArgumentParser, *, ticker: bool = False) -> None:
    if ticker:
        parser.add_argument("--ticker", required=True)
    parser.add_argument("--fixture", action="store_true")
    parser.add_argument("--include-estimates", action="store_true")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    parser.add_argument("--json", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="finance")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init")
    init.add_argument("--format", choices=("json", "text"), default="text")
    init.add_argument("--json", action="store_true")

    for name in ("screen", "underwrite", "audit", "challenge", "track", "refresh", "diff"):
        _add_common(subparsers.add_parser(name), ticker=True)

    compare = subparsers.add_parser("compare")
    compare.add_argument("--tickers", nargs="+", required=True)
    compare.add_argument("--fixture", action="store_true")
    compare.add_argument("--include-estimates", action="store_true")
    compare.add_argument("--format", choices=("json", "text"), default="text")
    compare.add_argument("--json", action="store_true")

    stress = subparsers.add_parser("stress")
    _add_common(stress, ticker=True)
    stress.add_argument("--assumptions", required=True)

    snapshot = subparsers.add_parser("snapshot")
    snapshot.add_argument("action", choices=("create",))
    _add_common(snapshot, ticker=True)

    explain = subparsers.add_parser("explain")
    explain.add_argument("--topic", required=True)
    explain.add_argument("--format", choices=("json", "text"), default="text")
    explain.add_argument("--json", action="store_true")
    return parser


def run(args: argparse.Namespace) -> dict[str, Any]:
    command = args.command
    if command == "init":
        return context.initialize_project()
    if command == "explain":
        return workflows.explain(args.topic)
    if command == "compare":
        reports = [
            _single_report(
                ticker,
                fixture=args.fixture,
                include_estimates=args.include_estimates,
            )
            for ticker in args.tickers
        ]
        failures = [
            report for report in reports if report.get("status") == "provider_error"
        ]
        if failures:
            return {
                "workflow": "compare",
                "status": "provider_error",
                "failure": {
                    "error_code": "PROVIDER_ERROR",
                    "message": "One or more companies have unavailable data.",
                    "reports": failures,
                },
            }
        return workflows.compare(reports)

    report = _single_report(
        args.ticker,
        fixture=args.fixture,
        include_estimates=args.include_estimates,
    )
    if command == "screen":
        return workflows.screen(report)
    if command == "underwrite":
        return workflows.underwrite(report)
    if command == "audit":
        return workflows.audit(report)
    if command == "challenge":
        thesis, watchpoints = state.read_saved_research(args.ticker)
        return workflows.challenge(report, saved_thesis=thesis, saved_watchpoints=watchpoints)
    if command == "stress":
        try:
            assumptions = json.loads(args.assumptions)
        except json.JSONDecodeError as exc:
            return {
                "workflow": "stress",
                "status": "unsupported_analysis",
                "failure": {
                    "error_code": "INVALID_ARGUMENT",
                    "message": f"Assumptions must be valid JSON: {exc}",
                },
            }
        if not isinstance(assumptions, dict):
            return {
                "workflow": "stress",
                "status": "unsupported_analysis",
                "failure": {
                    "error_code": "INVALID_ARGUMENT",
                    "message": "Assumptions JSON must be an object.",
                },
            }
        return workflows.stress(report, assumptions)
    if command in {"track", "snapshot"}:
        thesis = workflows.underwrite(report)
        return state.create_snapshot(report, thesis=thesis)
    if command in {"refresh", "diff"}:
        return state.refresh(report)
    return {
        "status": "engine_error",
        "failure": {
            "error_code": "ENGINE_ERROR",
            "message": f"Unsupported command: {command}",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        payload = run(args)
    except (ValueError, OSError, context.ContextError) as exc:
        payload = {
            "status": "engine_error",
            "failure": {
                "error_code": "ENGINE_ERROR",
                "message": str(exc),
            },
        }
        output_format = "json" if argv and ("--json" in argv or "json" in argv) else "text"
        print(_format_output(payload, output_format))
        return 1
    output_format = "json" if args.json else args.format
    print(_format_output(payload, output_format))
    return _exit_code(payload)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
