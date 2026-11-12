# Skill-routing evals

64 single-turn cases: a tuning set of 49 (4 per skill, plus `init-5` and `map-5` for the ICM structure triggers and `work-5` and `work-6` for project work that is not phrased as a board task; 13 near-miss prompts; 8 non-pm prompts) and a held-out set of 15 (`held-*`, tag `held-out`). Each case pre-approves only the `Skill` tool (`allowed_tools: [Skill]`); the model can still use read-only built-ins such as Glob, but only its **first** Skill call is graded: it must be the expected `pm:*` skill, or no pm skill for the non-pm prompts. Later chained calls (e.g. plan then init) are not counted. `near-10-init` ("set up pm here, we already have a TODO.md") must route to `pm:init`. Prompts that say "migrate" about the project itself (`near-9-plan`, `near-11-work`, `none-6`, `none-7`, `held-13-none`) guard against over-triggering. The ICM cases are `init-5`, `map-5`, `held-15-init` ("ICM this repo"), `held-16-map` (what a change would affect), `held-17-init` (a workflow to package as a skill), `near-12-plan` (a task *about* restructuring, which is plan, not init), and `none-8` ("what is ICM?", which needs no pm skill). Since 1.2 any project work goes through `/pm:work`: `work-5` (analyse refund data and write it up) and `work-6` (the redesign study's Endeavour memo prompt, so not a clean held-out case) must route to `pm:work`, and `near-13-plan` ("remember to write up ... next week") stays `pm:plan`. The non-pm prompts that are changes to the project (`none-1` a README typo, `none-6` a schema migration, `none-7` a config conversion, `held-9-none` a rename, `held-13-none` a framework port) now accept `pm:work` or no skill, and still fail on any other pm skill (`graders/no-board-skill.md`), so they keep guarding the board skills against over-triggering. The rest (questions, a generic snippet, running the tests) still take no pm skill.

Run (about $0.15-4.5 per model):

    claude plugin eval . --model claude-sonnet-5-5 --ablation none --trust-plugin -j 4 --no-publish

The pre-`migrate` skill descriptions were tuned on the original 37 tuning cases (the `migrate` description was written once and not adjusted after any run): the last description round borrowed wording from the prompts Haiku missed. So tuning-set gains were measured on the same prompts the descriptions were tuned on and are optimistic. The held-out cases were written afterwards as fresh paraphrases. The held-out numbers are the honest signal.

Results (1 run per case, full suite of 70, 1.2 descriptions, run on 2026-11-05). 1.6 removed `/pm:migrate` and its 6 cases (`migrate-1` to `migrate-4`, `held-11-migrate`, `held-12-migrate`), none of them among the misses below; the suite of 64 has not been run since:

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
| `work-waits-holds` | extend the reconciliation to a distributor whose data is not in the repository | the work goes on the board and is held with the question (`pm.py hold`) by the worker session, the session relays the question, and no tariff data is invented |
| `work-two-workers` | "work on both ready items" with two independent items on a small Python library's board | two worker sessions started with `pm.py worker start`, each in its own worktree, each claiming its item and starting its own `pm:validator`, both Done with a pass on their branches, and no edit or subagent by the session itself |
| `work-asks-settings` | "work on the word count item" on a board set up before 1.4 | no worker starts and nothing is recorded; the reply asks the worker model and effort and the permission setting, recommending auto (since 1.6 the validator follows the worker unless the person sets it apart) |
| `validate-catches-bad` | ask `pm:validator` to check a work branch whose `word_count` fails its own tests and leaves a notes file at the root | the verdict is findings naming both problems; nothing is edited |
| `validate-passes-good` | the same check on a correct branch | the verdict is a pass with no invented findings; nothing is edited |

Each item is done by a separate worker session (since 1.5 a full background session started with `claude --bg`), whose calls are not in the coordinating session's trace. The work cases grade that the session started it (`tool_used: Bash` matching `pm.py ... worker start`), made no edit and started no subagent (`main-made-no-edits.md`, `no-subagent-work.md`, `regex` on the trace), and read the worker's side from what the CLI keeps: `work-two-workers` reads each worker's session record in `.git/pm-workers/sessions/` (`regex` with a file target), and every case reads the report `pm.py worker` prints into the trace, whose `Its board commands this turn:` and `On branch pm/<id>:` lines come from the worker's session transcript and git, not from the worker's own words. The scaffolds record exact model versions, as the CLI requires since 1.5. The scaffolds of the work cases record the person's earlier choices (worker and validator defaults in `docs/pm/config.json`, `auto` in `.git/pm-workers/settings.json`); `work-asks-settings` has none.

Run them with:

    PM_WORKER_EXTRA_ARGS='--setting-sources project' claude plugin eval . --eval-dir evals-behavior --model claude-sonnet-5-5 --ablation none --trust-plugin --scaffold --allow-tools Bash Write Edit Agent --no-publish

`PM_WORKER_EXTRA_ARGS` passes extra flags to every worker session `pm.py worker` starts; here it keeps the machine's user settings and hooks out of the workers as the eval keeps them out of the session.

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

Results on 2026-11-10/11 for 1.4 (worker sessions), Sonnet 5.5 for the session, the workers, and the validators, 1 run per case. The machine still lacked `socat`, so each case ran the direct way: its `scaffold.sh` in a fresh scratch repository, then `claude -p "<prompt>" --plugin-dir . --setting-sources project --permission-mode auto --output-format stream-json --verbose` with `PM_WORKER_EXTRA_ARGS='--setting-sources project'`, and the case's graders applied to the files, the session records, and the trace (the `llm` graders by reading the reply). A headless session that started worker sessions in the background stays running until they end, then reports.

| Case | Result |
| --- | --- |
| `work-two-workers` | pass: two `pm.py worker start` calls in one message, two worker sessions started in the same second, each in `.claude/worktrees/pm-<id>/`, each claiming its item and starting its own validator; both branches Done with a recorded pass; the session made no edit and started no subagent. One worker's first validator recorded no verdict, so it ran a second, which passed |
| `work-memo-places` | pass: one worker session in the person's checkout moved the price list to `data/raw/endeavour/` under its own name, extended the reconciliation, wrote `reports/2026-11-11-endeavour-aer-discrepancies.md`, validated (pass) and finished; nothing new at the root |
| `work-waits-holds` | pass: the worker session claimed and held the item with the question (its board commands, read from its log: `claim, hold`); the session relayed one question with a recommendation and invented no rates |
| `work-asks-settings` | pass: no worker started and nothing recorded; the reply asked the worker and validator model and effort and the permission setting, recommending auto |
| `init-ordinary-cold-walk` | pass: app shape, table, both walk halves with the cold answers; the worker and validator defaults asked in the reply, not picked |
| `init-analysis-places` | pass: analysis shape, CSVs in `data/raw/<source>/`, the generated output out of Git, `data/README.md`; defaults asked in the reply |
| `validate-catches-bad` | pass: `VERDICT: findings` naming the `split(" ")` bug, its 2 failing tests, and `wordcount-notes.md` at the root; nothing edited |
| `validate-passes-good` | pass: `VERDICT: pass`, 4 tests OK, no invented findings; nothing edited |

The same round was also driven by hand through an interactive session in a terminal, the way a person uses it: on first `/pm:work` the session asked the three choices through its question prompt and recorded them, ran two items in two worker sessions at once, and reported both. In the hold case, the session relayed the worker's question, saved the answer with `resume --answer`, and sent it with `pm.py worker answer`: the same session ID (`claude -p --resume`) took up the work with its context and finished it after a validator pass. That session first tried `worker start --resume`, which the CLI refused with a pointer to `worker answer`; `/pm:work` step 4 now says `worker start` is only for an item with no session.

1.5 (interactive worker sessions) has not been run through these cases yet. On 2026-11-11 its terminal path was run with real sessions in a throwaway repository with no remote (Claude Code 2.1.322, Haiku 5.5 workers, `auto`):

| Run | Result |
| --- | --- |
| `worker start` on one item | background session started in its own worktree; report recorded with `claim, finish; validator subagents started: 1`; Done on `pm/<id>`; worktree removed, session closed |
| `worker answer` to that finished worker | worktree put back on the branch; same session ID continued and recalled its first turn |
| A worker told to stop first, then given the go-ahead | go-ahead handed over by the Stop hook: `auto` refused the claim. Sent as the session's next prompt: claimed, built, validated, Done |
| Validator set to another exact version than the family's newest | the validator subagent ran on that exact version (`CLAUDE_CODE_SUBAGENT_MODEL` in the session's settings) |
| A handed-over item, its session opened by hand in a terminal | the first message arrived by itself (SessionStart hook); claimed, built, validated, Done; a later message was delivered into the open session; its copy was kept until that session closed |
| The worker commands under Windows Python and Windows git, no session | board, defaults, handover with backslash paths, the hooks, the mailbox, and remove all worked |

Not run: the Claude app path (checklist in `docs/manual.md` › 2.6).
