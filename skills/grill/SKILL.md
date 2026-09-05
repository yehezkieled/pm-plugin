---
name: grill
description: Grill one ticket until it is ready to work on - a short questioning round that settles What, Why, a testable Acceptance line, the plan flag, priority and dependencies, then marks the ticket ready. Use when the user wants to grill, refine, flesh out, detail, sharpen, or firm up a ticket, make a ticket ready, prepare a ticket for work, go through the tickets of an epic before building, or when /pm:work or pm.py said a ticket is not grilled yet. Not for creating tickets (that is pm:plan) and not for building them (that is pm:work).
argument-hint: "[Txxx | Exx]"
---

# /pm:grill

A ticket is born thin (`ready: no`): a title, an epic, a first draft of What and Acceptance. This skill is the interview that turns it into something an agent can build without guessing, and ends by setting `ready: yes`. `/pm:work` refuses a ticket that is not ready.

Scripts: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm.py" ...`. If python3 is missing, edit the ticket markdown yourself and redraw the epic's Tickets and Flow sections by hand.

If docs/pm does not exist, say so and offer /pm:init. Never write dates, deadlines, or effort guesses.

## 1. Pick

- `$ARGUMENTS` names a ticket: grill that one.
- `$ARGUMENTS` names an epic: grill its `ready: no` tickets one after another, in the epic's Flow order, unblocked ones first. Stop between tickets only if the user asks to.
- Nothing given: run `pm.py board` and look at the `To grill:` line. One ticket: take it. Several: ask which one, recommending the first in Flow order. None: say so, show `Ready now`, and suggest /pm:work or /pm:plan.

## 2. Blocked check

A ticket with an open dependency (`depends_on` not all `done`) is grilled after that dependency lands, because what lands can change the answers. When the picked ticket is blocked: say which ticket it waits on, recommend waiting, and offer to grill that blocker instead when it is not ready either. Grill the blocked ticket now only when the user, told that it is blocked, says to go on anyway. "Do not ask questions" or "take your recommended answers" is not that: the recommended answer for a blocked ticket is to wait, so report and stop, changing nothing. Grilled early on the user's word (`pm.py ready Txxx --early`), the board flags it `grilled early` until the dependency is done, and /pm:grill on a `ready: yes` ticket is the re-check.

## 3. Read first

Before the first question read: the ticket file, its epic's Goal and Flow, `docs/pm/decisions.md`, the sibling tickets, and the code and tests the ticket will touch. Ask nothing you can look up. Many tickets need one question after this; some need none, and then you say so and go straight to step 5.

## 4. Interview

One question at a time: one AskUserQuestion call per question, never several bundled. Each question offers a recommended answer first and the reason for it. If AskUserQuestion is not available, ask in plain text and wait.

`ready: yes` means a person settled the answers, so the recommended answers may stand in for theirs only when that person delegated this grill: they asked for the grill and said to take your recommended answers (or not to ask questions). Then take the recommended answer for each and list them in the report. Without that delegation, a headless or routine run, or a run that arrived here from another skill, does not mark the ticket ready: write the proposed What and Acceptance lines under `## Notes` as "Grill draft:", leave `ready: no`, and say a person confirms them with /pm:grill Txxx.

Ask only what is still open, in this order:

1. **What.** Only when the What is a title restated or a placeholder: "What exactly should happen, in one paragraph?" Propose your own reading of the title and the epic as the recommended answer.
2. **Why.** Only when Why is missing: who is it for and what does it change for them. One or two lines.
3. **Acceptance.** Propose the lines yourself, one testable line per item, then ask accept or change. Testable means a person or a test can say yes or no: a command and its output, a behaviour and its result, a file and what it contains.
4. **Design choice.** More than one sensible approach, or it touches data shapes, public interfaces, or security: recommend `plan: required`. Otherwise `plan: none`.
5. **Priority and dependencies.** Only when the epic's Flow or the sibling tickets suggest a change. P0 stop everything, P1 next, P2 normal, P3 nice to have.
6. **auto.** `yes` only when a routine could do it unattended: clear acceptance, no decisions left, plan none or already approved.

Rules that shape the questions:

- **Intent versus fact.** You ask the user about intent: what should happen, for whom, how they would check it. Do not ask them facts nobody knows yet: how a library behaves, how fast something is, what shape the data has. When the answer to a question would be "not sure, probably X", stop asking. Turn the unknown into the ticket: `plan: required`, What = the question to answer, Acceptance = "a decisions.md entry names the chosen approach, the alternatives, and what decided it" plus the follow-up tickets this decision unblocks. The investigation then happens in /pm:work plan mode, with the code open.
- **No acceptance, no ticket.** When the user cannot say how they would check it, offer to move it to the Backlog as an idea instead (`pm.py dismiss Txxx --reason "not testable yet, kept as an idea"` and one line under `## Backlog` in `docs/pm/roadmap.md`).
- **Do not widen.** Anything that turns out to be a second piece of work becomes its own ticket through /pm:plan, possibly depending on this one. This ticket stays one PR.
- **Trivial ticket** (typo, rename, config value, one-file fix): at most one question, the acceptance line.
- Stop as soon as What, Why, one testable Acceptance line, and the plan flag are settled without guessing.

## 5. Write

1. Edit the ticket file: What (one paragraph), Why (one or two lines), Acceptance (one testable line per item, as `- [ ]` boxes), Subtasks (the first steps). Leave `## Plan`, `## Notes`, and `## Proposed changes` alone.
2. `pm.py set Txxx` for any field the interview changed (`plan=required`, `priority=P1`, `depends_on=T010,T011`, `auto=yes`), then `pm.py ready Txxx`. It refuses a blocked ticket; `--early` is added only when the user, told the ticket is blocked, said to go on (step 2), never on your own.
3. `pm.py flow Exx`, then `pm.py validate`. Fix anything it reports.
4. A decision a future reader would otherwise guess (a library, a data shape, a rule): add an entry at the top of `docs/pm/decisions.md` with Context, Decision, Consequences.
5. If the pm block says `mirror: on`: `pm.py sync` (no python3: skip it and say the mirror is behind).
6. Do not commit unless the user asks. In `direct` flow, offer to commit the ticket file.

## 6. Report

Ticket id and title, what changed (fields and sections), `ready: yes`, and one of: "ready to start with /pm:work Txxx", "waits on Tyyy", or "moved to the Backlog". When an epic was given, one line per ticket.
