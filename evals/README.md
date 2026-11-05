# Skill-routing evals

70 single-turn cases: a tuning set of 53 (4 per skill, plus `init-5` and `map-5` for the ICM structure triggers and `work-5` and `work-6` for project work that is not phrased as a board task; 13 near-miss prompts; 8 non-pm prompts) and a held-out set of 17 (`held-*`, tag `held-out`). Each case pre-approves only the `Skill` tool (`allowed_tools: [Skill]`); the model can still use read-only built-ins such as Glob, but only its **first** Skill call is graded: it must be the expected `pm:*` skill, or no pm skill for the non-pm prompts. Later chained calls (e.g. plan then init) are not counted. `near-10-init` ("set up pm here, we already have a TODO.md") accepts `pm:init` or `pm:migrate`, since init hands off to migrate. Migration cases are `migrate-*`, `held-11-migrate`, `held-12-migrate`; near misses that must not route to migrate (`near-9-plan`, `near-11-work`) and non-pm "migrate" prompts (`none-6`, `none-7`, `held-13-none`) guard against over-triggering. The ICM cases are `init-5`, `map-5`, `held-15-init` ("ICM this repo"), `held-16-map` (what a change would affect), `held-17-init` (a workflow to package as a skill), `near-12-plan` (a task *about* restructuring, which is plan, not init), and `none-8` ("what is ICM?", which needs no pm skill). Since 1.2 any project work goes through `/pm:work`: `work-5` (analyse refund data and write it up) and `work-6` (the redesign study's Endeavour memo prompt, so not a clean held-out case) must route to `pm:work`, and `near-13-plan` ("remember to write up ... next week") stays `pm:plan`. The non-pm prompts that are changes to the project (`none-1` a README typo, `none-6` a schema migration, `none-7` a config conversion, `held-9-none` a rename, `held-13-none` a framework port) now accept `pm:work` or no skill, and still fail on any other pm skill (`graders/no-board-skill.md`), so they keep guarding `migrate` and the board skills against over-triggering. The rest (questions, a generic snippet, running the tests) still take no pm skill.

Run (about $0.15-4.5 per model):

    claude plugin eval . --model claude-sonnet-5-5 --ablation none --trust-plugin -j 4 --no-publish

The pre-`migrate` skill descriptions were tuned on the original 37 tuning cases (the `migrate` description was written once and not adjusted after any run): the last description round borrowed wording from the prompts Haiku missed. So tuning-set gains were measured on the same prompts the descriptions were tuned on and are optimistic. The held-out cases were written afterwards as fresh paraphrases. The held-out numbers are the honest signal.

Results (1 run per case, full suite of 70, 1.2 descriptions, run on 2026-11-05):

| Model | Tuning set (53) | Held-out set (17) |
|---|---|---|
| Haiku 5.5 | 52/53 | 12/17 |
| Sonnet 5.5 | 52/53 | 17/17 |
| Opus 5.5 | 52/53 | 17/17 |

| Model | Set | Prompt | Expected |
|---|---|---|---|
| Haiku 5.5 | held-out | `held-1-help`, `held-2-plan`, `held-6-map`, `held-15-init`, `held-16-map` | help, plan, map, init, map |
| Haiku 5.5 | tuning | `near-7-plan` | plan (3/3 on re-run) |
| Sonnet 5.5 | tuning | `work-6` | work (1/3 on re-run) |
| Opus 5.5 | tuning | `none-8` ("what is ICM, the interpretable context methodology?") | no pm skill; Opus calls `pm:help`, 3/3 on re-run and 1/3 with `main`'s descriptions |

Sonnet's `near-5-init` run died on a Claude Code self-update mid-suite (`EACCES` spawning the binary) and passed 3/3 on re-run, so it is counted as passed. Opus sent `none-6` to `pm:work`, which the 1.2 grader accepts (3/3 on re-run; `main`'s descriptions sent it to no skill 3/3).

1.2 against `main`'s descriptions, 3 runs per case on the same day, for the cases the 1.2 change could move:

