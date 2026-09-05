#!/usr/bin/env bash
# SessionStart hook: prints one line of pm context when the project has docs/pm.
cat >/dev/null  # hook input is not needed
root="${CLAUDE_PROJECT_DIR:-$PWD}"
[ -f "$root/docs/pm/roadmap.md" ] || exit 0
plugin="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
if command -v python3 >/dev/null 2>&1; then
  line="$(python3 "$plugin/scripts/pm.py" --root "$root" line 2>/dev/null)"
  [ -n "$line" ] && echo "$line"
else
  echo "pm: docs/pm found, python3 missing; the pm skills will read the files by hand."
fi
echo "pm skills: board /pm:status | add or file work /pm:plan | do a ticket /pm:work | find bugs /pm:audit | cheat sheet /pm:help"
exit 0
