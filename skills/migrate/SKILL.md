---
name: migrate
description: "Move an existing task system (old pm board, TODO.md, tasks folder, Beads, GitHub Issues, Linear export) onto the pm board. Use when the user says \"migrate\", \"import our tasks\", \"move our backlog to pm\", or \"switch from X to pm\". Not for adding one task (use plan)."
---

# /pm:migrate

Converts another project-management system into `docs/pm/items/`. The full guide, field mappings, and plan file format are in `${CLAUDE_PLUGIN_ROOT}/docs/manual.md`; knowledge that is not a task is routed by `${CLAUDE_PLUGIN_ROOT}/docs/placement.md`. Never delete the old system without the owner's explicit yes, and never summarise the requester's words: they are copied verbatim into `## Requester intent`.

1. Scan: run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm.py" migrate scan`. It lists what it found with counts. For GitHub Issues, also run `gh issue list --state open --limit 200`; for Beads, Linear, or another tracker, read its export. If several systems are found, migrate one at a time, starting with the one the owner names.
2. Plan, in a scratch directory outside the repo (for example from `mktemp -d`); this writes nothing to the repo:
   - Old pm-plugin 0.x board: `pm.py migrate plan --from pm-0x --out PLAN.json`.
   - A Markdown checklist (`- [ ]`, `- [x]`): `pm.py migrate plan --from checklist --file TODO.md --out PLAN.json`.
   - Anything else: write the plan JSON yourself in the format in the manual. Map each source field to an item field, copy the requester's words verbatim into `intent`, and keep the source's id in `key`.
   Add `--done items` only if the owner wants finished work imported as Done items; the default leaves it in git history.
3. Show the owner what you found and the plan: the field mapping (a table for a hand-made plan), counts before and after, anything not carried over or ambiguous, the knowledge that is not a task with where it will go, and which old files would be removed afterwards. Resolve ambiguity by asking, one question at a time with a recommendation. Apply the owner's changes by editing `PLAN.json`. Ask once for a yes before writing anything.
4. After the yes, run `pm.py migrate apply PLAN.json` (add `--dry-run` first if unsure). It creates the board if needed, writes the items, and prints the counts after. A second run adds nothing twice. If `AGENTS.md` lacks the board pointer, add it as `/pm:init` step 4 describes.
5. Route the knowledge that is not a task, following `${CLAUDE_PLUGIN_ROOT}/docs/placement.md`: lasting rules and commands to `AGENTS.md`, product goals to `README.md`, architecture to `docs/pm/CODEBASE.md` (use `/pm:map`). Show each proposed edit to the owner before writing it; never drop anything.
6. Verify: show `pm.py board` and the before and after counts, and check that every old entry is an item, in git history, or listed in the plan as not carried over.
7. Retire: ask the owner whether to remove the old system. Only on a yes, `git rm` exactly the paths the plan lists as to remove (never `rm`, never anything unlisted), so git history keeps the old files. On a no, leave them and say they remain. Existing GitHub issue numbers are kept on the items; the mirror stays off, and enabling it makes sync rewrite those issues' bodies.

## Reply

Talk in outcomes, not mechanics: plain words, no internal jargon (say "waiting on your decision", not "hold"). The reply must stand alone: lead with the result, then any decision needed. No progress narration. Mark unverified claims `[UNSURE]`. Before writing: what was found, what will become what, the counts, and the one yes you need. After: counts before and after, what went where, what is left in the old system, and whether it was removed.
