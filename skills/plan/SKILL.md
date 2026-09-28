---
name: plan
description: Capture a piece of project work as a queued item with the requester's exact words, dependencies, or a decision hold. Use when the user asks to record, track, or queue work.
argument-hint: "[short title]"
---

# /pm:plan

1. Read `docs/pm/BOARD.md`; if it is missing, invoke `/pm:init` first.
2. Capture the requester's original words exactly in the item's `## Requester intent` section. Do not summarize, normalize, or silently add acceptance criteria. Ask for a short title only if one cannot be inferred.
3. Create the item with `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm.py" add "<short title>" --intent "<requester's exact words>"`. Include only details the requester actually supplied.
4. If the work must wait for another item, set dependencies with `pm.py set PM-NNN --depends PM-001,PM-002`. Dependencies point to item IDs and are satisfied only when those items are Done.
5. If a decision is needed before work can proceed, park it with `pm.py hold PM-NNN "<specific question>" [--until YYYY-MM-DD]`. The date is optional and means when to revisit the question, not a deadline.
6. Show the item ID and detail path, then the refreshed board.

Do not invent hierarchy, priority, due dates, effort, or a plan approval gate. Item notes are the current concise state; rewrite them when facts change instead of appending a log.
