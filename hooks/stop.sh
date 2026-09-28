#!/usr/bin/env bash
# Stop hook: warn when code changed without a project item detail update.
input="$(cat)"
root="${CLAUDE_PROJECT_DIR:-$PWD}"
[ -f "$root/docs/pm/BOARD.md" ] || exit 0
git -C "$root" rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
changed="$(git -C "$root" status --porcelain --untracked-files=all 2>/dev/null | cut -c4-)"
[ -n "$changed" ] || exit 0
code="$(printf '%s\n' "$changed" | grep -v -E '^(docs/pm/|.*\.(md|txt)$)' \
  | grep -v -E '(^|/)(__pycache__|node_modules|\.pytest_cache|\.mypy_cache|\.ruff_cache|dist|build|target|\.venv|venv|coverage)(/|$)' \
  | grep -v -E '\.(pyc|pyo|log|tmp)$' || true)"
item="$(printf '%s\n' "$changed" | grep -E '^docs/pm/items/PM-[0-9]+-.*\.md$' || true)"
[ -n "$code" ] && [ -z "$item" ] || exit 0
printf '{"systemMessage":"Code changed without an item detail update. If this work is tracked, rewrite its Current notes and refresh affected project docs before finishing."}\n'
exit 0
