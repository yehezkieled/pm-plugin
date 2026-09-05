#!/usr/bin/env bash
# Stop hook: warn once when code changed but no ticket file did. Never blocks.
input="$(cat)"
root="${CLAUDE_PROJECT_DIR:-$PWD}"
[ -f "$root/docs/pm/roadmap.md" ] || exit 0
git -C "$root" rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
changed="$(git -C "$root" status --porcelain --untracked-files=all 2>/dev/null | cut -c4-)"
[ -n "$changed" ] || exit 0
code="$(printf '%s\n' "$changed" | grep -v '^docs/pm/' | grep -v -E '\.(md|txt)$' \
  | grep -v -E '(^|/)(__pycache__|node_modules|\.pytest_cache|\.mypy_cache|\.ruff_cache|dist|build|target|\.venv|venv|coverage|\.coverage)(/|$)' \
  | grep -v -E '\.(pyc|pyo|log|tmp)$' || true)"
tickets="$(printf '%s\n' "$changed" | grep '^docs/pm/tickets/' || true)"
[ -n "$code" ] && [ -z "$tickets" ] || exit 0

session="$(printf '%s' "$input" | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)"
state_dir="${CLAUDE_PLUGIN_DATA:-${XDG_CACHE_HOME:-$HOME/.cache}/pm-plugin}"
mkdir -p "$state_dir" 2>/dev/null
state="$state_dir/stop-${session:-nosession}"
stamp="$(printf '%s' "$code" | cksum | cut -d' ' -f1)"
if [ -f "$state" ] && [ "$(cat "$state")" = "$stamp" ]; then exit 0; fi
printf '%s' "$stamp" > "$state"

count="$(printf '%s\n' "$code" | grep -c .)"
sample="$(printf '%s\n' "$code" | head -3 | tr -d '"\\' | paste -sd, - | sed 's/,/, /g')"
[ "$count" -gt 3 ] && sample="$sample, +$((count - 3)) more"
printf '{"systemMessage": "pm: code changed but no ticket was updated (%s). If this belongs to a ticket, update its status or notes. If it is new work, run /pm:plan ticket."}\n' "$sample"
exit 0
