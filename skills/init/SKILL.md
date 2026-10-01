---
name: init
description: "Set up the pm project board (docs/pm) in this repo. Use when the user says \"set up pm\", \"init the board\", \"start tracking work\", or \"is there a board? if not create one\". Call this first, not status; it checks for an existing board itself. Not for adding tasks (use plan)."
---

# /pm:init

1. Check the repository root, existing `AGENTS.md` and `CLAUDE.md`, and whether `docs/pm/config.json` already exists. Never replace existing project instructions or an existing board.
2. If the board already exists, run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm.py" board` and report that setup is already present; still do step 6.
3. Otherwise run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm.py" init`. With a Git remote, run it on the up-to-date default branch; it commits `docs/pm/config.json` and pushes it to the shared default branch.
4. If `AGENTS.md` is absent, create a short file with only enduring guidance useful in most coding sessions: read the board before planning work; preserve requester's words in item details; claim an item before code changes; update its current notes and status as work proceeds; add one line saying where each kind of knowledge goes, naming `/pm:help` (which prints the placement guide); point to `README.md` for the product overview rather than copying it, and to `/pm:status` and `docs/pm/items/` rather than copying workflow details. Do not copy the placement table into it. Read `${CLAUDE_PLUGIN_ROOT}/docs/placement.md` first; never put private or agent-only context in `README.md`. If it exists, do not rewrite it; add only a short board pointer if missing and clearly relevant.
5. If `CLAUDE.md` is absent and this project uses Claude Code, create the one-line pointer `@AGENTS.md`. Never replace an existing `CLAUDE.md`.
6. Look for a system this project already uses: run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm.py" migrate scan` (it only reads). If it finds one (an old pm board, TODO.md, a tasks folder, Beads, GitHub Issues), tell the owner what it found and follow `/pm:migrate` from its plan step: show the plan and counts, and write items only after the owner's yes. Never delete the old system without that confirmation. Do this on a fresh board too; an empty board next to an unmigrated backlog is the wrong outcome.
7. Show the board and explain `/pm:plan`, `/pm:work`, and `/pm:status` in one line each.

Do not create milestones, epics, sample items, schedules, or unrelated docs.

## Reply

Talk in outcomes, not mechanics: plain words, no internal jargon (say "waiting on your decision", not "hold"). The reply must stand alone: lead with the result, then any decision needed. No progress narration. Mark unverified claims `[UNSURE]`. Say whether the board was created or already existed, what was committed or pushed, whether an existing system was found and where its migration stands, and the three commands to use next.
