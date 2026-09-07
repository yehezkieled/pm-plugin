---
name: brainstorm
description: Brainstorm with the user - an open thinking session about the project or one part of it (a problem, a feature, a direction, what to build next) with questions one at a time, then a proposal of which pm files to update and why, written only after a yes. Use when the user wants to brainstorm, think out loud, explore, talk through, kick around, weigh options for, or discuss a project, feature, problem or direction, asks what a part of the project still needs or what is missing, asks which pm files you would change and why, or is not sure what to build next. Any request that says brainstorm belongs here, whatever else it says. Works when the user cannot answer questions right now: the session then ends at the proposal and writes nothing. Not for filing one known item (that is pm:plan), not for sharpening one ticket (that is pm:grill), and not for creating docs/pm from nothing (that is pm:init, which this skill hands off to).
argument-hint: "[topic]"
---

# /pm:brainstorm

Thinking first, files second. This skill is a conversation: it widens the question, looks up what the repo already answers, and narrows to what should change in docs/pm. It ends with a proposal, one row per file with the reason, and writes only the rows the user accepted. Nothing is written before that yes.

Scripts: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm.py" ...`. If python3 is missing, create files by hand from `${CLAUDE_PLUGIN_ROOT}/templates/` and redraw the epic's Tickets and Flow sections yourself.

If docs/pm does not exist, brainstorm anyway. The proposal is then the input of /pm:init (the goal of the first milestone, its two to five pieces, ideas for the Backlog), and on a yes you invoke the `pm:init` skill instead of writing files by hand. Never write dates, deadlines, or effort guesses.

## 1. Read first

Before the first question read: README or CONTEXT.md, the top-level layout, `docs/pm/roadmap.md`, the current milestone's epics and their Flow, `pm.py board`, `docs/pm/decisions.md`, and the code and tests the topic touches. Ask nothing you can look up. Open with two or three lines: what the repo and docs/pm already say about the topic.

## 2. Frame

Take the topic from `$ARGUMENTS` or from what the user said. When there is none, ask one question, "What is this session about?", with a recommended answer taken from the board: the current milestone's gaps, the `To grill:` line, or the Backlog. Restate the topic in one line and go on.

## 3. Widen, then narrow

One question at a time: one AskUserQuestion call per question, never several bundled. Each question offers a recommended answer first and the reason for it. If AskUserQuestion is not available, ask in plain text and wait. A question either widens (what else, for whom, what could go wrong) or narrows (which of these, what is out). Kinds, in rough order; skip any the reading already answered:

1. **Problem and person.** What hurts today, and for whom.
2. **What exists.** Say what the repo and docs/pm already cover, since you looked it up, and ask only whether that reading is right.
3. **Options.** Two to four ways to go, each with its trade-off in one line. The user picks one, mixes, or adds a fifth.
4. **Risks and non-goals.** What could go wrong; what is out of scope for now.
5. **First usable version.** What a person could do when it is done, and how they would check.

Rules that shape the questions:

- **Intent versus fact.** Ask about intent: what should happen, for whom, how they would check it. Do not ask facts nobody knows yet: how a library behaves, how fast something is, what shape the data has. When the answer would be "not sure, probably X", stop asking and carry the unknown into the proposal as a `plan: required` design ticket.
- **Say back what settled.** Every third question or so, restate the settled points in three lines so the user can correct them. Keep that list; it becomes the proposal.
- **No dates, no deadlines, no effort guesses.** Milestones are ordered versions.
- **Stop** when the user says enough, or when two answers in a row add nothing new. Most sessions need four to eight questions.
- **Talk only.** Do not build, do not edit code, do not grill a ticket inside the session. A ticket is grilled after it exists, by /pm:grill.

## 4. Propose

Print the proposal as a table with exactly these columns: `file | change | why`. One row per change. A row is one of:

- `docs/pm/roadmap.md`: a new milestone (title and one-line goal), a changed goal, or one Backlog line for an idea with no home yet.
- `docs/pm/epics/Exx-*.md`: a new epic under a milestone, with its goal.
- `docs/pm/tickets/Txxx-*.md`: a new thin ticket (`ready: no`) under an epic, with a first draft of What and Acceptance in the session's own words. A question nobody could answer becomes a `plan: required` ticket whose Acceptance is a decisions.md entry.
- `docs/pm/decisions.md`: something the session settled that a future reader would otherwise guess (a rule, a data shape, a library): Context, Decision, Consequences.
- an existing ticket: dismiss with a reason when the session decided against it (`pm.py dismiss Txxx --reason "..."`), or one line under its `## Notes` when its meaning changed.
- `CONTEXT.md` pm block: rarely, a gate or the flow the session changed.

"Nothing to write" is a valid proposal: say so, and list what was settled in talk only.

Then one question, asked with AskUserQuestion like the others, three options: apply every row (recommended), pick rows, or none. Nothing is written before that answer.

**Delegation.** When the user asked for this session and said to take your recommended answers (or not to ask questions), hold the session with yourself in their place: take the recommended answer at each step, list those answers in the report, print the proposal table all the same (the user asked to see which files change and why before they change), and then apply it. That delegation covers the brainstorm only, not the grill: the tickets it creates did not exist when the user spoke, so a delegated run never invokes pm:grill and never marks a ticket ready. They stay `ready: no` and the report names them for /pm:grill. Without that delegation, a headless or routine run, or a user who says they cannot answer now, ends at the proposal: write nothing, and say that a person applies it by running /pm:brainstorm again with the rows they want, or /pm:plan for a single row.

## 5. Write

Only the accepted rows, and only after the `file | change | why` table has been printed in this conversation, in every kind of run: the first `pm.py new`, edit, or file write comes after the table, never before it. Same commands /pm:plan uses:

1. `pm.py new milestone --title "<title>" --goal "<goal>"`; `pm.py new epic --title "<title>" --milestone Mx --goal "<goal>"`; `pm.py new ticket --title "<title>" --epic Exx [--priority P1] [--depends T010,T011] [--plan required]`, then edit the ticket: What (first draft from the session), Why (one or two lines, never a placeholder), Acceptance (one line per item, as testable as the session made it), Subtasks (first step). Tickets stay `ready: no`; never pass `--ready`. Backlog: one line under `## Backlog` in `docs/pm/roadmap.md`. Decisions: an entry at the top of `docs/pm/decisions.md`. Dismiss: `pm.py dismiss Txxx --reason "..."`.
2. `pm.py flow --all`, then `pm.py validate`. Fix anything it reports.
3. If the pm block says `mirror: on`: `pm.py sync` (no python3: skip it and say the mirror is behind).
4. New tickets get the hand-off, once for the set: "Grill the unblocked ones now, or later?" Recommend now. On now, invoke the `pm:grill` skill per ticket, unblocked ones first. On later, leave them `ready: no` and name them in the report. A delegated run does not ask this question and does not grill: same outcome as later, whatever the user said about taking your answers.
5. Do not commit unless the user asks. In `direct` flow, offer to commit the new files.

## 6. Report

Three short parts: **settled in talk** (points that changed no file), **written** (each applied row with its id or line and its why in a few words), and **next** (one command: `/pm:grill Txxx`, `/pm:init`, `/pm:plan`, or `/pm:work`).
