---
name: init
description: Set up the pm project board (docs/pm) in this repo, once. Use when the user says "set up pm", "init the board", or "start tracking work" and no board exists yet. Not for adding tasks (use plan).
---

# /pm:init

1. Check the repository root, existing `AGENTS.md` and `CLAUDE.md`, and whether `docs/pm/config.json` already exists. Never replace existing project instructions or an existing board.
2. If the board already exists, run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm.py" board` and report that setup is already present.
3. Otherwise run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm.py" init`. With a Git remote, run it on the up-to-date default branch; it commits `docs/pm/config.json` and pushes it to the shared default branch.
4. If `AGENTS.md` is absent, create a short file with only enduring guidance useful in most coding sessions: read the board before planning work; preserve requester's words in item details; claim an item before code changes; update its current notes and status as work proceeds; point to `/pm:status` and `docs/pm/items/` rather than copying workflow details. If it exists, do not rewrite it; add only a short board pointer if missing and clearly relevant.
5. If `CLAUDE.md` is absent and this project uses Claude Code, create the one-line pointer `@AGENTS.md`. Never replace an existing `CLAUDE.md`.
6. Show the board and explain `/pm:plan`, `/pm:work`, and `/pm:status` in one line each.

Do not create milestones, epics, sample items, schedules, or unrelated docs.

## Reply

Talk in outcomes, not mechanics: plain words, no internal jargon (say "waiting on your decision", not "hold"). The reply must stand alone: lead with the result, then any decision needed. No progress narration. Mark unverified claims `[UNSURE]`. Say whether the board was created or already existed, what was committed or pushed, and the three commands to use next.