| Model | Cases | `main` | 1.2 |
|---|---|---|---|
| Haiku 5.5 | held-out set | 39/51 | 42/51 |
| Haiku 5.5 | `work-5` / `work-6` | 0/3 / 0/3 | 2/3 / 0/3 |
| Haiku 5.5 | `work-1` to `work-4`, `near-7-plan`, `none-1` | 18/18 | 18/18 |
| Sonnet 5.5 | `work-5` / `work-6` | 0/3 / 0/3 | 3/3 / 1/3 |
| Sonnet 5.5 | `work-1` to `work-4`, `near-5-init`, `near-13-plan`, `none-1` | 21/21 | 21/21 |

Haiku's held-out misses move between runs rather than tracking the change: at 3 runs, `held-15-init` passed 3/3 with both, `held-6-map` and `held-1-help` went from 0/3 with `main` to 1/3 with 1.2, `held-16-map` from 1/3 to 0/3, and `held-2-plan` from 1/3 to 3/3. `work-6` stays weak because, in this single-turn harness, models open files to explore before any skill call. In the behavior cases below, where the session-start hook says that project work goes through `pm:work`, Sonnet called `pm:work` first on both work prompts, the memo prompt included.

Results on 2026-10-22 (67 cases): Haiku 5.5 50/50 tuning and 14/17 held-out (misses `held-1-help`, `held-14-plan`, `held-6-map`), Sonnet 5.5 50/50 and 17/17, Opus 5.5 49/50 and 17/17 (`none-8`). That round's first ICM `map` description dropped "with diagrams" and "architecture overview", and `held-6-map` ("give me a high-level overview of this repo's structure with a diagram") fell to 0/3 on Sonnet, so the 1.0 wording was restored; since that change followed a held-out result, `held-6-map` is no longer a clean held-out case. Haiku 4.5 sends "work on…" prompts to `pm:status` first (0/24 at 3 runs each, with both that round's descriptions and the previous ones), drift in the model or harness rather than a description change, so the tables use Haiku 5.5.

Results on 2026-10-01 (60 cases, after adding `migrate`): Haiku 4.5 45/46 tuning and 11/14 held-out (misses `held-1-help`, `held-2-plan`, `held-14-plan`, `help-3`), Sonnet 5.5 46/46 and 12/14 (`held-14-plan`, `held-6-map`; a re-run gave `held-6-map` 6/6 and `held-14-plan` 1/3), Opus 5.5 46/46 and 14/14. A "note that..." prompt with no "remember" or "add" (`held-14-plan`) is the weakest plan phrasing, and results are noisy at 1 run per case.

Earlier results, before `migrate` (47 cases): Haiku 35/37 tuning and 8/10 held-out, Sonnet and Opus 37/37 and 10/10. Haiku's tuning-set gains came from a last description round that borrowed wording from prompts it had missed, so tuning-set numbers are optimistic; the held-out numbers are the honest signal.

## Behavior evals

`evals-behavior/` holds multi-turn cases that run a skill end to end in a scaffolded repository and grade what it did, kept apart so the routing run above stays cheap and needs no tool grants. The tariff-check fixtures come from the 2026-11 redesign study, whose scenario runs showed agents writing to the wrong files and leaving work off the board.

| Case | Prompt | Checks |
| --- | --- | --- |
| `init-ordinary-cold-walk` | `/pm:init` on a small Python library | a `## Where things go` table in `AGENTS.md`; the reply reports both halves of the walk test, one cold-walk answer per question; the app shape, no stage folders |
| `init-analysis-places` | set up pm on a loose data analysis, with the yes given up front | the analysis shape and its table; the source CSVs moved into `data/raw/<source>/`, a `data/README.md`, no new CSV at the root |
| `work-memo-places` | add a price list dropped at the root, extend the reconciliation, write the memo | the data moved to `data/raw/<source>/` with its name kept, the memo in `reports/`, nothing new at the root, the work added to the board and claimed, finished after it was committed |
| `work-waits-holds` | extend the reconciliation to a distributor whose data is not in the repository | the work goes on the board and is held with the question (`pm.py hold`) by the worker, the session relays the question, and no tariff data is invented |
| `work-two-workers` | "work on both ready items" with two independent items on a small Python library's board | two `pm:worker` agents, each started with `isolation: "worktree"`, two claims, a `pm:validator` per item, and no edit by the session itself |
| `validate-catches-bad` | ask `pm:validator` to check a work branch whose `word_count` fails its own tests and leaves a notes file at the root | the verdict is findings naming both problems; nothing is edited |
| `validate-passes-good` | the same check on a correct branch | the verdict is a pass with no invented findings; nothing is edited |

