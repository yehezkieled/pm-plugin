---
name: init
description: Set up the lightweight project board and concise agent instructions in a project. Use when the user asks to initialize or set up pm tracking.
---

# /pm:init

1. Check the repository root, existing `AGENTS.md` and `CLAUDE.md`, and whether `docs/pm/BOARD.md` already exists. Never replace existing project instructions or an existing board.
2. If the board already exists, run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm.py" board` and report that setup is already present.
3. Otherwise run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm.py" init`.
4. If `AGENTS.md` is absent, create a short file with only enduring guidance useful in most coding sessions: read the board before planning work; preserve requester's words in item details; claim an item before code changes; update its current notes and status as work proceeds; point back to `docs/pm/BOARD.md` rather than copying workflow details. If it exists, do not rewrite it; add only a short board pointer if missing and clearly relevant.
5. If `CLAUDE.md` is absent and this project uses Claude Code, create the one-line pointer `@AGENTS.md`. Never replace an existing `CLAUDE.md`.
6. Show the board and explain `/pm:plan`, `/pm:work`, and `/pm:status` in one line each.

Do not create milestones, epics, sample items, schedules, or unrelated docs.
