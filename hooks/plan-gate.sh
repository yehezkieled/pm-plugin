#!/bin/bash
# PreToolUse hook (Edit|Write|MultiEdit|NotebookEdit|Bash).
# On a ticket branch (txxx-slug) it blocks code edits until the ticket is grilled (ready: yes) and its "## Plan" is written,
# and, for a "plan: required" ticket, until that plan carries "approved: yes".
# While the ticket says "tests: frozen" (a bug fix in progress) test files are not edited either.
# Ticket files, docs/pm, CONTEXT.md and markdown are always allowed. Exit 2 blocks the call; the message goes to the agent.
input=$(cat)
have_py=0; command -v python3 >/dev/null 2>&1 && have_py=1

field() {
  if [ "$have_py" = 1 ]; then
    printf '%s' "$input" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    d = {}
for k in sys.argv[1].split("."):
    d = d.get(k, {}) if isinstance(d, dict) else {}
print(d if isinstance(d, str) else "")' "$1" 2>/dev/null
  else
    printf '%s' "$input" | grep -o "\"${1##*.}\"[[:space:]]*:[[:space:]]*\"[^\"]*\"" | head -1 | sed 's/^[^:]*:[[:space:]]*"//; s/"$//'
  fi
}

tool=$(field tool_name)
cwd=$(field cwd); [ -z "$cwd" ] && cwd=$PWD
root=$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null) || exit 0
[ -d "$root/docs/pm/tickets" ] || exit 0
branch=$(git -C "$cwd" rev-parse --abbrev-ref HEAD 2>/dev/null) || exit 0
tid=$(printf '%s' "$branch" | grep -oE '^[tT][0-9]{3}' | tr t T)
[ -z "$tid" ] && exit 0
ticket=$(ls "$root/docs/pm/tickets/$tid"-*.md 2>/dev/null | head -1)
[ -z "$ticket" ] && exit 0

# a ticket claimed by a routine (owner routine-*) is never merged by that routine
if [ "$tool" = Bash ]; then
  cmd=$(field tool_input.command)
  if printf '%s' "$cmd" | grep -qE '(^|[;&|[:space:]])(git merge|gh pr merge)([[:space:]]|$)' && grep -qE '^owner:[[:space:]]*routine' "$ticket"; then
    echo "pm: $tid is claimed by a routine ($(grep -E '^owner:' "$ticket" | head -1 | sed 's/^owner:[[:space:]]*//')). Routine runs never merge: set status=review, leave the branch or PR for a person, and stop." >&2
    exit 2
  fi
fi

frozen=0; grep -qE '^tests:[[:space:]]*frozen' "$ticket" && frozen=1
routine_owner=0; grep -qE '^owner:[[:space:]]*routine' "$ticket" && routine_owner=1

# a routine never lifts a test freeze
if [ "$tool" = Bash ] && [ "$routine_owner" = 1 ] && printf '%s' "$cmd" | grep -qE 'unfreeze|tests=open'; then
  echo "pm: $tid is claimed by a routine, and a routine never lifts a test freeze. Write why the test looks wrong under ## Notes, set status=review, and stop." >&2
  exit 2
fi

# is this a test file? (relative to cwd or absolute)
test_path() {
  p=$1
  case "$p" in
    */tests/*|*/test/*|*/__tests__/*|*/spec/*|tests/*|test/*|__tests__/*|spec/*) return 0 ;;
  esac
  b=${p##*/}
  case "$b" in
    test_*.py|*_test.py|*_test.go|*_test.rs|*.test.js|*.test.jsx|*.test.ts|*.test.tsx|*.test.mjs|*.spec.js|*.spec.jsx|*.spec.ts|*.spec.tsx|*_spec.rb|*.spec.rb|*Test.java|*Tests.cs|conftest.py) return 0 ;;
  esac
  return 1
}
freeze_block() {
  echo "pm: $tid has tests: frozen (a bug fix in progress), so test files are not edited while the fix is written. If the test itself is wrong, say why and ask the user; on a yes run \`pm.py unfreeze $tid --reason \"...\"\`. A headless or routine run stops here and writes the reason under ## Notes." >&2
  exit 2
}

# is this a docs path? (relative to cwd or absolute)
docs_path() {
  p=$1
  case "$p" in /*) ;; *) p="$cwd/$p" ;; esac
  case "$p" in
    "$root"/docs/*|"$root"/CONTEXT.md|*.md|*.txt) return 0 ;;
  esac
  return 1
}

edits_code=0
case "$tool" in
  Edit|Write|MultiEdit|NotebookEdit)
    path=$(field tool_input.file_path)
    [ -z "$path" ] && path=$(field tool_input.notebook_path)
    if [ -n "$path" ] && ! docs_path "$path"; then
      edits_code=1
      [ "$frozen" = 1 ] && test_path "$path" && freeze_block
    fi
    ;;
  Bash)
    cmd=$(field tool_input.command)
    # drop harmless redirections, then look at what a write would target
    stripped=$(printf '%s' "$cmd" | sed -E 's/[0-9]*>&[0-9]+//g; s/[0-9]*&?>+[[:space:]]*\/dev\/null//g')
    targets=$(printf '%s' "$stripped" | grep -oE '(>>?|\btee( -a)?|\bsed -i([^ ]*)?( -e)?( '"'"'[^'"'"']*'"'"'| "[^"]*"| [^ ]+)?)[[:space:]]*[^[:space:]|;&]+' | sed -E 's/^(>>?|tee( -a)?|sed -i[^ ]*( -e)?( '"'"'[^'"'"']*'"'"'| "[^"]*"| [^ ]+)?)[[:space:]]*//')
    for t in $targets; do
      case "$t" in "'"*|'"'*) continue ;; esac
      if ! docs_path "$t"; then
        edits_code=1
        [ "$frozen" = 1 ] && test_path "$t" && freeze_block
      fi
    done
    ;;
  *) exit 0 ;;
esac
[ "$edits_code" = 1 ] || exit 0

if grep -qE '^ready:[[:space:]]*no' "$ticket"; then
  echo "pm: $tid is not grilled yet (ready: no), so its What, Why and Acceptance are not settled. Run /pm:grill $tid with the user first; do not edit code on this ticket until it says ready: yes." >&2
  exit 2
fi
approach=$(sed -n '/^## Plan/,/^## /p' "$ticket" | grep -E '^Approach:' | head -1 | sed 's/^Approach:[[:space:]]*//')
if [ -z "$approach" ]; then
  echo "pm: $tid has no plan yet. Write the ticket's ## Plan section first (Approach, Touches, Tests first, Decisions to record, approved), then edit code." >&2
  exit 2
fi
if grep -qE '^plan:[[:space:]]*required' "$ticket" && ! grep -qE '^approved:[[:space:]]*yes' "$ticket"; then
  echo "pm: $tid is plan: required and its plan is not approved. A person approves it in this session (plan mode, or a question to the user). Until then do not edit code: stop and say the ticket waits for plan approval." >&2
  exit 2
fi
exit 0
