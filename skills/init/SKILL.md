---
name: init
description: Set up project management for a repo, new or existing, any size, forks included. Use when the user wants to start tracking work, organise or structure a project, set up milestones, epics and tickets, plan a new project from scratch, or asks how to manage the work in this repo. Runs a short interview (one question at a time, with a recommended answer) and then creates docs/pm plus a pm block in CONTEXT.md.
argument-hint: "[--quick]"
---

# /pm:init

Set up the four-level work structure for this repo:

```
milestone -> epic -> ticket -> subtask
docs/pm/roadmap.md         milestones in order, plus Backlog
docs/pm/epics/Exx-slug.md  goal, ticket list, dependency Flow
docs/pm/tickets/Txxx-slug.md  the unit of work; subtasks are a checklist inside
docs/pm/decisions.md       decisions a future reader would otherwise guess
CONTEXT.md  ## pm block    how this project works (flow, gates, check command)
```

Rules that apply to everything below:
- Never ask for, write, or suggest a deadline, target date, or how long anything takes. Milestones are ordered versions.
- Do not ask what you can find out by reading the repo.
- Do not overwrite an existing docs/pm. If it exists, say so and offer /pm:status.
- Scripts: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm.py" ...`. If python3 is missing, do the same work by hand from the templates in `${CLAUDE_PLUGIN_ROOT}/templates/`.

## 1. Detect

Run and read the facts:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/pm_detect.sh"
```

Keys: git, host (github | gitlab | other | none), remote, branch, fork, commits, files, languages, check_guess, readme, context_md, claude_md, planning_docs, pm, flow_suggest, python3, gh.

If `pm=yes`: stop here, tell the user pm is already set up, and offer /pm:status or /pm:plan.

## 2. Audit (existing repos: commits > 0 or files > 0)

Read README, CONTEXT.md or CLAUDE.md if present, the top-level layout, the test setup, and every file listed in `planning_docs`. Write a short summary (five lines at most): what the project is, what already exists, how it is tested, what old planning material exists. This summary is what you use to skip questions.

## 3. Interview

Ask one question at a time: one AskUserQuestion call per question, never several questions bundled in one call. Each question comes with a recommended answer (listed first) and why. If AskUserQuestion is not available, ask in plain text and wait. Skip any question the audit already answered. Stop as soon as you can state the goal, the first milestone, its epics, the flow, and the gates without guessing.

Questions, in this order:

1. **First usable version.** "What does M1 do for its user when it is done?" One sentence. This becomes the M1 goal.
2. **Big pieces.** "What are the two to five pieces of work needed for M1?" Each becomes an epic. Recommend a split based on the audit.
3. **Git flow.** Recommend `flow_suggest`: `branch-pr` when there is a remote host, `branch-local` when git has no remote, `direct` when there is no git at all or the user wants to commit straight to the branch.
4. **Mirror.** Only when host=github and gh=yes: "Mirror milestones, epics, and tickets to GitHub issues (one way, markdown stays the source)?" Recommend on, except for forks (recommend off).
5. **Gates.** Recommend all four: tdd, checks, review, docs. Ask which one does not fit this project and why. Write only the ones that stay.
6. **Check command.** Recommend `check_guess`. Confirm or take the project's own lint and test command.
7. **Old planning docs.** When `planning_docs` is not empty: "Move these into docs/archive/ so docs/pm is the single place, or leave them where they are?" Recommend archive. Move only after a yes.
8. **Fork.** When fork=yes: propose keeping docs/pm and CONTEXT.md out of git through `.git/info/exclude` and mirror off, so upstream never sees them. A backup copy is made on every /pm:status run.

Also ask, once, how the first tickets should be handled: create one to three starter tickets per epic now (recommended for small projects), or leave epics empty and add tickets with /pm:plan.

With `--quick` in $ARGUMENTS: skip the interview, take every recommended answer, and print the answers so the user can change them after.

## 4. Propose

Show the plan as text before writing anything:
- the pm block that will go into CONTEXT.md
- M1 title and goal
- epics with one-line goals
- starter tickets (id, title, epic, priority, depends_on) if any
- what happens to old planning docs

Wait for a yes (not with `--quick`).

## 5. Write

1. `docs/pm/roadmap.md` from `${CLAUDE_PLUGIN_ROOT}/templates/roadmap.md` with the M1 title and goal. Backlog holds the ideas that came up but are not in M1.
2. `docs/pm/decisions.md` from the template. First entry: this project uses the pm layout. Add one entry per decision the interview settled (flow, mirror, gate exceptions).
3. Epics: `pm.py new epic --title "<title>" --milestone M1 --goal "<goal>"` for each.
4. Starter tickets: `pm.py new ticket --title "<title>" --epic Exx --priority P1 [--depends Txxx] [--plan required]`, then edit each file and replace every bracketed placeholder: What (one paragraph), Why (one or two lines), Acceptance (one testable line per item), the first Subtask. `pm.py validate` reports any placeholder left behind. A ticket that is a design choice gets `plan: required`. Starter tickets stay `ready: no`: you drafted them, the user has not grilled them, and /pm:work takes a ticket only after /pm:grill marks it ready.
5. `CONTEXT.md`: create it if missing (one-line project description, where the code and tests live, how to run checks), then add the `## pm` block by copying `${CLAUDE_PLUGIN_ROOT}/templates/context-pm-block.md` and replacing only the `{{placeholders}}`. The block must stay plain `key: value` lines, one per line, with exactly those keys, because the scripts parse it: no bold, no bullets, no prose inside the block. Keep any existing text of the file.
6. Forks: append `docs/pm/` and, when it is new, `CONTEXT.md` to `.git/info/exclude`.
7. Archive: `git mv` the old planning docs into `docs/archive/` only if the user said yes.
8. `pm.py flow --all`, then `pm.py validate`. Fix anything it reports.
9. Mirror on: run `pm.py sync --dry-run`, show it, and run `pm.py sync` after a yes.
10. Ask whether to commit the new files now (`pm: set up project management docs`). Do not commit without a yes. Forks: nothing to commit.

## 6. Report

Print the board (`pm.py board`) and end with four lines: how to add work (/pm:plan ticket), how to get the first ticket ready (/pm:grill Txxx, naming the first one in the Flow), how to start once a ticket is ready (/pm:work), where the cheat sheet is (/pm:help).
