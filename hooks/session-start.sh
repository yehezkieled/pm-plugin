#!/usr/bin/env bash
# SessionStart: show the board and ready items without model-specific setup.
cat >/dev/null  # hook input is not needed
root="${CLAUDE_PROJECT_DIR:-$PWD}"
plugin="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
if ! command -v python3 >/dev/null 2>&1; then
  [ -f "$root/docs/pm/config.json" ] && echo "Project items are in docs/pm/items/; python3 is needed to render the board."
  exit 0
fi
# An old pm 0.x board is not read by this version; point at the migration until apply has recorded every ticket.
pending=$(python3 -c 'import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); import pm_migrate; print(len(pm_migrate.unmigrated_tickets(Path(sys.argv[2]))))' "$plugin/scripts" "$root" 2>/dev/null)
if [ "${pending:-0}" -gt 0 ]; then
  if [ -f "$root/docs/pm/config.json" ]; then command="/pm:migrate"; else command="/pm:init"; fi
  echo "This project has a pm 0.x board in docs/pm/tickets with $pending ticket(s) this version does not read yet. Run $command to move them onto the new board; nothing is deleted without the owner's yes."
fi
if [ ! -f "$root/docs/pm/config.json" ]; then
  exit 0
fi
(cd "$root" && python3 "$plugin/scripts/pm.py" board 2>/dev/null)
echo
echo "Before building any item on this board, use the pm:work skill to claim it first. When the user asks to add, track, or \"remember to\" do project work, use the pm:plan skill to put it on this board, not your memory."
exit 0
