---
name: help
description: "Explain the pm plugin and list its commands. Use when the user types just \"help\", or asks \"how does pm work\", \"what commands are there\", or how to use this. For a bare \"help\", call this; do not answer from memory. Not for project progress (use status)."
---

# /pm:help

```text
/pm:init             Set up the board, the AGENTS.md catalog, and where things go
/pm:plan <request>   Record a request verbatim, with what it touches
/pm:work [item-id]   Any project work: a worker session claims, builds, validates, commits
/pm:status           Show owners, waiting items, and what's ready
/pm:map [area]       Map the code as cards: what a change hits
/pm:help             Show this guide
```

One flow, structured with ICM (Interpretable Context Methodology): the root `AGENTS.md` is a small catalog that routes, its `## Where things go` table says where each kind of file goes (stamped by `/pm:init` from the project's shape: analysis, automation, skill, app, or research) and links each place, its `## When you finish a task` table says which linked file a change updates, every file links back up to what routes to it (`pm.py walk` fails on a broken or missing link), facts live in the file that owns them, every working folder's `CONTEXT.md` is its contract (Inputs, Process, Outputs, Verify, Human check), and an item names the cards or stages it touches so `/pm:work` loads only those. Any shape can add a System map in `docs/pm/map/`; only the skill shape gets numbered stages inside a skill folder, packageable as a Claude skill. Any project work goes through an item; `validated` records a separate validator's verdict for committed work, and `finish` marks it Done only with a current pass and committed work. The method and its credit are in `${CLAUDE_PLUGIN_ROOT}/icm/README.md`.

Each item is one file in `docs/pm/items/`, the only board state stored in git. `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm.py" board` renders In flight, Queued, Waiting, and the latest ten Done items from those files; `next` shows queued items with completed dependencies. A hold keeps an item in Waiting, still owned by any claimer, until the decision is resolved. `pm.py validated ITEM_ID --verdict pass|findings` records a validator result for committed work; `finish` requires a current pass. `/pm:work` runs each item in its own worker session, a full Claude Code session in its own copy of the project that the person can open and talk to: `pm.py worker start` starts one in the background (in the Claude app, `pm.py worker brief` gives the app's own session tool what it needs), `pm.py worker answer` continues it with the owner's answer, `pm.py worker list` shows what each is doing or waiting on, `pm.py defaults` holds the worker sessions' model (an exact version) and effort, which their validator uses too unless set apart, and `pm.py worker mode` this copy's permission setting for worker sessions. `pm.py walk` runs the walk test's mechanical checks, `pm.py index` rebuilds the map's card index, `pm.py refs` checks what points at a file before it moves, `pm.py places` lists new files outside the table's places (the Stop hook runs it), and `pm.py correct` records a correction so the third of one kind suggests fixing the source. The manual is `${CLAUDE_PLUGIN_ROOT}/docs/manual.md`; where each kind of knowledge goes is `${CLAUDE_PLUGIN_ROOT}/docs/placement.md`.

## Reply

Print the guide as is, then stop.
