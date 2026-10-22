---
name: help
description: "Explain the pm plugin and list its commands. Use when the user types just \"help\", or asks \"how does pm work\", \"what commands are there\", or how to use this. For a bare \"help\", call this; do not answer from memory. Not for project progress (use status)."
---

# /pm:help

```text
/pm:init             Set up the board and a small AGENTS.md catalog
/pm:plan <request>   Record a request verbatim, with what it touches
/pm:work [item-id]   Claim first, build, verify, then update notes
/pm:status           Show owners, waiting items, and what's ready
/pm:map [area]       Map the code as cards: what a change hits
/pm:migrate          Move an existing task system onto the board
/pm:help             Show this guide
```

One flow, structured with ICM (Interpretable Context Methodology): the root `AGENTS.md` is a small catalog that routes, facts live in the file that owns them, every working folder's `CONTEXT.md` is its contract (Inputs, Process, Outputs, Verify, Human check), and an item names the cards or stages it touches so `/pm:work` loads only those. An ordinary project gets the light parts and an optional System map in `docs/pm/map/`; a workflow being built gets numbered stages inside a skill folder, packageable as a Claude skill. The method and its credit are in `${CLAUDE_PLUGIN_ROOT}/icm/README.md`.

Each item is one file in `docs/pm/items/`, the only board state stored in git. `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm.py" board` renders In flight, Queued, Waiting, and the latest ten Done items from those files; `next` shows queued items with completed dependencies. A hold keeps an item in Waiting, still owned by any claimer, until the decision is resolved. `pm.py walk` runs the walk test's mechanical checks, `pm.py index` rebuilds the map's card index, `pm.py refs` checks what points at a file before it moves, and `pm.py correct` records a correction so the third of one kind suggests fixing the source. `docs/manual.md` is the setup and migration manual. See the README for GitHub mirror behavior and its publication disclosure.

## Reply

Print the guide as is, then read `${CLAUDE_PLUGIN_ROOT}/docs/placement.md` and print it too, then stop.
