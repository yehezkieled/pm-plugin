---
name: work
description: Do one ticket end to end - claim it, branch, write a plan, tests first, build, run checks, review by two read-only agents, update docs, open a PR or merge, and report. Use when the user says pick up the next ticket, work on T012, fix the bug ticket about X, fix it (about a ticket), do the next task, implement the next item, continue the project work, keep going with the plan, or wants unattended routine work with --routine. Not for filing or recording new work (that is pm:plan) and not for only showing progress (that is pm:status).
argument-hint: "[Txxx] [--routine]"
---

# /pm:work

One ticket per run, one PR per ticket. Never widen a ticket: anything extra goes under `## Proposed changes` in the ticket file, for /pm:plan apply.

Scripts: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm.py" ...`. If python3 is missing, apply the same rules by reading and editing the markdown yourself.

Never write dates, deadlines, or effort guesses anywhere. The report says what remains, not when.

## 0. Settings

`pm.py config --json` gives the pm block: `flow` (branch-pr | branch-local | direct), `merge` (ask | auto), `gates`, `check` (the project's lint and test command), `auto_cap`, `review_model` (model for the two review agents; sonnet when the line is missing). If docs/pm is missing, stop and offer /pm:init.

Owner name for claims: `$PM_OWNER` if set, else `work-<ticket id in lower case>`. In routine mode always `routine-<ticket id in lower case>` (`pm.py next --routine` prints it); the plugin's gate hook refuses `git merge` and `gh pr merge` on a ticket with a `routine-` owner.

## 1. Pick

- `$ARGUMENTS` names a ticket: use it. It must be `todo`, or already claimed by this owner, and every ticket in its `depends_on` must be `done`. `pm.py claim` refuses a ticket with an open dependency: do not add `--force` for that, not even when the user said to skip questions; say which dependency is open, offer to do that ticket instead, and stop. If another owner holds it and its branch has commits, stop and say so. If its branch has no commits and that owner's session is gone, tell the user and take it over with `pm.py claim Txxx <owner> --force`.
- Otherwise `pm.py next` (`pm.py next --routine` in routine mode). It picks: status todo, `ready: yes`, every `depends_on` done, no owner; then highest priority; then earliest in the epic Flow. If it prints `none`, say what is blocked, claimed, or still to grill and stop; suggest /pm:grill for the tickets it lists as `to grill`, /pm:plan when there is nothing at all.
- A ticket that says `ready: no` was never grilled: `pm.py claim` refuses it and the plan gate blocks code on its branch. For `ready: no` never add `--force`, and never grill it yourself with your own answers: the flag means a person settled the ticket. Interactive session: say the ticket is not grilled and ask (AskUserQuestion) whether to grill it now; on yes invoke the `pm:grill` skill with its id and come back to this skill once it says `ready: yes`. Routine or headless run, or "no questions": say which ticket needs /pm:grill and stop.

Read the whole ticket file. If the acceptance is not testable or the What is unclear even though the ticket says `ready: yes`, stop and ask one question (routine mode: skip it, say why, pick the next).

## 2. Claim, then branch

1. `pm.py claim Txxx <owner>` sets `owner` and `status: in progress`, and prints the exact `next:` and `then:` commands for this project's flow. Run them as printed.
2. The `next:` line commits the claim on the main branch before branching so other agents see it (`git add docs/pm && git commit -m "pm: claim Txxx"`, plus `git push` in `branch-pr` flow). Do not skip the push: the claim must be on the remote main before the PR exists.
3. Branch (`branch-pr` and `branch-local`): `git switch -c txxx-<slug>`. A separate worktree is fine when the user works on several tickets at once. `direct`: stay on the current branch.

## 3. Plan (every ticket)

**Hard rule.** A `plan: required` ticket whose `## Plan` does not end with `approved: yes` gets no code edit in this run until the user approves the plan in this session, through plan mode or a question. "Do not ask me questions" is not an approval, and neither is a routine or headless run: in those cases write the plan, stop, and say the ticket waits for approval. `pm.py claim` prints a reminder when this applies, and the plugin's plan-gate hook blocks code edits on the ticket branch until the `## Plan` section is written and, for `plan: required`, approved. When the hook blocks you, do what its message says; never work around it.

Read-only look first: read the files the ticket touches, the tests around them, and `docs/pm/decisions.md`. No edits yet.

**`plan: required`, not yet approved, interactive session** (not `--routine`, and the EnterPlanMode tool is available):
1. Call EnterPlanMode. The session is now read-only until the plan is approved; the claim and the branch already exist, so nothing is lost.
2. Investigate, then write the plan with exactly these four labels: Approach, Touches, Tests first, Decisions to record.
3. Call ExitPlanMode. The user approves or rejects there. Rejected with feedback: adjust and exit again. Asked to stop: `pm.py release Txxx`, commit that, and end with a short report.
4. Approved: copy the plan into the ticket's `## Plan` section, set `approved: yes` on its last line, and continue with step 4.

**Every other case** (`plan: none`, or already approved, or routine mode, or no plan-mode tool): write the ticket's `## Plan` section directly, then continue (in an interactive session, through the questions below first). The plan stays in the ticket as the record.
```
Approach: how you will do it, in three lines at most
Touches: the files you expect to change
Tests first: the test names you will write, one per acceptance line
Decisions to record: anything a future reader would have to guess
approved: no
```
**Interactive session, any ticket that did not go through plan mode** (a person can answer; this includes `plan: none` tickets, since `plan:` only decides whether plan mode is used): before the first code edit, ask what the ticket leaves open, one AskUserQuestion call per question with a recommended answer first, at most three; then show the plan on one screen and ask to go ahead (go / change / stop). A ticket approved in plan mode is not asked again. Then, for every ticket in an interactive session, one more question: which model runs the review agents at the review gate, with the pm block's `review_model` preselected (Sonnet when the line is missing) and Opus as the other choice; pass the answer as the Agent tool's `model` when the review gate runs. Routine and headless runs skip all of these questions and take the default.

If plan mode is not available and the ticket is `plan: required` and not approved: write the `## Plan` section into the ticket first, then show it and ask with AskUserQuestion (approve / change / stop) before any edit. If no way to ask exists either (a headless run), stop after writing the plan and say the ticket waits for approval.

## 4. Build through the gates

Run only the gates listed in the pm block, in this order:

- **tdd**: for each acceptance line write a failing test first, run it and watch it fail, then the smallest code that passes. Tick `## Subtasks` boxes as you go. **Bug tickets** (title starts with `Bug:`): write the test that reproduces the bug, commit it, then `pm.py freeze Txxx` and commit that too. From here the plugin's gate refuses edits to test files until the ticket is done. When a test looks wrong, decide whose it is. This ticket's own test, meaning the reproduction you wrote or an old test that encoded the bug: say why, ask the user (AskUserQuestion), and on a yes run `pm.py unfreeze Txxx --reason "..."`, which records the reason under `## Notes`; then fix it in the same ticket. A test unrelated to the bug: leave it alone, file it as a new ticket (`pm.py new ticket --title "Bug: <test> is wrong: <why>" --epic Exx`, never `--auto`) and say so in the report. Headless and routine runs never lift a freeze: write the reason under `## Notes`, set `status=review`, and stop.
- **checks**: run the `check` command. It must pass. Fix what it reports, even when it is unrelated to the ticket, and say so in the report (on a frozen Bug ticket an unrelated failing test becomes a new ticket instead, see tdd).
- **review**: two read-only agents, started together with the Agent tool: `pm:verifier` (runs the check command, tests every acceptance line against the diff, flags widened scope) and `pm:reviewer` (hunts bugs, edge cases, error handling gaps, security holes, tests that prove nothing). Give each the ticket id and file path, the base branch, and the check command. Model: the pm block's `review_model` when set, else the agents' own default (sonnet). They fix nothing. Normal run: fix every finding inside the ticket's scope, re-run the check command, and put findings outside the scope under `## Proposed changes`. Routine mode: fix nothing; write the findings under `## Notes` and in the PR body, file each out-of-scope finding as its own ticket (`pm.py new ticket ... --confidence <high|medium|low>`, never `--auto`), set `status=review`, and stop the run there. No Agent tool in this session: review the diff yourself against the acceptance lines and say so in the report.
- **docs**: update README or docs that the change affects, tick the acceptance boxes, add what a future reader needs under `## Notes`, and add decisions to `docs/pm/decisions.md`. If the build departed from the `## Plan`, rewrite the plan's Approach and Touches to what was actually done and add one line under `## Notes` saying what changed and why.

A gate that fails and cannot be fixed: write what failed under `## Notes`, keep the branch, `pm.py release Txxx`, and stop with a clear report. Routine mode stops the whole run at the first failing gate.

## 5. Finish

`branch-pr`:
1. Commit the code and the ticket file. `pm.py set Txxx status=review`, commit, push.
2. `gh pr create --title "Txxx: <title>" --body "<acceptance lines, what changed, tests added>"`; add `Closes #<issue>` when the ticket has an `issue` number.
3. `pm.py set Txxx pr=<number>`, commit and push.
4. `merge: ask`: ask the user whether to merge now (AskUserQuestion); if you cannot ask, stop here and say the PR waits for the merge decision. `merge: auto`: `gh pr merge --squash --delete-branch` once checks pass. Routine mode never merges.
5. After the merge: `pm.py set Txxx status=done`, `pm.py flow <epic>`, `pm.py sync` when mirror is on (no python3: skip it and say the mirror is behind; the next sync catches up), commit on main.

`branch-local`: commit, `status=review`, then ask to merge (`merge: ask`) or merge yourself with `git switch main && git merge --no-ff txxx-<slug>` (`merge: auto`). After the merge set `status=done` and redraw the flow. Routine mode stops at `status=review` and never merges, whatever `merge` says.

`direct`: commit on the current branch, set `status=done`, redraw the flow. Routine mode sets `status=review` instead of done.

`merge: ask` means a person decides. If nothing in this session can ask (a headless run, no AskUserQuestion tool), stop after the PR or the review commit and say the ticket waits for the merge decision. "Do not ask me questions" is not a merge approval.

## 6. Report

Short and plain: ticket id and title, what changed, tests added, each gate's result, review findings (fixed, filed as tickets, or left for a person), PR link or branch name, proposed changes if any, and `pm.py line` for what is ready next.

## Routine mode (`--routine`)

Runs unattended, for example from a scheduler the project sets up itself.
- Take only tickets with `auto: yes` whose plan is `none` or approved (`pm.py next --routine` does this) and claim them as `routine-<id>`.
- Do at most `auto_cap` tickets in one run, one PR each.
- Never ask questions, never merge, never lift a test freeze. Stop at the first failing gate, and after the review gate's findings (status=review, findings under Notes, out-of-scope ones filed as tickets).
- End with one line per ticket: id, PR or branch, gate results.
