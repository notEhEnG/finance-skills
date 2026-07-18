"""Immutable project research state, snapshots, and deterministic diffs."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__:
    from finance_skills.context import (
        DEFAULT_CONFIG,
        ContextError,
        discover_project_root,
    )
    from finance_skills.evidence import metric_value
else:
    from context import DEFAULT_CONFIG, ContextError, discover_project_root
    from evidence import metric_value

STATE_SCHEMA_VERSION = "1.0"
_SAFE_TICKER = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,15}$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_child(root: Path, *parts: str) -> Path:
    root = root.resolve()
    candidate = root.joinpath(*parts)
    resolved = candidate.resolve(strict=False)
    if resolved != root and root not in resolved.parents:
        raise ContextError(f"state path escapes project root: {candidate}")
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise ContextError(f"symlink state path is not allowed: {current}")
    return candidate


def _ticker(value: str) -> str:
    ticker = value.strip().upper()
    if not _SAFE_TICKER.fullmatch(ticker):
        raise ContextError(f"invalid ticker: {value!r}")
    return ticker


def _exclusive_write(path: Path, content: str) -> bool:
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(content)
    except FileExistsError:
        return False
    return True


def _append_event(path: Path, content: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(content)


def _stable_report(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _stable_report(item)
            for key, item in value.items()
            if key not in {"retrieved_at", "snapshot_id", "created_at"}
        }
    if isinstance(value, list):
        return [_stable_report(item) for item in value]
    return value


def report_hash(report: dict[str, Any]) -> str:
    canonical = json.dumps(
        _stable_report(report),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _company_dir(root: Path, ticker: str) -> Path:
    return _safe_child(root, ".finance", "companies", _ticker(ticker))


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file() or path.is_symlink():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _history(root: Path, ticker: str) -> list[tuple[Path, dict[str, Any]]]:
    history = _company_dir(root, ticker) / "history"
    if not history.is_dir() or history.is_symlink():
        return []
    snapshots: list[tuple[Path, dict[str, Any]]] = []
    for path in history.iterdir():
        payload = _load_json(path)
        if payload is not None and payload.get("ticker") == _ticker(ticker):
            snapshots.append((path, payload))
    snapshots.sort(key=lambda item: str(item[1].get("created_at") or item[0].name))
    return snapshots


def latest_snapshot(project_root: Path, ticker: str) -> dict[str, Any] | None:
    snapshots = _history(project_root, ticker)
    return snapshots[-1][1] if snapshots else None


def _thesis_markdown(ticker: str, report: dict[str, Any], thesis: dict[str, Any] | None) -> str:
    thesis = thesis or {}
    limitations = thesis.get("limitations") or report.get("warnings") or ["None recorded"]
    paths = [
        "$.derived.revenue_growth_pct",
        "$.derived.fcf_margin_pct",
        "$.derived.share_dilution_pct",
        "$.derived.net_debt",
    ]
    return f"""# {ticker} Research Thesis

## Status
ACTIVE

## Last Reviewed
{_now().date().isoformat()}

## Current Thesis
{thesis.get("thesis") or "Conditional evidence-grounded thesis; review the saved evidence snapshot."}

## Core Assumption
{thesis.get("core_assumption") or "Growth converts into sustainable free cash flow without excessive dilution."}

## Bull Case
{json.dumps(thesis.get("bull_case") or [], ensure_ascii=False)}

## Bear Case
{json.dumps(thesis.get("bear_case") or [], ensure_ascii=False)}

## Valuation Condition
{thesis.get("valuation_condition") or "Operating growth and margins must support the selected comparison basis."}

## Disconfirming Conditions
- Revenue growth materially deteriorates.
- Free-cash-flow conversion fails to improve.
- Dilution prevents improvement in per-share economics.

## Data Limitations
{chr(10).join(f"- {item}" for item in limitations)}

## Evidence Snapshot
{chr(10).join(f"- `{path}`" for path in paths)}
"""


def _watchpoints_markdown(ticker: str, report: dict[str, Any]) -> str:
    growth = metric_value(report, "revenue_growth_pct")
    dilution = metric_value(report, "share_dilution_pct")
    growth_trigger = growth - 10 if growth is not None else 0
    dilution_trigger = max(2.0, dilution or 0)
    created = _now().date().isoformat()
    return f"""# {ticker} Watchpoints

## Open

### WP-001 — Revenue growth durability
- Importance: high
- Trigger: Revenue growth falls below {growth_trigger:.1f}%
- Evidence path: `$.derived.revenue_growth_pct`
- Created: {created}
- Status: open

### WP-002 — Dilution
- Importance: medium
- Trigger: Diluted shares rise more than {dilution_trigger:.1f}% year over year
- Evidence path: `$.derived.share_dilution_pct`
- Created: {created}
- Status: open

