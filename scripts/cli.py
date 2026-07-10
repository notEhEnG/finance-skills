"""Shared CLI plumbing for single-ticker verbs.

Every Core verb's `main` should use `run_single_ticker` (or `load_for_cli`
directly for multi-arg tools) so ticker validation, fixture loading, JSON flags,
and exit codes cannot drift between doors.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any

if __package__:
    from finance_skills.data import load_for_cli
else:
    from data import load_for_cli

Builder = Callable[..., Any]


def parse_argv(argv: list[str]) -> tuple[list[str], set[str]]:
    """Split positional args from `--flags` (including `--name=value` forms)."""
    args = [a for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}
    return args, flags


def flag_value(flags: set[str], name: str, default: str) -> str:
    """Read `--name=value` from a flags set; return default if absent."""
    prefix = f"--{name}="
    for fl in flags:
        if fl.startswith(prefix):
            return fl.split("=", 1)[1]
    return default


def has_flag(flags: set[str], name: str) -> bool:
    """True if `--name` or `--name=…` is present."""
    if f"--{name}" in flags:
        return True
    prefix = f"--{name}="
    return any(fl.startswith(prefix) for fl in flags)


def run_single_ticker(
    argv: list[str],
    *,
    usage: str,
    build: Builder,
    pass_flags: bool = False,
) -> int:
    """Standard single-ticker CLI: load → build → print → exit code by availability.

    When `pass_flags=True`, calls `build(f, as_json, flags=flags)` so verbs can
    honor `--style=…`, `--explain`, etc. without reimplementing argv parsing.
    """
    args, flags = parse_argv(argv)
    if not args:
        print(usage, file=sys.stderr)
        return 2

    f = load_for_cli(args[0], use_fixture="--fixture" in flags)
    as_json = "--json" in flags
    if pass_flags:
        report = build(f, as_json, flags=flags)
    else:
        report = build(f, as_json)
    print(json.dumps(report, indent=2) if as_json else report)
    return 0 if f.available else 1
