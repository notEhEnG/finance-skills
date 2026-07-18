"""Pure, non-destructive state-schema migrations."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

if __package__:
    from finance_skills.context import DEFAULT_CONFIG
else:
    from context import DEFAULT_CONFIG


def migrate_config(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Return an in-memory schema-1.0 config without changing the source file."""
    migrated = deepcopy(payload)
    changes: list[str] = []
    for key, default in DEFAULT_CONFIG.items():
        if key not in migrated:
            migrated[key] = deepcopy(default)
            changes.append(f"added {key}")
    if migrated.get("schema_version") != "1.0":
        migrated["schema_version"] = "1.0"
        changes.append("set schema_version to 1.0")
    for section in ("staleness", "materiality"):
        defaults = DEFAULT_CONFIG[section]
        current = migrated.get(section)
        if not isinstance(current, dict):
            migrated[section] = deepcopy(defaults)
            changes.append(f"replaced invalid {section} in migrated view")
            continue
        for key, value in defaults.items():
            if key not in current:
                current[key] = value
                changes.append(f"added {section}.{key}")
    provider_defaults = DEFAULT_CONFIG["providers"]
    providers = migrated.get("providers")
    if not isinstance(providers, dict):
        migrated["providers"] = deepcopy(provider_defaults)
        changes.append("replaced invalid providers in migrated view")
    else:
        for provider, defaults in provider_defaults.items():
            current = providers.get(provider)
            if not isinstance(current, dict):
                providers[provider] = deepcopy(defaults)
                changes.append(f"added providers.{provider}")
                continue
            for key, value in defaults.items():
                if key not in current:
                    current[key] = deepcopy(value)
                    changes.append(f"added providers.{provider}.{key}")
    return migrated, changes


def migrate_snapshot(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Normalize legacy snapshot fields in memory; history remains immutable."""
    migrated = deepcopy(payload)
    changes: list[str] = []
    if "schema_version" not in migrated:
        migrated["schema_version"] = "1.0"
        changes.append("added schema_version")
    if "data_mode" not in migrated:
        report = migrated.get("report") or {}
        migrated["data_mode"] = report.get("data_mode", "cached")
        changes.append("derived data_mode")
    if "warnings" not in migrated:
        migrated["warnings"] = list((migrated.get("report") or {}).get("warnings") or [])
        changes.append("derived warnings")
    return migrated, changes