### WP-003 — Cash conversion
- Importance: high
- Trigger: Free-cash-flow margin deteriorates materially
- Evidence path: `$.derived.fcf_margin_pct`
- Created: {created}
- Status: open

## Resolved
None
"""


def create_snapshot(
    report: dict[str, Any],
    *,
    project_root: Path | None = None,
    thesis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create an immutable history entry and first-state files."""
    root = discover_project_root(project_root)
    ticker = _ticker(str(report.get("ticker") or ""))
    if report.get("status") in {"provider_error", "engine_error"}:
        return {
            "status": "provider_error",
            "failure": report.get("failure"),
            "ticker": ticker,
        }
    company = _company_dir(root, ticker)
    history = _safe_child(root, ".finance", "companies", ticker, "history")
    history.mkdir(mode=0o755, parents=True, exist_ok=True)
    digest = report_hash(report)
    for path, existing in _history(root, ticker):
        if existing.get("report_hash") == digest:
            return {
                "status": "success",
                "operation": "snapshot_create",
                "ticker": ticker,
                "duplicate": True,
                "snapshot": existing,
                "snapshot_path": str(path),
                "writes": [],
            }

    created = _now()
    data_as_of = str(report.get("data_as_of") or created.date().isoformat())
    period = re.sub(r"[^A-Za-z0-9._-]+", "-", data_as_of).strip("-") or "unknown-period"
    snapshot_id = f"{ticker}-{created.date().isoformat()}-{period}-{digest[7:15]}"
    snapshot = {
        "snapshot_id": snapshot_id,
        "schema_version": STATE_SCHEMA_VERSION,
        "ticker": ticker,
        "created_at": created.isoformat(),
        "data_as_of": report.get("data_as_of"),
        "period_label": data_as_of,
        "data_mode": report.get("data_mode"),
        "report": report,
        "report_hash": digest,
        "source_summary": report.get("source_summary") or {},
        "warnings": report.get("warnings") or [],
    }
    filename = f"{created.date().isoformat()}_{period}_{digest[7:15]}.json"
    snapshot_path = history / filename
    if not _exclusive_write(snapshot_path, json.dumps(snapshot, indent=2, sort_keys=True) + "\n"):
        raise ContextError(f"snapshot path already exists with a different state: {snapshot_path}")

    writes = [str(snapshot_path)]
    thesis_path = company / "thesis.md"
    watchpoints_path = company / "watchpoints.md"
    if _exclusive_write(thesis_path, _thesis_markdown(ticker, report, thesis)):
        writes.append(str(thesis_path))
    if _exclusive_write(watchpoints_path, _watchpoints_markdown(ticker, report)):
        writes.append(str(watchpoints_path))
    latest_path = company / "latest-snapshot.json"
    if _exclusive_write(latest_path, json.dumps(snapshot, indent=2, sort_keys=True) + "\n"):
        writes.append(str(latest_path))

    audit = _safe_child(root, ".finance", "audit-log.jsonl")
    _append_event(
        audit,
        json.dumps(
            {
                "timestamp": created.isoformat(),
                "command": "snapshot create",
                "ticker": ticker,
                "writes": [str(Path(path).relative_to(root)) for path in writes],
                "data_mode": report.get("data_mode"),
                "status": "success",
            },
            sort_keys=True,
        )
        + "\n",
    )
    writes.append(str(audit))
    return {
        "status": "success",
        "operation": "snapshot_create",
        "ticker": ticker,
        "duplicate": False,
        "snapshot": snapshot,
        "snapshot_path": str(snapshot_path),
        "writes": writes,
        "latest_semantics": (
            "Immutable history is authoritative. latest-snapshot.json is creation-only "
            "under the repository no-overwrite policy."
        ),
    }


_DIFF_METRICS: dict[str, tuple[str, bool]] = {
    "revenue_growth_pct": ("percentage_points", True),
    "ebitda_margin_pct": ("percentage_points", True),
    "fcf_margin_pct": ("percentage_points", True),
    "capex_intensity_pct": ("percentage_points", False),
    "share_dilution_pct": ("percentage_points", False),
    "net_debt": ("currency", False),
    "ev_sales": ("multiple", False),
    "ev_ebitda": ("multiple", False),
}


