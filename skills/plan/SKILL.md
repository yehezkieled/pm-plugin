---
name: plan
description: "Add a task to the board, keeping the user's exact words, and optionally set what it depends on or park it for a decision. Use when the user says \"add\", \"track\", \"queue\", or \"remember to\" some work, or \"wait on X\". Not for doing the work (use work)."
argument-hint: "[short title]"
---

# /pm:plan

1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm.py" board`; if there is no board, invoke `/pm:init` first.
2. Capture the requester's original words exactly in the item's `## Requester intent` section. Do not summarize, normalize, or silently add acceptance criteria. Ask for a short title only if one cannot be inferred.
3. Create the item by passing a single-quoted heredoc to `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm.py" add`. Put the short title on the first line and the requester's exact words on the remaining lines. Choose a closing marker that does not appear in either value. This passes `$`, quotes, backticks, and command-like text literally. Include only details the requester actually supplied. With a Git remote, the CLI commits the new item file and pushes it to the shared default branch, so `/pm:work` in any clone can claim it; `set`, `hold`, and `resume` publish the same way. If the current branch is the default branch, it must be able to fast-forward to the remote.
4. If the work must wait for another item, set dependencies with `pm.py set ITEM_ID --depends DEPENDENCY_ID,DEPENDENCY_ID`. Dependencies point to item IDs and are satisfied only when those items are Done.
5. If a decision is needed before work can proceed, park it by passing the question through a single-quoted heredoc to `pm.py hold ITEM_ID [--until YYYY-MM-DD]`. Choose a closing marker that does not appear in the question. The date is optional and means when to revisit the question, not a deadline. A hold keeps any existing claim; `pm.py resume ITEM_ID` returns a claimed item to In flight for the same owner and an unclaimed one to Queued.
6. Show the item ID and detail path, then the output of `pm.py board`. If the CLI says the change was published from another branch, say that it is on the shared default branch and appears on the current branch only after syncing with it.

Do not invent hierarchy, priority, due dates, effort, or a plan approval gate. Item notes are the current concise state; rewrite them when facts change instead of appending a log.

## Reply

Talk in outcomes, not mechanics: plain words, no internal jargon (say "waiting on your decision", not "hold"). The reply must stand alone: lead with the result, then any decision needed. No progress narration. Mark unverified claims `[UNSURE]`. Confirm what was captured (item ID, path, title) and, if something is blocked or parked, the one question you need answered. Ask only for real decisions.
