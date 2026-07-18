"""Allowlisted loader for exactly one workflow reference per request."""

from __future__ import annotations

from pathlib import Path

WORKFLOW_REFERENCES = {
    "init": "init.md",
    "screen": "screen.md",
    "underwrite": "underwrite.md",
    "audit": "audit.md",
    "compare": "compare.md",
    "challenge": "challenge.md",
    "stress": "stress.md",
    "track": "track.md",
    "refresh": "refresh.md",
    "explain": "explain.md",
}

SPECIALISTS = {
    "fundamental_analyst": "fundamental-analyst.md",
    "forensic_accountant": "forensic-accountant.md",
    "valuation_skeptic": "valuation-skeptic.md",
}


def _skill_root() -> Path:
    return Path(__file__).resolve().parent.parent / "skill"


def load_workflow(command: str, *, skill_root: Path | None = None) -> str:
    filename = WORKFLOW_REFERENCES.get(command)
    if filename is None:
        raise ValueError(f"unsupported workflow reference: {command}")
    root = (skill_root or _skill_root()).resolve()
    path = root / "reference" / filename
    resolved = path.resolve(strict=True)
    if resolved.parent != (root / "reference").resolve():
        raise ValueError(f"workflow reference escapes skill root: {path}")
    return resolved.read_text(encoding="utf-8")


def load_specialist(
    name: str,
    *,
    workflow: str,
    skill_root: Path | None = None,
) -> str:
    if workflow != "underwrite":
        raise ValueError("specialists are permitted only for underwrite")
    filename = SPECIALISTS.get(name)
    if filename is None:
        raise ValueError(f"unsupported specialist: {name}")
    root = (skill_root or _skill_root()).resolve()
    path = root / "agents" / filename
    resolved = path.resolve(strict=True)
    if resolved.parent != (root / "agents").resolve():
        raise ValueError(f"specialist reference escapes skill root: {path}")
    return resolved.read_text(encoding="utf-8")
