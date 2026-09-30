---
name: work
description: "Do a task from the board: claim it, build it, mark it done. Use when the user says \"work on\", \"implement\", \"do\", or \"go ahead and do\" a task on the board, or \"pick the next task and do it\". Call this first; it finds the task itself, so do not call status first. Not for adding tasks (use plan)."
argument-hint: "[item-id]"
---

# /pm:work

1. With a Git remote, switch to the default branch and fast-forward it from the remote so the board is current. If the user did not name an item, run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm.py" next` and take the first ready item. If none is ready, show the waiting reason and stop.
2. Identify yourself as the current user's name (ask only if it cannot be determined). For a new claim in a repository with a remote, start from the remote default branch. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm.py" claim ITEM_ID` with the person's name in a single-quoted heredoc before inspecting or editing product code. Choose a closing marker that does not appear in the name. The CLI fetches the latest default branch, commits the claim there, and pushes without force; only one competing push can land. A rejected push is fetched and checked again. If another person owns it, stop without touching the work. Without a remote, the CLI uses a local file lock.
3. After the claim command succeeds, use `pm/ITEM_ID` as the work branch. If resuming, switch to the existing local branch when present. Otherwise fetch the same remote used by the claim command and switch to `pm/ITEM_ID` from that remote if it exists. If the branch exists nowhere, create it from the claim commit: with a remote, check out the default branch, fetch it, and fast-forward to the shared claim commit first; without a remote, use the current branch where the local claim was saved. For a new claim, create and switch to `pm/ITEM_ID` from the branch containing the saved claim. Do not create a separate branch-only claim commit.
4. Read the item detail and relevant code. Keep implementation within the requester's saved intent. If a product decision is needed, park the item with `/pm:plan`'s hold command and stop for that decision.
5. Make the change, run the project's relevant checks, and update the item's `## Current notes` with a concise summary of current progress (rewrite, do not append a diary). Update project docs affected by the change.
6. When the requested work is complete, run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm.py" finish ITEM_ID` with the completion summary in a single-quoted heredoc. Choose a closing marker that does not appear in the summary. In a Git repository, this commits only that item's file with its Done state locally on the work branch; the PR merge publishes it to the shared default branch. Do not push separately. Until merge, other clones correctly continue to see the item In flight. Otherwise leave it In flight, still owned by you, and report the next action.
7. Show `pm.py board` and relate the result to the requester's exact words.

This workflow uses the active Claude Code model. It does not start reviewer agents or switch model providers.

## Reply

Talk in outcomes, not mechanics: plain words, no internal jargon (say "waiting on your decision", not "hold"). The reply must stand alone: lead with the result, then any decision needed. No progress narration. Mark unverified claims `[UNSURE]`. When finished, state what changed for the requester, the branch or PR link, checks run and their real results, and any decision or review needed. When stopping (owned by someone else, needs a decision), lead with the evidence, then the consequence, then options with a recommendation. Report failures plainly with the command output.
