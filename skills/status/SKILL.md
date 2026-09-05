---
name: status
description: Show the project board - milestones, epics, tickets, who is working on what, what is blocked, and what is ready next. Read-only. Use when the user asks where are we, what is the status or progress, what is next, what is blocked, show the board, or wants an overview of the work. Not for doing a ticket (that is pm:work), filing work (pm:plan), or finding bugs (pm:audit).
argument-hint: "[--validate]"
---

# /pm:status

One page, no dates, no guesses about when.

1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm.py" board` and print its output unchanged. If docs/pm is missing, say so and offer /pm:init. If python3 is missing, read `docs/pm/roadmap.md`, the epics, and the tickets and print the same shape by hand: milestone, epics with done counts, tickets with status, priority, owner, PR, and what blocks them.
2. Run `pm.py validate`. When it lists problems, show them under "Needs fixing" (for example a claimed ticket still marked todo, a missing epic, a dependency cycle).
3. Add at most three lines of reading: what is ready to pick up and what waits for a grill (the board's `To grill:` line), what looks stuck (in progress with no PR, proposed changes waiting, review waiting on a merge, a ticket flagged `grilled early`), and the single most useful next command (/pm:work, /pm:grill Txxx when nothing is ready but something is to grill, /pm:plan apply Txxx, /pm:retro when every ticket of the current milestone is done).
4. Run `pm.py backup` every time. On a fork (docs/pm is in `.git/info/exclude`) it copies docs/pm and CONTEXT.md to `${PM_BACKUP_DIR:-$HOME/.pm-backup}/<repo name>/` so the tracking survives a reset, and prints the path: repeat that path in your answer. Otherwise it says no backup is needed. If python3 is missing, do the copy by hand with `cp -r`.

Never turn the board into percentages of a plan against a calendar. The board answers "what is done, what is next, what is stuck".

## Hand-off

This skill only reads. If the user actually asked to do, pick up, or fix a ticket (including "fix it" about a bug ticket), invoke the `pm:work` skill now; do not fix the code from here. If they asked to file, record, or track something, or to apply, accept, or go through the proposed changes on a ticket, invoke `pm:plan`. If they asked to grill, refine, flesh out, or get a ticket ready, invoke `pm:grill`. If they asked to look for bugs or problems in the code, invoke `pm:audit`.