def diff_reports(
    previous: dict[str, Any],
    current: dict[str, Any],
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or DEFAULT_CONFIG
    materiality = config.get("materiality") or {}
    percentage_limit = float(materiality.get("percentage_point_change", 2.0))
    relative_limit = float(materiality.get("relative_change_pct", 10.0))
    changes: list[dict[str, Any]] = []
    score = 0
    for concept, (unit, higher_is_better) in _DIFF_METRICS.items():
        old, new = metric_value(previous, concept), metric_value(current, concept)
        if old is None or new is None:
            continue
        delta = new - old
        relative = abs(delta / old * 100) if old != 0 else None
        material = abs(delta) >= percentage_limit if unit == "percentage_points" else (
            relative is not None and relative >= relative_limit
        )
        if not material:
            continue
        improved = delta > 0 if higher_is_better else delta < 0
        direction = "improved" if improved else "deteriorated"
        score += 1 if improved else -1
        changes.append(
            {
                "metric_path": f"$.derived.{concept}",
                "previous": old,
                "current": new,
                "absolute_change": delta,
                "relative_change_pct": relative,
                "unit": unit,
                "direction": direction,
                "materiality": "high" if abs(delta) >= percentage_limit * 2 else "medium",
            }
        )
    effect = "UNCHANGED"
    if score >= 2:
        effect = "STRENGTHENED"
    elif score <= -3:
        effect = "BROKEN"
    elif score < 0:
        effect = "WEAKENED"
    elif score > 0:
        effect = "STRENGTHENED"
    if not changes and previous.get("data_as_of") != current.get("data_as_of"):
        effect = "INCONCLUSIVE"
    watchpoints = []
    for change in changes:
        mapping = {
            "$.derived.revenue_growth_pct": "WP-001",
            "$.derived.share_dilution_pct": "WP-002",
            "$.derived.fcf_margin_pct": "WP-003",
        }
        watchpoint = mapping.get(change["metric_path"])
        if watchpoint:
            watchpoints.append(
                {
                    "watchpoint_id": watchpoint,
                    "status": "triggered" if change["direction"] == "deteriorated" else "improved",
                    "reason": (
                        f"{change['metric_path']} {change['direction']} by "
                        f"{change['absolute_change']:.2f}."
                    ),
                }
            )
    return {
        "ticker": current.get("ticker"),
        "material_changes": changes,
        "watchpoint_updates": watchpoints,
        "thesis_effect": effect,
        "reason": (
            "Material improvements outweighed deteriorations."
            if score > 0
            else "Material deteriorations outweighed improvements."
            if score < 0
            else "No net material change was detected."
        ),
    }


def refresh(
    current_report: dict[str, Any],
    *,
    project_root: Path | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = discover_project_root(project_root)
    ticker = _ticker(str(current_report.get("ticker") or ""))
    prior = latest_snapshot(root, ticker)
    if prior is None:
        return {
            "status": "no_tracked_state",
            "failure": {
                "error_code": "NO_TRACKED_STATE",
                "message": f"No tracked snapshot exists for {ticker}.",
            },
            "next_command": f"/finance track {ticker}",
        }
    creation = create_snapshot(current_report, project_root=root)
    current_snapshot = creation.get("snapshot")
    if not isinstance(current_snapshot, dict):
        return creation
    change = diff_reports(prior["report"], current_snapshot["report"], config=config)
    change.update(
        {
            "status": "success",
            "workflow": "refresh",
            "previous_snapshot_id": prior.get("snapshot_id"),
            "current_snapshot_id": current_snapshot.get("snapshot_id"),
            "previous_period": prior.get("period_label"),
            "current_period": current_snapshot.get("period_label"),
            "unresolved_questions": [
                "Do the material changes persist in the next comparable period?",
                "Do saved disconfirming conditions require a thesis revision?",
            ],
            "proposed_thesis_update": (
                f"Proposed status: {change['thesis_effect']}. "
                f"{change['reason']} Review before changing the saved thesis."
            ),
        }
    )
    company = _company_dir(root, ticker)
    proposals = company / "thesis-proposals"
    proposals.mkdir(mode=0o755, parents=True, exist_ok=True)
    timestamp = _now()
    proposal_path = proposals / f"{timestamp.strftime('%Y%m%dT%H%M%S%fZ')}.md"
    _exclusive_write(
        proposal_path,
        f"# {ticker} Thesis Update Proposal\n\n"
        f"Created: {timestamp.isoformat()}\n\n"
        f"Status: {change['thesis_effect']}\n\n"
        f"{change['proposed_thesis_update']}\n",
    )
    log_path = company / "refresh-log.md"
    _append_event(
        log_path,
        f"\n## {timestamp.isoformat()} — {change['thesis_effect']}\n\n"
        f"{change['reason']}\n",
    )
    change["writes"] = [*creation.get("writes", []), str(proposal_path), str(log_path)]
    return change


def read_saved_research(
    ticker: str,
    *,
    project_root: Path | None = None,
) -> tuple[str | None, str | None]:
    root = discover_project_root(project_root)
    company = _company_dir(root, ticker)
    thesis = company / "thesis.md"
    watchpoints = company / "watchpoints.md"
    thesis_text = thesis.read_text(encoding="utf-8") if thesis.is_file() and not thesis.is_symlink() else None
    watchpoint_text = (
        watchpoints.read_text(encoding="utf-8")
        if watchpoints.is_file() and not watchpoints.is_symlink()
        else None
    )
    return thesis_text, watchpoint_text
