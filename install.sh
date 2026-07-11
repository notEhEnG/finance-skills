#!/usr/bin/env bash
#
# Install finance-skills as an agent skill so it can be triggered with
# /finance-skills.
#
# Usage:
#   ./install.sh [claude|antigravity|codex|all] [--dir TARGET_PROJECT]
#
# Run from a clone, or pipe from GitHub:
#   curl -fsSL https://raw.githubusercontent.com/notEhEnG/finance-skills/main/install.sh | bash -s -- claude
#
# It copies the skill (SKILL.md + scripts + references) into the tool's skill
# directory under the target project, so /finance-skills can run the engine.

set -euo pipefail

REPO_URL="https://github.com/notEhEnG/finance-skills.git"
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
CLEANUP=""
if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/SKILL.md" ] && [ -f "$SCRIPT_DIR/scripts/analyze.py" ]; then
  SRC="$SCRIPT_DIR"
else
  echo "Cloning $REPO_URL ..."
  SRC="$(mktemp -d)"; CLEANUP="$SRC"
  git clone --depth 1 "$REPO_URL" "$SRC" >/dev/null 2>&1
fi

copy_into() {
  local dest="$1"; mkdir -p "$dest"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a \
      --exclude '.git' --exclude '.cache' --exclude '__pycache__' --exclude '*.pyc' \
      --exclude '.pytest_cache' --exclude 'overview*.md' --exclude '*-cli.txt' --exclude 'Gap-*.csv' \
      --exclude '.claude' --exclude '.antigravity' --exclude '.codex' \
      --exclude 'dist' --exclude 'build' --exclude '*.egg-info' --exclude '.venv' --exclude 'venv' \
      "$SRC"/ "$dest"/
  else
    cp -R "$SRC"/. "$dest"/
    rm -rf "$dest/.git" "$dest/.cache" "$dest/.pytest_cache" \
      "$dest/.claude" "$dest/.antigravity" "$dest/.codex" \
      "$dest/dist" "$dest/build" "$dest/.venv" "$dest/venv"
    rm -rf "$dest"/*.egg-info
    rm -f "$dest"/overview*.md "$dest"/*-cli.txt "$dest"/Gap-*.csv
    find "$dest" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
    find "$dest" -name '*.pyc' -delete 2>/dev/null || true
  fi
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

# Record installed skill version for doctor / support (before temp clone cleanup)
if [ -f "$SRC/scripts/__init__.py" ]; then
  VER="$(grep -E '^__version__' "$SRC/scripts/__init__.py" | head -1 | cut -d'"' -f2 || true)"
  echo "Skill package version: ${VER:-unknown}"
fi

[ -n "$CLEANUP" ] && rm -rf "$CLEANUP"

cat <<'EOF'

Done. If needed: pip install yfinance
  (optional CLI) pip install -U finance-skills   # keep in sync with skill scripts

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
