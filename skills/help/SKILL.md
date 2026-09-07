---
name: help
description: Cheat sheet for the pm plugin - every pm skill with what it does, its input and output, a brief example, and this project's pm settings. Use when the user asks which pm skills exist, how the pm workflow or the ticket system works, what /pm:init, /pm:brainstorm, /pm:plan, /pm:grill, /pm:work, /pm:status, /pm:retro or /pm:audit do, or how to use the pm plugin.
argument-hint: "[init|brainstorm|plan|grill|work|status|retro|audit]"
---

# /pm:help

Step 1, always: run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm.py" config` and `bash "${CLAUDE_PLUGIN_ROOT}/scripts/doctor.sh"` and keep their output for the "This project" part.

Step 2, no argument: print the cheat sheet code block below word for word (do not summarise or reformat it), then the examples, then "This project" with the output of step 1. With a skill name in `$ARGUMENTS`: print that skill's section word for word, then "This project".

## Cheat sheet

```
Structure   milestone -> epic -> ticket -> subtask, all markdown under docs/pm/
            roadmap.md (milestones + Backlog) . epics/Exx-*.md . tickets/Txxx-*.md . decisions.md
Settings    the "## pm" block in CONTEXT.md: flow, host, mirror, merge, gates, check, milestone, routines, auto_cap, review_model

Skill        What it does                                  Input                          Output
/pm:init     interview, then create docs/pm + pm block     [--quick]                      files, board, next steps
/pm:brainstorm think out loud, then propose file changes   [topic]                        file | change | why table, accepted rows written
/pm:plan     add milestone/epic/ticket/bug/idea, apply     kind [title | Txxx]            thin ticket file (ready: no), redrawn Flow
/pm:grill    question one ticket until it is ready         [Txxx | Exx]                   What/Why/Acceptance settled, ready: yes
/pm:work     do one ticket: claim, plan, TDD, gates, PR    [Txxx] [--routine]             branch or PR, report
/pm:status   the board, problems, what is ready            [--validate]                   one page
/pm:retro    close a milestone, keep/change notes          [Mx]                           roadmap Retro block, next milestone
/pm:audit    find bugs and debt, file tickets w/ evidence  [path] [--cap N] [--routine]   tickets, report
/pm:help     this sheet, or one skill in detail            [skill]                        text

Ticket status: todo -> in progress -> review -> done, or dismissed with a reason.  Priority: P0 (stop everything) .. P3 (nice to have).
Brainstorm first when the shape of the work is unclear: /pm:brainstorm asks, then proposes rows (milestone, epic, thin ticket, Backlog line, decision) and writes only the ones you accept.
Ticket life: /pm:plan writes it thin (ready: no) -> /pm:grill settles What, Why, Acceptance (ready: yes) -> /pm:work builds it. Blocked tickets are grilled once free.
Claim = owner field + status in progress, committed on main before branching.
An agent never widens a ticket; extra ideas go to "## Proposed changes", then /pm:plan apply.
No dates, no deadlines, no effort numbers anywhere: the board says what is done, next, and stuck.
```

Examples:
- `/pm:init` on a fresh repo: six questions, then docs/pm with M1, three epics, a few starter tickets.
- `/pm:brainstorm "sharing lists"` : five questions with recommended answers, then a table: E04 sharing epic, two thin tickets, one Backlog line, one decision; you say apply, they are written, then "grill T016 now or later?".
- `/pm:plan bug "login fails when the password has a space"` : one question, then T014 with a reproduce step and acceptance, ready by its shape.
- `/pm:plan ticket "remember me box"` : T015 written thin under E03, then "grill now or later?".
- `/pm:grill T015` : three questions with recommended answers, acceptance lines proposed, `ready: yes`, "start with /pm:work T015".
- `/pm:work` : claims T002, writes its Plan, tests first, opens PR "T002: Rate-limit login attempts".
- `/pm:status` : the board plus "Ready now: T004, T006".
- `/pm:audit src/api --cap 2` : two tickets with file:line evidence, the rest listed as not filed.

## This project

