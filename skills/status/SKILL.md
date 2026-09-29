---
name: status
description: Show what is in flight, who owns it, what is queued or waiting, and which item is ready next. Use when the user asks for status or next work.
---

# /pm:status

Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm.py" board` and show its output. It lists In flight, Queued, Waiting, recent Done, and Ready next. Read the detail files for any item whose reason or requester intent needs more context. If Python is unavailable, read the item files in `docs/pm/items/` directly.

End with a concise recommendation for the next action. Do not infer dates, progress percentages, or priorities that the board does not record.

## Reply

Talk in outcomes, not mechanics: plain words, no internal jargon (say "waiting on your decision", not "hold"). The reply must stand alone: lead with the result, then any decision needed. No progress narration. Mark unverified claims `[UNSURE]`. Show the board, then one recommendation for what to do next and why. If several items need the person, say which decision unblocks what.
