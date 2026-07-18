"""Deterministic evaluation harness for redesigned workflow transcripts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

if __package__:
    from finance_skills.validation import validate_claims, validate_report
else:
    from validation import validate_claims, validate_report


def evaluate_transcript(
    report: dict[str, Any],
    response: dict[str, Any],
) -> dict[str, Any]:
    claims = response.get("claims") or []
    quantitative = [
        claim for claim in claims if claim.get("claim_type") == "quantitative"
    ]
    grounded = [
        claim for claim in quantitative if claim.get("evidence_paths")
    ]
    claim_errors = validate_claims(report, claims)
    report_result = validate_report(
        report,
        expected_ticker=response.get("ticker") or report.get("ticker"),
    )
    material_warnings = [
        item
        for item in report.get("findings") or []
        if item.get("severity") in {"high", "critical"}
    ]
    preserved_ids = set(response.get("preserved_finding_ids") or [])
    limitation_coverage = (
        sum(item.get("rule_id") in preserved_ids for item in material_warnings)
        / len(material_warnings)
        if material_warnings
        else 1.0
    )
    grounding_coverage = len(grounded) / len(quantitative) if quantitative else 1.0
    field_association = 1.0 if report_result["valid"] else 0.0
    workflow_correct = response.get("workflow") in {
        "screen",
        "underwrite",
        "audit",
        "compare",
        "challenge",
        "stress",
        "track",
        "refresh",
        "explain",
    }
    metrics = {
        "grounding_coverage": grounding_coverage,
        "correct_field_association": field_association,
        "limitation_preservation": limitation_coverage,
        "workflow_correctness": 1.0 if workflow_correct else 0.0,
    }
    targets = {
        "grounding_coverage": 0.95,
        "correct_field_association": 0.98,
        "limitation_preservation": 1.0,
        "workflow_correctness": 1.0,
    }
    failures = [
        name for name, target in targets.items() if metrics[name] < target
    ]
    return {
        "passed": not failures and not claim_errors,
        "metrics": metrics,
        "targets": targets,
        "failures": failures,
        "claim_errors": claim_errors,
        "report_errors": report_result["errors"],
    }


def adapter_support_matrix(root: Path) -> list[dict[str, Any]]:
    status = []
    for provider in ("claude", "codex", "cursor", "gemini", "generic"):
        skill = root / "dist" / provider / "SKILL.md"
        content = skill.read_text(encoding="utf-8") if skill.is_file() else ""
        exact_cli = "python3 -m finance_skills" in content
        broad_permission = "Bash(python3 *)" in content or "Bash(python *)" in content
        status.append(
            {
                "agent": provider,
                "router": "supported" if skill.is_file() else "missing",
                "exact_cli": exact_cli,
                "state": "supported" if exact_cli else "pending",
                "reference_loading": "supported" if "reference/" in content else "pending",
                "command_contract": (
                    "passing" if exact_cli and not broad_permission else "failing"
                ),
                "eval": "unpublished",
            }
        )
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report")
    parser.add_argument("--response")
    parser.add_argument("--matrix", action="store_true")
    args = parser.parse_args(argv)
    if args.matrix:
        root = Path(__file__).resolve().parent.parent
        print(json.dumps(adapter_support_matrix(root), indent=2))
        return 0
    if not args.report or not args.response:
        parser.error("--report and --response are required unless --matrix is used")
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    response = json.loads(Path(args.response).read_text(encoding="utf-8"))
    result = evaluate_transcript(report, response)
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
