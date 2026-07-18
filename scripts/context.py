"""Project research context discovery and safe initialization.

This module implements the first persistent-workspace slice from the redesign:

    python3 -m finance_skills context --format json
    python3 -m finance_skills context init --format json

Initialization is deliberately creation-only. Existing research files are read
and reported as preserved; they are never truncated or overwritten.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"

DEFAULT_CONFIG: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "default_currency": "USD",
    "default_depth": "standard",
    "source_priority": [
        "filing",
        "investor_relations",
        "market_data",
    ],
    "staleness": {
        "market_price_hours": 24,
        "fundamentals_days": 120,
        "tracked_snapshot_days": 100,
    },
    "materiality": {
        "percentage_point_change": 2.0,
        "relative_change_pct": 10.0,
        "share_count_change_pct": 2.0,
    },
    "providers": {
        "filings": {
            "enabled": True,
            "sec_user_agent_env": "FINANCE_SEC_USER_AGENT",
            "cik_by_ticker": {},
        },
        "investor_relations": {"enabled": True},
        "market_data": {"enabled": True},
        "estimates": {"enabled": False},
    },
}

RESEARCH_TEMPLATE = """# Research Context

## Universe
US public equities

## Reporting Currency
USD

## Preferred Sources
1. Regulatory filings
2. Company investor relations
3. Approved market-data provider

## Research Style
Fundamentals-first, growth at a reasonable price

## Default Analysis Depth
standard

## Priority Dimensions
- Revenue durability
- Free-cash-flow conversion
- Dilution
- Balance-sheet risk
- Capital intensity
- Valuation relative to growth and margins

