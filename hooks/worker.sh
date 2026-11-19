#!/usr/bin/env bash
# Worker-session hooks, one script for three events (the event name is the first argument):
#   session-start  hand a waiting ticket to a session the person opened in an item's copy
#   stop           save the worker's report at the end of its turn, then listen for its next message
#   permission     note what a worker is asking the person to allow
# In the session that started workers, session-start and stop instead wait for their news (a turn that ended, a
# question, a failed session) and wake that session with it.
# It exits at once in any session of a project that has no worker sessions; scripts/pm.py decides the rest.
event="${1:-}"
common="$(git rev-parse --git-common-dir 2>/dev/null)" || exit 0
[ -d "$common/pm-workers/sessions" ] || exit 0
plugin="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
for python in python3 python py; do
  if command -v "$python" >/dev/null 2>&1; then
    exec "$python" "$plugin/scripts/pm.py" worker hook "$event"
  fi
done
exit 0
