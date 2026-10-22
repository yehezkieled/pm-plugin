# Skill-routing evals

67 single-turn cases: a tuning set of 50 (4 per skill, plus `init-5` and `map-5` for the ICM structure triggers; 12 near-miss prompts; 8 non-pm prompts) and a held-out set of 17 (`held-*`, tag `held-out`). Each case pre-approves only the `Skill` tool (`allowed_tools: [Skill]`); the model can still use read-only built-ins such as Glob, but only its **first** Skill call is graded: it must be the expected `pm:*` skill, or no pm skill for the non-pm prompts. Later chained calls (e.g. plan then init) are not counted. `near-10-init` ("set up pm here, we already have a TODO.md") accepts `pm:init` or `pm:migrate`, since init hands off to migrate. Migration cases are `migrate-*`, `held-11-migrate`, `held-12-migrate`; near misses that must not route to migrate (`near-9-plan`, `near-11-work`) and non-pm "migrate" prompts (`none-6`, `none-7`, `held-13-none`) guard against over-triggering. The ICM cases are `init-5`, `map-5`, `held-15-init` ("ICM this repo"), `held-16-map` (what a change would affect), `held-17-init` (a workflow to package as a skill), `near-12-plan` (a task *about* restructuring, which is plan, not init), and `none-8` ("what is ICM?", which needs no pm skill).

Run (about $0.15-4.5 per model):

    claude plugin eval . --model claude-sonnet-5-5 --ablation none --trust-plugin -j 4 --no-publish

The pre-`migrate` skill descriptions were tuned on the original 37 tuning cases (the `migrate` description was written once and not adjusted after any run): the last description round borrowed wording from the prompts Haiku missed. So tuning-set gains were measured on the same prompts the descriptions were tuned on and are optimistic. The held-out cases were written afterwards as fresh paraphrases. The held-out numbers are the honest signal.

Results (1 run per case, full suite of 67, committed descriptions, run on 2026-10-22 after the ICM change to the `init` and `map` descriptions):

| Model | Tuning set (50) | Held-out set (17) |
|---|---|---|
| Haiku 5.5 | 50/50 | 14/17 |
| Sonnet 5.5 | 50/50 | 17/17 |
| Opus 5.5 | 49/50 | 17/17 |

| Model | Set | Prompt | Expected |
|---|---|---|---|
| Haiku 5.5 | held-out | `held-1-help`, `held-14-plan`, `held-6-map` | help, plan, map |
| Opus 5.5 | tuning | `none-8` ("what is ICM, the interpretable context methodology?") | no pm skill; Opus called `pm:help` in 2 of 3 re-runs, defensible now that pm ships the method, and the descriptions were not tuned to it |

Notes from this round:

- The first ICM `map` description dropped "with diagrams" and "architecture overview". `held-6-map` ("give me a high-level overview of this repo's structure with a diagram") then fell to 0/3 on Sonnet against 2/3 with the 1.0 description, so that 1.0 wording was restored. Since the change was made after seeing a held-out result, `held-6-map` is no longer a clean held-out case; `held-15` to `held-17` were written before any run and the descriptions were not changed after seeing them.
- Haiku 4.5 now sends "work on…" prompts to `pm:status` first: 0/24 on the 8 work cases at 3 runs each, with both this round's descriptions and `main`'s, so it is drift in the model or harness since 2026-10-01 rather than a description change. Haiku 5.5 routes the same 24 runs correctly, so the table now uses Haiku 5.5. Haiku 4.5 on the full suite scored 52/67.

Results on 2026-10-01 (60 cases, after adding `migrate`): Haiku 4.5 45/46 tuning and 11/14 held-out (misses `held-1-help`, `held-2-plan`, `held-14-plan`, `help-3`), Sonnet 5.5 46/46 and 12/14 (`held-14-plan`, `held-6-map`; a re-run gave `held-6-map` 6/6 and `held-14-plan` 1/3), Opus 5.5 46/46 and 14/14. A "note that..." prompt with no "remember" or "add" (`held-14-plan`) is the weakest plan phrasing, and results are noisy at 1 run per case.

Earlier results, before `migrate` (47 cases): Haiku 35/37 tuning and 8/10 held-out, Sonnet and Opus 37/37 and 10/10. Haiku's tuning-set gains came from a last description round that borrowed wording from prompts it had missed, so tuning-set numbers are optimistic; the held-out numbers are the honest signal.
