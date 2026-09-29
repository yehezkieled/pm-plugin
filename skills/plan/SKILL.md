---
name: plan
description: Capture a piece of project work as a queued item with the requester's exact words, dependencies, or a decision hold. Use when the user asks to record, track, or queue work.
argument-hint: "[short title]"
---

# /pm:plan

1. Read `docs/pm/BOARD.md`; if it is missing, invoke `/pm:init` first.
2. Capture the requester's original words exactly in the item's `## Requester intent` section. Do not summarize, normalize, or silently add acceptance criteria. Ask for a short title only if one cannot be inferred.
3. Create the item by passing a single-quoted heredoc to `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm.py" add --request-stdin`. Put the short title on the first line and the requester's exact words on the remaining lines. Choose a closing marker that does not appear in either value. This passes `$`, quotes, backticks, and command-like text literally. Include only details the requester actually supplied.
4. If the work must wait for another item, set dependencies with `pm.py set ITEM_ID --depends DEPENDENCY_ID,DEPENDENCY_ID`. Dependencies point to item IDs and are satisfied only when those items are Done.
5. If a decision is needed before work can proceed, park it by passing the question through a single-quoted heredoc to `pm.py hold ITEM_ID --reason-stdin [--until YYYY-MM-DD]`. Choose a closing marker that does not appear in the question. The date is optional and means when to revisit the question, not a deadline.
6. Show the item ID and detail path, then the refreshed board.

Do not invent hierarchy, priority, due dates, effort, or a plan approval gate. Item notes are the current concise state; rewrite them when facts change instead of appending a log.
