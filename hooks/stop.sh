#!/usr/bin/env bash
# Stop hook: keep new files in the places AGENTS.md > Where things go names (block once), and warn when code
# changed without a project item detail update.
payload="$(cat)"
root="${CLAUDE_PROJECT_DIR:-$PWD}"
plugin="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
[ -f "$root/docs/pm/config.json" ] || exit 0
git -C "$root" rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
if command -v python3 >/dev/null 2>&1; then
  # stop_hook_active is true when this stop already follows a block: never block twice in a row.
  active="$(printf '%s' "$payload" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("stop_hook_active") is True)' 2>/dev/null)"
  strays="$(cd "$root" && python3 "$plugin/scripts/pm.py" places --paths 2>/dev/null)"
  if [ -n "$strays" ] && [ "$active" != "True" ]; then
    python3 -c 'import json, sys; print(json.dumps({"decision": "block", "reason": "These new files are outside the places in AGENTS.md > Where things go: " + ", ".join(sys.argv[1].splitlines()) + ". Move each to the place for its kind (git mv, then update anything that reads or writes it), or, if it is a new kind of thing, ask the owner once and add a row."}))' "$strays"
    exit 0
  fi
fi
# An untracked directory listed whole is another checkout only when it has a Git worktree's .git entry.
changed="$(git -C "$root" status --porcelain --untracked-files=all 2>/dev/null | while IFS= read -r entry; do
  case "$entry" in
    '?? .claude/worktrees/'*)
      relative="${entry#?? .claude/worktrees/}"
      worktree="${relative%%/*}"
      [ -e "$root/.claude/worktrees/$worktree/.git" ] && continue
      ;;
  esac
  printf '%s\n' "$entry"
done | cut -c4-)"
[ -n "$changed" ] || exit 0
code="$(printf '%s\n' "$changed" | grep -v -E '^(docs/pm/|.*\.(md|txt)$)' \
  | grep -v -E '(^|/)(__pycache__|node_modules|\.pytest_cache|\.mypy_cache|\.ruff_cache|dist|build|target|\.venv|venv|coverage|out)(/|$)' \
  | grep -v -E '\.(pyc|pyo|log|tmp)$' || true)"
item="$(printf '%s\n' "$changed" | grep -E '^docs/pm/items/[^/]+\.md$' || true)"
[ -n "$code" ] && [ -z "$item" ] || exit 0
printf '{"systemMessage":"Code changed without an item detail update. If this work is tracked, rewrite its Current notes, update the map cards it touches, and refresh affected project docs before finishing."}\n'
exit 0
