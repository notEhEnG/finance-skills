"""Creation-only harness for reproducible, externally executed model studies."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STUDY_VERSION = "0.14.0"
MODES = ("base", "compatibility_skill", "redesigned_skill")
RATING_DIMENSIONS = (
    "usefulness",
    "clarity",
    "evidence_traceability",
    "conditional_reasoning",
    "risk_balance",
    "unsupported_confidence",
)
COMMAND_TEMPLATES: dict[str, dict[str, Any]] = {
    "claude": {
        "availability": "supported",
        "argv": [
            "claude",
            "--print",
            "--tools",
            "",
            "--output-format",
            "json",
            "{prompt}",
        ],
    },
    "codex": {
        "availability": "supported",
        "argv": [
            "codex",
            "exec",
            "--sandbox",
            "read-only",
            "--ask-for-approval",
            "never",
            "--json",
            "{prompt}",
        ],
    },
    "cursor": {
        "availability": "requires_cursor_agent",
        "argv": ["cursor-agent", "--print", "--output-format", "json", "{prompt}"],
    },
    "gemini": {
        "availability": "supported",
        "argv": [
            "gemini",
            "--approval-mode",
            "plan",
            "--output-format",
            "json",
            "--prompt",
            "{prompt}",
        ],
    },
}
_STUDY_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


def load_prompts(path: Path) -> list[dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("study prompts must be a list")
    prompts: list[dict[str, str]] = []
    for item in payload:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("id"), str)
            or not isinstance(item.get("prompt"), str)
        ):
            raise ValueError("each study prompt requires string id and prompt fields")
        prompts.append({"id": item["id"], "prompt": item["prompt"]})
    if len({item["id"] for item in prompts}) != len(prompts):
        raise ValueError("study prompt ids must be unique")
    return prompts


def build_manifest(
    prompts: list[dict[str, str]],
    *,
    study_id: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    if not _STUDY_ID_RE.fullmatch(study_id):
        raise ValueError(f"invalid study id: {study_id!r}")
    cases = [
        {
            "case_id": f"{provider}:{mode}:{prompt['id']}",
            "provider": provider,
            "mode": mode,
            "prompt_id": prompt["id"],
            "prompt": prompt["prompt"],
            "result_status": "unpublished",
        }
        for provider in COMMAND_TEMPLATES
        for mode in MODES
        for prompt in prompts
    ]
    return {
        "schema_version": "1.0",
        "study_version": STUDY_VERSION,
        "study_id": study_id,
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "execution_policy": "external_manual_execution",
        "human_review_status": "pending",
        "command_templates": COMMAND_TEMPLATES,
        "cases": cases,
    }


def randomized_review_packet(
    transcript_records: list[dict[str, Any]],
    *,
    study_id: str,
) -> dict[str, Any]:
    records = [dict(record) for record in transcript_records]
    seed = int(hashlib.sha256(study_id.encode("utf-8")).hexdigest()[:16], 16)
    random.Random(seed).shuffle(records)
    blinded = []
    answer_key = []
    for index, record in enumerate(records, start=1):
        review_id = f"review-{index:04d}"
        blinded.append(
            {
                "review_id": review_id,
                "prompt": record.get("prompt"),
                "response": record.get("response"),
                "rating_dimensions": list(RATING_DIMENSIONS),
            }
        )
        answer_key.append(
            {
                "review_id": review_id,
                "case_id": record.get("case_id"),
                "provider": record.get("provider"),
                "mode": record.get("mode"),
            }
        )
    return {
        "study_id": study_id,
        "review_status": "pending_human_review",
        "blinded_records": blinded,
        "answer_key": answer_key,
    }


def aggregate_human_scores(scores: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, dict[str, list[float]]] = {}
    for score in scores:
        mode = score.get("mode")
        ratings = score.get("ratings")
        if not isinstance(mode, str) or not isinstance(ratings, dict):
            raise ValueError("each score requires mode and ratings")
        bucket = grouped.setdefault(
            mode,
            {dimension: [] for dimension in RATING_DIMENSIONS},
        )
        for dimension in RATING_DIMENSIONS:
            value = ratings.get(dimension)
            if not isinstance(value, (int, float)) or not 1 <= value <= 5:
                raise ValueError(f"{dimension} must be between 1 and 5")
            bucket[dimension].append(float(value))
    aggregates = {
        mode: {
            dimension: sum(values) / len(values)
            for dimension, values in dimensions.items()
            if values
        }
        for mode, dimensions in grouped.items()
    }
    return {
        "review_type": "blinded_human",
        "score_count": len(scores),
        "aggregates": aggregates,
    }


def _exclusive_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def prepare_study(repo_root: Path, study_id: str) -> dict[str, Any]:
    if not _STUDY_ID_RE.fullmatch(study_id):
        raise ValueError(f"invalid study id: {study_id!r}")
    prompts_path = repo_root / "eval" / "prompts.v0.14.0.json"
    prompts = load_prompts(prompts_path)
    study_dir = repo_root / "eval" / "runs" / study_id
    resolved = study_dir.resolve(strict=False)
    runs_root = (repo_root / "eval" / "runs").resolve(strict=False)
    if runs_root not in resolved.parents:
        raise ValueError("study path escapes eval/runs")
    manifest = build_manifest(prompts, study_id=study_id)
    _exclusive_json(study_dir / "manifest.json", manifest)
    return {
        "status": "prepared",
        "study_id": study_id,
        "manifest": str(study_dir / "manifest.json"),
        "case_count": len(manifest["cases"]),
        "external_runs_completed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="finance-study")
    parser.add_argument("command", choices=("prepare", "matrix"))
    parser.add_argument("--study-id")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parent.parent
    if args.command == "matrix":
        print(json.dumps(COMMAND_TEMPLATES, indent=2, sort_keys=True))
        return 0
    if not args.study_id:
        parser.error("--study-id is required for prepare")
    print(json.dumps(prepare_study(root, args.study_id), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