Since 1.3 the coordinating session does no project work itself: `work-memo-places`, `work-waits-holds`, and `work-two-workers` also grade that a `pm:worker` did the work (`tool_used: Agent` with `"subagent_type":"pm:worker"`) and that the session made no edit (`main-made-no-edits.md`, a `regex` on the trace: a main-session message has `"parent_tool_use_id":null`, a subagent's carries the id of the Agent call that started it). `tool_used` counts subagents' calls too, so the claim, hold, and finish graders still see the worker's Bash calls; `held-by-the-worker.md` checks the hold came from a subagent. A worker's own call to `pm:validator` shows in the trace; the validator's calls do not.

Run them with:

    claude plugin eval . --eval-dir evals-behavior --model claude-sonnet-5-5 --ablation none --trust-plugin --scaffold --allow-tools Bash Write Edit Agent --no-publish

The Bash grant runs inside Claude Code's shell sandbox, which on Linux needs `bubblewrap` and `socat` installed; without them the run refuses to start rather than run unconfined.

Results on 2026-11-05, Sonnet 5.5, 1 run per case. The machine lacked `socat`, so each case ran as the study's scenarios did: its `scaffold.sh` in a fresh scratch repository, then `claude -p "<prompt>" --plugin-dir . --setting-sources project --dangerously-skip-permissions`, with the case's graders applied to the files and trace by hand.

| Case | Result |
| --- | --- |
| `init-ordinary-cold-walk` | pass: the app shape, a table with the real `src/tinyslug/` and `tests/`, both walk halves with one cold answer per question |
| `init-analysis-places` | pass on the third run. The first left the generated `discrepancies.csv` tracked inside the gitignored `out/`, and the second renamed `explore.ipynb` to a dated name it invented. `/pm:init` and `icm/shapes.md` now say that a generated output leaves Git as it moves and that a moved file keeps its name; the third run did both |
| `work-memo-places` | pass, twice: `pm:work` called first, the item added and claimed, the price list moved to `data/raw/endeavour/` under its own name, the memo in `reports/`. In the first run `finish` was refused with 5 files uncommitted, the agent committed them, and `finish` then succeeded; that memo carried the data's year (2025) in its name, so `icm/shapes.md` now says to date a file the day it is written, and the second run named it `2026-11-05-…` and committed before `finish` |
| `work-waits-holds` | pass: `pm:work` called first, the item added, claimed, and held with the question asking for Essential Energy's price list, no rates invented |

Results on 2026-11-06 for 1.3 (coordinator, `pm:worker`, `pm:validator`), Sonnet 5.5, 1 run per case, run the same direct way; every Agent, Edit, and Write call in the trace was attributed to the main session or a subagent by its `parent_tool_use_id`.

| Case | Result |
| --- | --- |
| `work-two-workers` | pass, twice: the session started two `pm:worker` agents in one message, each with `isolation: "worktree"`; each claimed its own item, had its own `pm:validator` (pass, 1 round each), and finished on `pm/<id>`; the session's only tool calls were `pm.py next`, `pm.py board`, and `git log`/`git show`. Both runs' replies flagged that the two branches edit the same files, so the second merge conflicts |
| `work-memo-places` | pass on the third run. In the first two the work was right and the session made no edits, but it split the request in two: the session filed two items, the second depending on the first, so the memo waited for a merge (in the first run), or one worker did both under one item while the file graders read the person's checkout, which stayed on the start branch (in the second). `/pm:work` now keeps one request as one item and a lone worker leaves the person on its finished branch; the third run moved the data under its own name, wrote `reports/2026-11-06-…md`, validated (pass, 1 round), and finished |
| `work-waits-holds` | pass, twice: the worker claimed, found no Essential Energy price list, switched back, and ran `pm.py hold` with the question (from a subagent, per `held-by-the-worker`); the session relayed it as one question with options and invented no rates. The second run noticed the item's requester intent was empty because the session had added a one-line request; `pm.py add` now saves a lone line as its own intent |
| `validate-catches-bad` | pass: `VERDICT: findings`, naming the `split(" ")` bug with the 2 failing tests by name and `wordcount-notes.md` at the root against the table; nothing edited |
| `validate-passes-good` | pass: `VERDICT: pass`, 4 tests OK, no invented findings; nothing edited |
