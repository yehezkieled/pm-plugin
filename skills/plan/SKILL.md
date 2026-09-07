---
name: plan
description: Add or change work items - a milestone, an epic, a ticket, a bug, or an idea - and apply an agent's proposed changes. Use when the user wants to add a feature or task, file, report, record, track, log, or note down a bug or an idea for later, break an epic into tickets, set priorities or dependencies, or apply, accept, review, or go through the proposed changes an agent left on a ticket (never edit code for those: they become tickets). Creates the item thin and offers to grill it. Not for grilling a ticket that already exists (that is pm:grill), not for open thinking about what to build (that is pm:brainstorm), and not for doing the work itself (that is pm:work).
argument-hint: "milestone|epic|ticket|bug|idea|apply [title or Txxx]"
---

# /pm:plan

Adds work to docs/pm. Kinds: `milestone`, `epic`, `ticket`, `bug`, `idea`, `apply`. Take the kind from $ARGUMENTS; if it is missing, infer it from what the user said (a broken behaviour is a bug, "someday" is an idea, everything else is a ticket).

Scripts: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm.py" ...`. If python3 is missing, create the files by hand from `${CLAUDE_PLUGIN_ROOT}/templates/` with the next free id and rewrite the epic's Tickets and Flow sections yourself.

If docs/pm does not exist, say so and offer /pm:init. Never invent milestones, dates, or effort numbers.

## Thin first, grill second

This skill captures; /pm:grill questions. A new ticket is written thin, `ready: no`: title, epic, priority, dependencies, and a first draft of What and Acceptance taken from the user's own words and from the repo. The interview that settles What, Why, testable Acceptance, and the plan flag is /pm:grill, and /pm:work refuses a ticket until it says `ready: yes`.

- First read the repo and docs/pm. Ask nothing you can look up.
- Ask only what the file needs and cannot be inferred: which epic, and a dependency when the Flow suggests one. One question at a time, a recommended answer first, with AskUserQuestion when available. Most tickets need no question here.
- Blocked tickets (an open `depends_on`) are grilled after the dependency lands, so for those the hand-off is "later".
- Every ticket ends with the hand-off question (step 8), unless the user already said when ("grill it now", "just file it, details later"): then do that without asking. When the user said not to ask questions and did not say when, take the recommended answer: grill now when the ticket is unblocked, later when it is blocked.
- Never write a placeholder into What or Acceptance: `pm.py validate` rejects it. A first draft in plain words is fine; the grill sharpens it.

## ticket

1. Epic: pick the epic it belongs to (read `docs/pm/roadmap.md` and `docs/pm/epics/`). If none fits, offer to create one.
2. Priority: P0 stop everything, P1 next, P2 normal (default), P3 nice to have.
3. Dependencies: look at the epic's Flow. Ask "must anything finish first?" only when the Flow suggests it.
4. auto: `yes` only when a routine could do it unattended: clear acceptance, no decisions left, plan none or already approved.
5. Create: `pm.py new ticket --title "<title>" --epic Exx [--priority P1] [--depends T010,T011] [--auto] [--plan required]`, then edit the file: What (a first draft, one paragraph, from the user's words), Why (one or two lines; when the user gave no reason, write the one the title implies, never a placeholder), Acceptance (a first draft, one line per item, as testable as you can make it from what was said), Subtasks (first step). The ticket stays `ready: no`.
6. `pm.py flow Exx`, then `pm.py validate`.
7. If the pm block says `mirror: on`: `pm.py sync` (no python3: skip it and say the mirror is behind; the next sync catches up).
8. Hand-off, one question: "Grill Txxx now, or later?" Recommend now when its dependencies are done (or it has none), later when it is blocked, and say which ticket it waits on. On now: invoke the `pm:grill` skill with the ticket id. On later: report and stop.
9. Report: id, path, where it sits in the Flow, `ready: no` or `ready: yes`, and the next command (`/pm:grill Txxx` or `/pm:work Txxx`).

## bug

Same as ticket, with: title starts with `Bug:`; What = steps to reproduce, expected and actual; Acceptance includes "a test reproduces the bug and now passes"; priority default P1. A bug whose reproduce steps and expected behaviour are known is grilled by its shape: pass `--ready` and skip the hand-off question. A bug the user cannot reproduce yet stays `ready: no` and is grilled like any ticket.

## idea

Append one line to the Backlog section of `docs/pm/roadmap.md`. No ticket, no questions beyond a title. Report the line.

## epic

Ask for the milestone and a one-line goal (recommend from the roadmap). `pm.py new epic --title "<title>" --milestone Mx --goal "<goal>"`. Then ask once: break it into tickets now (two to six) or later. If now, run the ticket steps for each, but ask the hand-off question once for the whole set at the end: grill the unblocked ones now (recommended) or later. Blocked tickets of the set wait either way.

## milestone

Ask for the title and the one-line goal. `pm.py new milestone --title "<title>" --goal "<goal>"`. It goes after the last milestone and before Backlog. Milestones are ordered versions, never calendar targets.

## apply

For the ticket named in $ARGUMENTS (or every ticket the board lists under "Proposed changes waiting"): read its `## Proposed changes` section and walk through each proposal, one at a time:
- accept: new thin ticket via the ticket steps (it may depend on the current one; the hand-off question comes once at the end for all accepted ones), or an edit to this ticket's Acceptance or Subtasks
- edit: ask what to change, then accept
- reject: drop it and write one line in `## Notes` saying why
Clear the section when done, then `pm.py flow Exx`.

## Decisions

If the questioning settled something a future reader would otherwise have to guess (a library, a data shape, a rule), add an entry at the top of `docs/pm/decisions.md`: Context, Decision, Consequences. When it replaces an older entry, say "Replaces entry of <date>".
