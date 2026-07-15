#!/usr/bin/env bash
#
# Install finance-skills as an agent skill so it can be triggered with
# /finance-skills.
#
# Usage:
#   ./install.sh [claude|antigravity|codex|all] [--dir TARGET_PROJECT]
#
# Run from a clone, or pipe from GitHub:
#   curl -fsSL https://raw.githubusercontent.com/notEhEnG/finance-skills/v0.13.0/install.sh | bash -s -- claude
#
# It copies the skill (SKILL.md + scripts + references) into the tool's skill
# directory under the target project, so /finance-skills can run the engine.

set -euo pipefail

REPO_URL="https://github.com/notEhEnG/finance-skills.git"
REPO_REF="${FINANCE_SKILLS_REF:-v0.13.0}"
TOOL="claude"
TARGET_DIR="$PWD"

while [ $# -gt 0 ]; do
  case "$1" in
    claude|antigravity|codex|all) TOOL="$1"; shift ;;
    --dir) TARGET_DIR="${2:?--dir needs a path}"; shift 2 ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" >/dev/null 2>&1 && pwd || true)"
RETAINED_CLONE=""
if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/SKILL.md" ] && [ -f "$SCRIPT_DIR/scripts/analyze.py" ]; then
  SRC="$SCRIPT_DIR"
else
  echo "Cloning $REPO_URL at $REPO_REF ..."
  SRC="$(mktemp -d)"; RETAINED_CLONE="$SRC"
  git clone --depth 1 --branch "$REPO_REF" "$REPO_URL" "$SRC" >/dev/null 2>&1
fi

copy_into() {
  local dest="$1"
  if [ -d "$dest" ] && [ -n "$(find "$dest" -mindepth 1 -print -quit 2>/dev/null)" ]; then
    echo "Refusing to overwrite existing skill directory: $dest" >&2
    echo "Install into a new project/path or preserve the existing directory manually." >&2
    return 1
  fi
  mkdir -p "$dest"
  cp -n "$SRC/SKILL.md" "$SRC/README.md" "$SRC/LICENSE" "$SRC/SECURITY.md" "$dest"/
  mkdir -p "$dest/scripts" "$dest/references" "$dest/docs"
  cp -n "$SRC/scripts/"*.py "$dest/scripts"/
  cp -n "$SRC/references/"*.md "$dest/references"/
  cp -n "$SRC/docs/"*.md "$SRC/docs/"*.json "$SRC/docs/"*.tape \
    "$SRC/docs/"*.gif "$SRC/docs/"*.mp4 "$dest/docs"/
  echo "  Installed skill at: $dest/SKILL.md"
}

install_tool() {
  case "$1" in
    claude)      copy_into "$TARGET_DIR/.claude/skills/finance-skills" ;;
    antigravity) copy_into "$TARGET_DIR/.antigravity/skills/finance-skills" ;;
    codex)       copy_into "${CODEX_SKILLS_DIR:-$TARGET_DIR/.codex/skills}/finance-skills" ;;
    *) echo "Unknown tool: $1" >&2; exit 2 ;;
  esac
}

echo "Installing finance-skills skill (tool: $TOOL) into: $TARGET_DIR"
if [ "$TOOL" = "all" ]; then
  install_tool claude; install_tool antigravity; install_tool codex
else
  install_tool "$TOOL"
fi

# Record installed skill version for doctor / support.
if [ -f "$SRC/scripts/__init__.py" ]; then
  VER="$(grep -E '^__version__' "$SRC/scripts/__init__.py" | head -1 | cut -d'"' -f2 || true)"
  echo "Skill package version: ${VER:-unknown}"
fi

if [ -n "$RETAINED_CLONE" ]; then
  echo "Retained downloaded source at: $RETAINED_CLONE"
fi

cat <<'EOF'

Done. If needed: pip install yfinance
  (optional CLI) pip install finance-skills==0.13.0

Preferred agent command (one shot → report + evidence floor, then agent synthesis):
  python3 scripts/ask.py --json "is NBIS a buy?"
  python3 scripts/ask.py "is CRWV a buy?" --fixture

Slash (agent runs ask, then writes its analyst answer on the report's numbers):
  /finance-skills is NBIS a buy?
  /finance-skills is NVDA overvalued?
  /finance-skills compare AMD and NVDA

Diagnose stale installs:
  python3 scripts/ask.py doctor

Or ask your agent: "install this skill https://github.com/notEhEnG/finance-skills"
EOF