## Exclusions
- Personalized buy/sell instructions
- Portfolio allocation
- Unverified social-media claims
- Automatic price targets
"""


class ContextError(RuntimeError):
    """A typed project-context or initialization failure."""


def discover_project_root(start: Path | None = None) -> Path:
    """Return the nearest project-like directory at or above ``start``."""
    current = (start or Path.cwd()).resolve()
    if not current.is_dir():
        raise ContextError(f"project root is not a directory: {current}")
    if (current / "RESEARCH.md").exists() or (current / ".finance").exists():
        return current
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists() or (candidate / "pyproject.toml").exists():
            return candidate
    return current


def _safe_child(root: Path, relative: str) -> Path:
    root = root.resolve()
    candidate = root / relative
    resolved = candidate.resolve(strict=False)
    if resolved != root and root not in resolved.parents:
        raise ContextError(f"path escapes project root: {candidate}")
    if candidate.is_symlink():
        raise ContextError(f"symlink state path is not allowed: {candidate}")
    return candidate


def _load_config(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return dict(DEFAULT_CONFIG), "missing"
    if not path.is_file() or path.is_symlink():
        return dict(DEFAULT_CONFIG), "invalid"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULT_CONFIG), "malformed"
    if not isinstance(value, dict):
        return dict(DEFAULT_CONFIG), "malformed"
    return value, "loaded"


def load_project_config(
    project_root: Path | None = None,
) -> tuple[Path, dict[str, Any], str]:
    """Return the discovered root and non-sensitive project configuration."""
    root = discover_project_root(project_root)
    config_path = _safe_child(root, ".finance/config.json")
    config, status = _load_config(config_path)
    merged = dict(DEFAULT_CONFIG)
    merged.update(config)
    default_providers = DEFAULT_CONFIG["providers"]
    configured_providers = config.get("providers")
    if isinstance(default_providers, dict):
        providers = {
            name: dict(settings) if isinstance(settings, dict) else settings
            for name, settings in default_providers.items()
        }
        if isinstance(configured_providers, dict):
            for name, settings in configured_providers.items():
                if isinstance(settings, dict) and isinstance(providers.get(name), dict):
                    providers[name].update(settings)
                else:
                    providers[name] = settings
        merged["providers"] = providers
    return root, merged, status


def safe_project_path(root: Path, relative: str) -> Path:
    """Expose the project-root confinement check to provider adapters."""
    return _safe_child(root, relative)


def _snapshot_summary(company_dir: Path) -> tuple[str | None, int | None]:
    candidates: list[Path] = []
    latest = company_dir / "latest-snapshot.json"
    if latest.is_file() and not latest.is_symlink():
        candidates.append(latest)
    history = company_dir / "history"
    if history.is_dir() and not history.is_symlink():
        candidates.extend(
            path
            for path in history.iterdir()
            if path.is_file() and not path.is_symlink() and path.suffix == ".json"
        )

    snapshots: list[tuple[str, dict[str, Any]]] = []
    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            sort_key = str(payload.get("created_at") or payload.get("data_as_of") or path.name)
            snapshots.append((sort_key, payload))
    if not snapshots:
        return None, None

    payload = max(snapshots, key=lambda item: item[0])[1]
    period = payload.get("period_label") or payload.get("data_as_of")
    age_source = payload.get("created_at") or payload.get("data_as_of")
    if not isinstance(age_source, str):
        return str(period) if period else None, None
    try:
        parsed = datetime.fromisoformat(age_source.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            parsed = date.fromisoformat(age_source[:10])
        except ValueError:
            return str(period) if period else None, None
    return str(period) if period else None, max((date.today() - parsed).days, 0)


def _open_watchpoints(company_dir: Path) -> int:
    path = company_dir / "watchpoints.md"
    if not path.is_file() or path.is_symlink():
        return 0
    try:
        content = path.read_text(encoding="utf-8").lower()
    except OSError:
        return 0
    return content.count("- status: open")


def _tracked_companies(root: Path) -> dict[str, dict[str, Any]]:
    companies_root = _safe_child(root, ".finance/companies")
    if not companies_root.is_dir() or companies_root.is_symlink():
        return {}
    companies: dict[str, dict[str, Any]] = {}
    for company_dir in sorted(companies_root.iterdir(), key=lambda path: path.name):
        if not company_dir.is_dir() or company_dir.is_symlink():
            continue
        period, age_days = _snapshot_summary(company_dir)
        companies[company_dir.name.upper()] = {
            "latest_snapshot_period": period,
            "snapshot_age_days": age_days,
            "open_watchpoints": _open_watchpoints(company_dir),
        }
    return companies


def _provider_status() -> dict[str, str]:
    try:
        market_data = "healthy" if importlib.util.find_spec("yfinance") else "unavailable"
    except (ImportError, ValueError):
        market_data = "unavailable"
    return {
        "market_data": market_data,
        "filing_data": "adapter_available",
        "fixture_data": "available",
    }


def _recommendations(
    *,
    research_exists: bool,
    config_status: str,
    companies: dict[str, dict[str, Any]],
    config: dict[str, Any],
) -> list[dict[str, str]]:
    recommendations: list[dict[str, str]] = []
    if not research_exists or config_status == "missing":
        recommendations.append(
            {
                "command": "/finance init",
                "reason": "Project research context has not been initialized.",
            }
        )

    raw_staleness = config.get("staleness")
    staleness = raw_staleness if isinstance(raw_staleness, dict) else {}
    limit = staleness.get("tracked_snapshot_days", 100)
    if not isinstance(limit, (int, float)):
        limit = 100
    for ticker, summary in companies.items():
        age = summary.get("snapshot_age_days")
        if isinstance(age, int) and age > limit:
            recommendations.append(
                {
                    "command": f"/finance refresh {ticker}",
                    "reason": f"Saved snapshot is {age} days old (limit: {limit:g}).",
                }
            )
        if summary.get("open_watchpoints"):
            recommendations.append(
                {
                    "command": f"/finance challenge {ticker}",
                    "reason": f"{summary['open_watchpoints']} open watchpoint(s) need review.",
                }
            )

    if not recommendations:
        recommendations.append(
            {
                "command": "/finance screen <ticker>",
                "reason": "Start a scoped, evidence-grounded company assessment.",
            }
        )
    return recommendations[:3]


def build_context(project_root: Path | None = None) -> dict[str, Any]:
    """Build a read-only summary of project finance state."""
    root, config, config_status = load_project_config(project_root)
    research = _safe_child(root, "RESEARCH.md")
    companies = _tracked_companies(root)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "success",
        "project_root": str(root),
        "research_context_exists": research.is_file() and not research.is_symlink(),
        "config_status": config_status,
        "default_currency": config.get("default_currency", "USD"),
        "default_depth": config.get("default_depth", "standard"),
        "tracked_companies": list(companies),
        "companies": companies,
        "provider_status": _provider_status(),
        "recommended_commands": _recommendations(
            research_exists=research.is_file() and not research.is_symlink(),
            config_status=config_status,
            companies=companies,
            config=config,
        ),
    }


def _exclusive_create(path: Path, content: str) -> bool:
    """Create ``path`` once; return False when it already exists."""
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(content)
    except FileExistsError:
        return False
    return True


def initialize_project(project_root: Path | None = None) -> dict[str, Any]:
    """Create non-sensitive research defaults without changing existing files."""
    root = discover_project_root(project_root)
    research = _safe_child(root, "RESEARCH.md")
    finance_dir = _safe_child(root, ".finance")
    config = _safe_child(root, ".finance/config.json")

    for path in (research, config):
        if path.exists() and (not path.is_file() or path.is_symlink()):
            raise ContextError(f"state target is not a regular file: {path}")
    if finance_dir.exists() and (not finance_dir.is_dir() or finance_dir.is_symlink()):
        raise ContextError(f"state directory is unsafe: {finance_dir}")

    finance_dir.mkdir(mode=0o755, parents=True, exist_ok=True)
    research_created = _exclusive_create(research, RESEARCH_TEMPLATE)
    config_created = _exclusive_create(
        config,
        json.dumps(DEFAULT_CONFIG, indent=2, sort_keys=True) + "\n",
    )
    result = build_context(root)
    result.update(
        {
            "operation": "init",
            "files": [
                {
                    "path": str(research),
                    "status": "created" if research_created else "preserved",
                },
                {
                    "path": str(config),
                    "status": "created" if config_created else "preserved",
                },
            ],
            "research_defaults": {
                "universe": "US public equities",
                "reporting_currency": "USD",
                "research_style": "fundamentals-first",
                "depth": "standard",
                "automatic_price_targets": False,
                "personalized_trading_instructions": False,
            },
        }
    )
    return result


def _render_text(payload: dict[str, Any]) -> str:
    lines = [
        f"Project root: {payload.get('project_root')}",
        f"Research context: {'present' if payload.get('research_context_exists') else 'missing'}",
        f"Configuration: {payload.get('config_status')}",
        f"Tracked companies: {', '.join(payload.get('tracked_companies') or []) or 'none'}",
        "",
        "Recommended next actions:",
    ]
    for item in payload.get("recommended_commands") or []:
        lines.append(f"- {item['command']}: {item['reason']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="finance-skills context")
    parser.add_argument("action", nargs="?", choices=("show", "init"), default="show")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    parser.add_argument("--json", action="store_true", help="compatibility alias for --format json")
    args = parser.parse_args(argv)

    try:
        payload = initialize_project() if args.action == "init" else build_context()
    except (ContextError, OSError) as exc:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "status": "engine_error",
            "error_code": "ENGINE_ERROR",
            "error": str(exc),
        }
        print(json.dumps(payload, indent=2) if args.json or args.format == "json" else payload["error"])
        return 1

    print(json.dumps(payload, indent=2) if args.json or args.format == "json" else _render_text(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
