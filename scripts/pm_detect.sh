#!/usr/bin/env bash
# Looks at a project and prints key=value facts for /pm:init. Read-only.
start="${CLAUDE_PROJECT_DIR:-$PWD}"
has() { command -v "$1" >/dev/null 2>&1 && echo yes || echo no; }

if git -C "$start" rev-parse --show-toplevel >/dev/null 2>&1; then
  git_yes=yes
  root="$(git -C "$start" rev-parse --show-toplevel)"
else
  git_yes=no
  root="$start"
fi
echo "root=$root"
echo "git=$git_yes"

remote=""; branch=""; commits=0; files=0; host=none; fork=unknown
if [ "$git_yes" = yes ]; then
  branch="$(git -C "$root" symbolic-ref --short HEAD 2>/dev/null || git -C "$root" rev-parse --abbrev-ref HEAD 2>/dev/null)"
  remote="$(git -C "$root" remote get-url origin 2>/dev/null || true)"
  if [ -z "$remote" ]; then
    first="$(git -C "$root" remote 2>/dev/null | head -1)"
    [ -n "$first" ] && remote="$(git -C "$root" remote get-url "$first" 2>/dev/null || true)"
  fi
  commits="$(git -C "$root" rev-list --count HEAD 2>/dev/null || echo 0)"
  files="$(git -C "$root" ls-files 2>/dev/null | wc -l | tr -d ' ')"
  case "$remote" in
    *github.com*) host=github ;;
    *gitlab*) host=gitlab ;;
    "") host=none ;;
    *) host=other ;;
  esac
  if [ "$host" = github ] && command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    f="$(cd "$root" && gh repo view --json isFork -q .isFork 2>/dev/null || true)"
    case "$f" in true) fork=yes ;; false) fork=no ;; esac
  fi
else
  files="$(find "$root" -type f -not -path '*/.git/*' -not -path '*/node_modules/*' 2>/dev/null | wc -l | tr -d ' ')"
fi
echo "branch=$branch"
echo "remote=$remote"
echo "host=$host"
echo "fork=$fork"
echo "commits=$commits"
echo "files=$files"

langs=()
checks=()
[ -f "$root/package.json" ] && langs+=(node)
{ [ -f "$root/pyproject.toml" ] || [ -f "$root/setup.py" ] || [ -f "$root/requirements.txt" ]; } && langs+=(python)
[ -f "$root/go.mod" ] && langs+=(go)
[ -f "$root/Cargo.toml" ] && langs+=(rust)
{ [ -f "$root/pom.xml" ] || [ -f "$root/build.gradle" ] || [ -f "$root/build.gradle.kts" ]; } && langs+=(java)
[ -f "$root/composer.json" ] && langs+=(php)
[ -f "$root/Gemfile" ] && langs+=(ruby)
[ -f "$root/Makefile" ] && langs+=(make)
langs_joined="$(IFS=,; echo "${langs[*]}")"
echo "languages=$langs_joined"

if [ -f "$root/Makefile" ] && grep -qE '^test:' "$root/Makefile"; then
  checks+=("make test")
else
  if [ -f "$root/package.json" ]; then
    if grep -q '"lint"' "$root/package.json"; then checks+=("npm run lint && npm test"); else checks+=("npm test"); fi
  fi
  if [ -f "$root/pyproject.toml" ] || [ -f "$root/setup.py" ] || [ -f "$root/requirements.txt" ]; then
    if grep -qs pytest "$root/pyproject.toml" "$root/requirements.txt" "$root/setup.cfg" 2>/dev/null || [ -d "$root/tests" ] && ls "$root/tests"/test_*.py >/dev/null 2>&1; then
      checks+=("python3 -m pytest")
    else
      checks+=("python3 -m unittest")
    fi
  fi
  [ -f "$root/go.mod" ] && checks+=("go test ./...")
  [ -f "$root/Cargo.toml" ] && checks+=("cargo test")
fi
check_guess=""
for c in "${checks[@]}"; do
  if [ -z "$check_guess" ]; then check_guess="$c"; else check_guess="$check_guess && $c"; fi
done
echo "check_guess=$check_guess"

yn() { [ -e "$1" ] && echo yes || echo no; }
echo "readme=$(yn "$root/README.md")"
echo "context_md=$(yn "$root/CONTEXT.md")"
echo "claude_md=$(yn "$root/CLAUDE.md")"
echo "docs_dir=$(yn "$root/docs")"
echo "pm=$(yn "$root/docs/pm/roadmap.md")"

find_planning() {
  cd "$root" || return
  find . -maxdepth 2 \( -path ./.git -o -path ./node_modules -o -path ./docs/pm \) -prune -o -type f \
    \( -iname 'TODO*' -o -iname 'ROADMAP*' -o -iname 'PLAN*' -o -iname 'BACKLOG*' -o -iname 'MILESTONES*' -o -iname 'TASKS*' \) -print 2>/dev/null \
    | sed 's|^\./||'
  # any docs subfolder that holds markdown, apart from docs/pm
  for d in docs/*/; do
    [ -d "$d" ] || continue
    case "$d" in docs/pm/) continue ;; esac
    if ls "$d"*.md >/dev/null 2>&1; then echo "${d}"; fi
  done
}
planning_joined="$(find_planning | sed '/^$/d' | LC_ALL=C sort -u | paste -sd, -)"
echo "planning_docs=$planning_joined"

if [ "$git_yes" = no ]; then flow=direct
elif [ "$host" = none ]; then flow=branch-local
else flow=branch-pr; fi
echo "flow_suggest=$flow"
echo "python3=$(has python3)"
echo "gh=$(has gh)"