Print the `pm.py config` lines and the `doctor.sh` lines from step 1 under the heading "This project". When docs/pm is missing (doctor says pm=no), say that /pm:init sets it up.
Then one line: "Design page (open it in a browser): ${CLAUDE_PLUGIN_ROOT}/docs/blueprint.html".

## init

Detect (`pm_detect.sh`), audit an existing repo, interview one question at a time with a recommended answer, propose, write: roadmap, decisions, epics, starter tickets, the pm block in CONTEXT.md. Forks keep docs out of git through `.git/info/exclude`. Old planning docs move to docs/archive only after a yes. `--quick` takes every recommended answer.

## brainstorm

An open thinking session on a topic (or the board's gaps when none is given). Reads the repo, roadmap, epics, board and decisions first, then asks one question at a time with a recommended answer: problem and person, what exists, options with trade-offs, risks and non-goals, the first usable version. Intent questions only; an unknown fact becomes a `plan: required` design ticket. Ends with a `file | change | why` table (roadmap milestone or Backlog line, epic, thin ticket, decisions entry, a dismissed ticket, rarely the pm block) and one question: apply all, pick rows, or none. Writes only the accepted rows, tickets thin (`ready: no`), then asks once whether to grill them now. Without docs/pm the proposal feeds /pm:init. A run that cannot ask ends at the proposal and writes nothing, unless the user delegated the answers.

## plan

Kinds: milestone, epic, ticket, bug, idea, apply. Captures, does not interview: a ticket is written thin (`ready: no`) with a first draft of What and Acceptance from the user's words, then one hand-off question: grill it now (unblocked) or later (blocked). A bug with known reproduce steps is ready by its shape. `apply Txxx` walks through an agent's proposed changes: accept (a thin ticket), edit, or reject each.

## grill

One ticket (or every ungrilled ticket of an epic, unblocked first). Reads the repo, the epic, decisions and siblings first, then asks one question at a time with a recommended answer: What, Why, Acceptance lines proposed for you to accept or change, design choice (`plan: required`), priority and dependencies when the Flow suggests, auto. Intent questions only: a fact nobody knows yet becomes a `plan: required` design ticket instead of a guess. No testable acceptance means the ticket goes to the Backlog as an idea. Ends with `pm.py ready Txxx`; /pm:work takes only ready tickets. A blocked ticket is grilled after its dependency lands; grilled early, the board flags it for a re-check.

## work

Pick (named ticket or `pm.py next`), claim and commit the claim, branch, then plan: a `plan: required` ticket in an interactive session enters plan mode, you approve or reject at the exit, and the approved plan is copied into the ticket; any other ticket gets its `## Plan` section written directly. Then gates in order: tdd, checks, review, docs. Finish by flow: branch-pr opens a PR (merge asks unless `merge: auto`), branch-local merges locally, direct commits on the branch. The review gate runs two read-only agents at once, `pm:verifier` and `pm:reviewer` (Sonnet unless `review_model` says otherwise; an interactive session asks per ticket at the plan step), and fixes what they find. Bug tickets freeze their test files once the reproducing test is committed (`pm.py freeze`); a wrong test is unfrozen by a person with `pm.py unfreeze --reason`. `--routine`: only `auto: yes` tickets, at most `auto_cap`, never merges, never unfreezes, stops at the first failing gate or at review findings. Routine recipe: `templates/routine-cron.txt` and `templates/routine-github-actions.yml` in the plugin folder.

## status

`pm.py board` unchanged, then `pm.py validate` problems, then at most three lines: ready, stuck, next command. Forks get a backup copy under `${PM_BACKUP_DIR:-$HOME/.pm-backup}/<repo>/`.

## retro

Moves unfinished tickets (next milestone or Backlog), asks what to keep and change, writes a Retro block under the milestone in roadmap.md, updates the pm block, sets the next milestone as current, closes the host milestone when mirroring.

## audit

Runs the check command, then looks for failing tests, untested public code, error handling gaps, security smells, duplication, drift between docs and code. Files at most `--cap` tickets, each with file:line evidence and a confidence rating, never `auto: yes`, never edits code. A person rejects a finding with `pm.py dismiss Txxx --reason`.
