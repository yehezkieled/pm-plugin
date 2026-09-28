#!/usr/bin/env bash
# SessionStart: show the board and ready items without model-specific setup.
cat >/dev/null  # hook input is not needed
root="${CLAUDE_PROJECT_DIR:-$PWD}"
[ -f "$root/docs/pm/BOARD.md" ] || exit 0
plugin="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
if command -v python3 >/dev/null 2>&1; then
  (cd "$root" && python3 "$plugin/scripts/pm.py" board 2>/dev/null)
else
  cat "$root/docs/pm/BOARD.md"
  echo "Run /pm:status for dependency-aware Ready next items."
fi
exit 0
