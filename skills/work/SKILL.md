---
name: work
description: Claim and carry out one queued project item, updating its current notes and status. Use when the user asks to start or implement tracked work.
argument-hint: "[PM-NNN]"
---

# /pm:work

1. Read `docs/pm/BOARD.md`. If the user did not name an item, run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm.py" next` and take the first ready item. If none is ready, show the waiting reason and stop.
2. Identify yourself as the current user's name (ask only if it cannot be determined). Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm.py" claim PM-NNN "<person>"` before inspecting or editing product code. This claim is serialized with a file lock. If another person owns it, stop without touching the work.
3. When the repository has a remote and shared collaborators use separate checkouts, commit and push the claim before code changes. If the push is rejected, pull the board and resolve ownership before proceeding.
4. Read the item detail and relevant code. Keep implementation within the requester's saved intent. If a product decision is needed, park the item with `/pm:plan`'s hold command and stop for that decision.
5. Make the change, run the project's relevant checks, and update the item's `## Current notes` with a concise summary of current progress (rewrite, do not append a diary). Update project docs affected by the change.
6. When the requested work is complete, run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm.py" finish PM-NNN --note "<concise completion summary>"`. Otherwise leave it In flight, still owned by you, and report the next action.
7. Show the updated board and relate the result to the requester's exact words.

This workflow uses the active Claude Code model. It does not start reviewer agents or switch model providers.
