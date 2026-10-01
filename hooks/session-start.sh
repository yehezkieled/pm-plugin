#!/usr/bin/env bash
# SessionStart: show the board and ready items without model-specific setup.
cat >/dev/null  # hook input is not needed
root="${CLAUDE_PROJECT_DIR:-$PWD}"
plugin="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
if [ ! -f "$root/docs/pm/config.json" ]; then
  # An old pm 0.x board is not read by this version; point at the migration instead of staying silent.
  if ls "$root"/docs/pm/tickets/T*.md >/dev/null 2>&1; then
    echo "This project has a pm 0.x board in docs/pm/tickets that this version does not read. Run /pm:init to move it onto the new board; nothing is deleted without the owner's yes."
  fi
  exit 0
fi
if command -v python3 >/dev/null 2>&1; then
  (cd "$root" && python3 "$plugin/scripts/pm.py" board 2>/dev/null)
  echo
  echo "Before building any item on this board, use the pm:work skill to claim it first. When the user asks to add, track, or \"remember to\" do project work, use the pm:plan skill to put it on this board, not your memory."
else
  echo "Project items are in docs/pm/items/; python3 is needed to render the board."
fi
exit 0
