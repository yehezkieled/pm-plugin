#!/usr/bin/env bash
# SessionStart: show the board and ready items without model-specific setup.
payload="$(cat)"  # the hook input: only used to tell a worker session from the one the person talks to
root="${CLAUDE_PROJECT_DIR:-$PWD}"
plugin="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
if ! command -v python3 >/dev/null 2>&1; then
  [ -f "$root/docs/pm/config.json" ] && echo "Project items are in docs/pm/items/; python3 is needed to render the board."
  exit 0
fi
# This version neither reads nor migrates a pm 0.x board; an earlier version's migration records itself in the config.
if ls "$root"/docs/pm/tickets/T*.md >/dev/null 2>&1 && ! grep -qs '"migrated_from"' "$root/docs/pm/config.json"; then
  echo "This project has a pm 0.x board in docs/pm/tickets, which this pm version does not read. To move it onto the new board, install pm 1.5.1 and run /pm:migrate there."
fi
if [ ! -f "$root/docs/pm/config.json" ]; then
  exit 0
fi
# The one-file architecture map of pm 1.0 is replaced by the System map; point at the conversion once per session.
if [ -f "$root/docs/pm/CODEBASE.md" ] && [ ! -d "$root/docs/pm/map" ]; then
  echo "This project's architecture is in docs/pm/CODEBASE.md, which this pm version replaces with a System map of cards in docs/pm/map/. Run /pm:map to convert it; nothing is deleted without the owner's yes."
fi
# A board from before pm 1.2 has no Where things go table in AGENTS.md; point at init once per session.
if [ -f "$root/AGENTS.md" ] && ! grep -q '^## Where things go' "$root/AGENTS.md"; then
  echo "This project's AGENTS.md has no Where things go table, so new files have no agreed place. Run /pm:init to add one from the project's shape; it moves nothing without the owner's yes."
fi
(cd "$root" && python3 "$plugin/scripts/pm.py" board 2>/dev/null)
echo
# A worker session is told so by how it was started (PM_WORKER), or is one the person opened in an item's copy.
worker="${PM_WORKER:-}"
if [ -z "$worker" ]; then
  worker="$(cd "$root" && printf '%s' "$payload" | python3 "$plugin/scripts/pm.py" worker hook whoami 2>/dev/null)"
fi
if [ -n "$worker" ]; then
  echo "This is the worker session for board item $worker, started for the session the person talks to. Do only that item, as your pm:worker instructions say; report back in your final message, never to the person directly. Every new file goes where AGENTS.md > Where things go says for its kind."
  exit 0
fi
echo "Any project work (code, data, a deliverable) goes through the pm:work skill: it adds the work to this board if it is not there and hands each item to its own worker session (a separate, full Claude Code session in its own copy of the project), which claims it, builds it, has it checked by a separate validator, and finishes it. Do not edit project files in this session yourself. When the user asks to add, track, or \"remember to\" do project work, use the pm:plan skill to put it on this board, not your memory. Every new file goes where AGENTS.md > Where things go says for its kind."
exit 0
