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
      "$SRC"/ "$dest"/
  else
    cp -R "$SRC"/. "$dest"/
    rm -rf "$dest/.git" "$dest/.cache" "$dest/.pytest_cache"
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

[ -n "$CLEANUP" ] && rm -rf "$CLEANUP"

cat <<'EOF'

Done. If needed: pip install yfinance
Trigger it with:
  /finance-skills analyze Do you think NBIS is a buy?
  /finance-skills is NVDA overvalued?
  /finance-skills compare AMD and NVDA

Or ask your agent: "install this skill https://github.com/notEhEnG/finance-skills"
EOF
