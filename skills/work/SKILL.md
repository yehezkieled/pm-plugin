---
name: work
description: "Do project work through the board: claim, build, mark done. Use when the user asks to work on, implement, build, analyse, or write up something in this project, or \"pick the next task and do it\". Call this first; it finds the task itself, so do not call status first. Not for adding tasks (use plan)."
argument-hint: "[item-id]"
---

# /pm:work

You coordinate; workers build. In this session you never edit project files, claim an item, or run the build yourself: each board item is done by a `pm:worker` agent you start with the Agent tool. It claims the item, builds it, has a separate `pm:validator` agent check it, and finishes it or parks it with a question. Your part is the board, filing, talking to the person, starting workers, and checking their reports.

`pm.py` below means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm.py"`.

1. Find the items. With a Git remote, switch to the default branch and fast-forward it from the remote so the board is current. Work the person asks for that is not on the board yet goes on it first with `/pm:plan`'s `add`, the requester's words verbatim. One request is one item, done by one worker in order, even when it has several steps; split it only into pieces that do not build on each other, so each can run in its own worker now. If they named items, use those. Otherwise run `pm.py next` and take the first ready item. If none is ready, show the waiting reason and stop.
2. Find the person's name (`git config user.name`, or the conversation; ask only if it cannot be determined). Workers claim under it.
3. Start the workers. For each item, one Agent call with `subagent_type: "pm:worker"` and a short brief: the item ID, the person's name, and "new claim" or "resume the existing claim". Add to a resume brief that the owner's answer is saved in the item, or the person's correction in their exact words. Do not restate or reinterpret the requester's words; the worker reads them from the item.
   - Items that are all ready can run at once: start them in one message, each with `isolation: "worktree"`, so their checkouts do not collide. A lone worker runs in this checkout without isolation, so it sees files the person left here; while it runs, start no other worker.
   - An item that depends on another waits until that one is Done on the board, which happens when its branch merges. Say so rather than starting it.
   - Never give one item to two workers, and never start a worker on an item in flight for someone else.
4. While workers run, change nothing: no edits, no claims, no builds. You may read the board.
5. Check each report against the repository: `pm.py board` and `git log --oneline -5 pm/ITEM_ID`. A done item has a recorded `Validation: pass at <sha>` line in its notes on its branch; the validator records its verdict, then the worker confirms the line is present before finishing. This CLI check guards against forgetting validation; it cannot identify who called it, and the session trace shows each `pm:validator` launch. A waiting item is in Waiting with the question. If the report and the repository disagree, or the worker stopped without finishing or parking the item, start one fresh worker to resume it with the gap stated; if that also fails, tell the person what is wrong.
6. Waiting on the owner: relay the worker's question to the person in plain words, one clear question per item. When they answer, run `pm.py resume ITEM_ID --answer` with their exact words in a single-quoted heredoc (choose a closing marker that does not appear in them), then start a worker to resume the claim.
7. When the person corrects a worker's output (in chat, in a review comment, or by editing a file a worker produced), start a worker to resume that item with their exact words; it fixes the output and records the correction with `pm.py correct`.
8. Show `pm.py board` and relate each result to the requester's exact words.

Workers use the active Claude Code model. This workflow does not switch model providers.

## Reply

Talk in outcomes, not mechanics: plain words, no internal jargon (say "waiting on your decision", not "hold"; "a separate check passed", not the agent's name). The reply must stand alone: lead with the result, then any decision needed. No progress narration. Mark unverified claims `[UNSURE]`. For each item: what changed for the requester, the branch, the checks run and their real results, what the separate check found, and any decision or review needed. When an item is waiting, lead with the question, then what it blocks, then options with a recommendation. Report failures plainly with the command output.
