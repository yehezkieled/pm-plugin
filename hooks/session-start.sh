#!/usr/bin/env bash
# SessionStart: show the board and ready items without model-specific setup.
cat >/dev/null  # hook input is not needed
root="${CLAUDE_PROJECT_DIR:-$PWD}"
[ -f "$root/docs/pm/config.json" ] || exit 0
plugin="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
if command -v python3 >/dev/null 2>&1; then
  (cd "$root" && python3 "$plugin/scripts/pm.py" board 2>/dev/null)
  echo
  echo "Before building any item on this board, use the pm:work skill to claim it first. When the user asks to add, track, or \"remember to\" do project work, use the pm:plan skill to put it on this board, not your memory."
else
  echo "Project items are in docs/pm/items/; python3 is needed to render the board."
fi
exit 0
