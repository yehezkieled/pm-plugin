#!/usr/bin/env bash
# Prints key=value lines about the tools the pm plugin can use in this project.
root="${CLAUDE_PROJECT_DIR:-$PWD}"
has() { command -v "$1" >/dev/null 2>&1 && echo yes || echo no; }
echo "root=$root"
echo "python3=$(has python3)"
echo "git=$(has git)"
echo "gh=$(has gh)"
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then echo "gh_auth=yes"; else echo "gh_auth=no"; fi
if [ -f "$root/docs/pm/roadmap.md" ]; then echo "pm=yes"; else echo "pm=no"; fi
