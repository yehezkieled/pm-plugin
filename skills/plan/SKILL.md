---
name: plan
description: Add or change work items - a milestone, an epic, a ticket, a bug, or an idea - and apply an agent's proposed changes. Use when the user wants to add a feature or task, file, report, record, track, log, or note down a bug or an idea for later, break an epic into tickets, set priorities or dependencies, or apply, accept, review, or go through the proposed changes an agent left on a ticket (never edit code for those: they become tickets). Asks one question at a time, then writes the markdown and redraws the epic flow. Not for doing the work itself (that is pm:work).
argument-hint: "milestone|epic|ticket|bug|idea|apply [title or Txxx]"
---

# /pm:plan

Adds work to docs/pm. Kinds: `milestone`, `epic`, `ticket`, `bug`, `idea`, `apply`. Take the kind from $ARGUMENTS; if it is missing, infer it from what the user said (a broken behaviour is a bug, "someday" is an idea, everything else is a ticket).

Scripts: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm.py" ...`. If python3 is missing, create the files by hand from `${CLAUDE_PLUGIN_ROOT}/templates/` with the next free id and rewrite the epic's Tickets and Flow sections yourself.

If docs/pm does not exist, say so and offer /pm:init. Never invent milestones, dates, or effort numbers.

## How to question

This is the essence of a structured "grill me" interview, kept short:
- First read the repo and docs/pm. Ask nothing you can look up.
- One question at a time. Each question offers a recommended answer and the reason for it. Use AskUserQuestion when available.
- Stop as soon as you can write What, Why, and at least one testable Acceptance line without guessing. A trivial ticket (typo, rename, config value, one-file fix) needs at most one question.
- A ticket is a design choice when there is more than one sensible approach, or it touches data shapes, public interfaces, or security. Design choices get `plan: required`, so /pm:work will write a plan and wait for approval before editing code.
- No ticket without testable acceptance. If the user cannot say how they would check it, keep asking, or file it as an idea instead.

## ticket

1. Epic: pick the epic it belongs to (read `docs/pm/roadmap.md` and `docs/pm/epics/`). If none fits, offer to create one.
2. Priority: P0 stop everything, P1 next, P2 normal (default), P3 nice to have.
3. Dependencies: look at the epic's Flow. Ask "must anything finish first?" only when the Flow suggests it.
4. auto: `yes` only when a routine could do it unattended: clear acceptance, no decisions left, plan none or already approved.
5. Create: `pm.py new ticket --title "<title>" --epic Exx [--priority P1] [--depends T010,T011] [--auto] [--plan required]`, then edit the file: What (one paragraph), Why (one or two lines), Acceptance (one testable line per item), Subtasks (first steps).
6. `pm.py flow Exx`, then `pm.py validate`.
7. If the pm block says `mirror: on`: `pm.py sync` (no python3: skip it and say the mirror is behind; the next sync catches up).
8. Report: id, path, where it sits in the Flow, and whether it is ready now.

## bug

Same as ticket, with: title starts with `Bug:`; What = steps to reproduce, expected and actual; Acceptance includes "a test reproduces the bug and now passes"; priority default P1.

## idea

Append one line to the Backlog section of `docs/pm/roadmap.md`. No ticket, no questions beyond a title. Report the line.

## epic

Ask for the milestone and a one-line goal (recommend from the roadmap). `pm.py new epic --title "<title>" --milestone Mx --goal "<goal>"`. Then ask once: break it into tickets now (two to six) or later. If now, run the ticket steps for each.

## milestone

Ask for the title and the one-line goal. `pm.py new milestone --title "<title>" --goal "<goal>"`. It goes after the last milestone and before Backlog. Milestones are ordered versions, never calendar targets.

## apply

For the ticket named in $ARGUMENTS (or every ticket the board lists under "Proposed changes waiting"): read its `## Proposed changes` section and walk through each proposal, one at a time:
- accept: new ticket via the ticket steps (it may depend on the current one), or an edit to this ticket's Acceptance or Subtasks
- edit: ask what to change, then accept
- reject: drop it and write one line in `## Notes` saying why
Clear the section when done, then `pm.py flow Exx`.

## Decisions

If the questioning settled something a future reader would otherwise have to guess (a library, a data shape, a rule), add an entry at the top of `docs/pm/decisions.md`: Context, Decision, Consequences. When it replaces an older entry, say "Replaces entry of <date>".
