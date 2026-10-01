# Skill-routing evals

60 single-turn cases: a tuning set of 46 (4 per skill including `migrate`, 11 near-miss prompts, 7 non-pm prompts) and a held-out set of 14 (`held-*`, tag `held-out`). Each case pre-approves only the `Skill` tool (`allowed_tools: [Skill]`); the model can still use read-only built-ins such as Glob, but only its **first** Skill call is graded: it must be the expected `pm:*` skill, or no pm skill for the non-pm prompts. Later chained calls (e.g. plan then init) are not counted. `near-10-init` ("set up pm here, we already have a TODO.md") accepts `pm:init` or `pm:migrate`, since init hands off to migrate. Migration cases are `migrate-*`, `held-11-migrate`, `held-12-migrate`; near misses that must not route to migrate (`near-9-plan`, `near-11-work`) and non-pm "migrate" prompts (`none-6`, `none-7`, `held-13-none`) guard against over-triggering.

Run (about $2-4.5 per model):

    claude plugin eval . --model claude-sonnet-5-5 --ablation none --trust-plugin -j 4 --no-publish

The pre-`migrate` skill descriptions were tuned on the original 37 tuning cases (the `migrate` description was written once and not adjusted after any run): the last description round borrowed wording from the prompts Haiku missed. So tuning-set gains were measured on the same prompts the descriptions were tuned on and are optimistic. The held-out cases were written afterwards as fresh paraphrases, and the descriptions were not changed after seeing their results. The held-out numbers are the honest signal.

Results (1 run per case, full suite of 60, committed descriptions, run on 2026-10-01 after adding `migrate`):

| Model | Tuning set (46) | Held-out set (14) |
|---|---|---|
| Haiku 4.5 | 45/46 | 11/14 |
| Sonnet 5.5 | 46/46 | 12/14 |
| Opus 5.5 | 46/46 | 14/14 |

Every migration prompt (the 4 tuning cases, both held-out ones, and all near-miss and non-pm "migrate" prompts) routed correctly on all three models. The misses are in the older routing classes:

| Model | Set | Prompt | Expected |
|---|---|---|---|
| Haiku | held-out | `held-1-help`, `held-2-plan`, `held-14-plan` ("note that we should migrate off Node 18 before the end of the quarter") | help, plan, plan |
| Haiku | tuning | `help-3` | help |
| Sonnet | held-out | `held-14-plan` | plan |
| Sonnet | held-out | `held-6-map` | map |

Traces for the full-suite misses were not kept. Re-running Sonnet alone gave `held-6-map` 6/6 correct (its miss in the full run was a one-off), and `held-14-plan` 1/3 on one re-run: a "note that..." prompt with no "remember" or "add" is the weakest plan phrasing. It is a held-out prompt, so the descriptions were not tuned to it. Across runs Haiku still sometimes answers help-style and "for later" prompts directly instead of calling a skill, and results are noisy at 1 run per case.

Earlier results, before `migrate` (47 cases): Haiku 35/37 tuning and 8/10 held-out, Sonnet and Opus 37/37 and 10/10. Haiku's tuning-set gains came from a last description round that borrowed wording from prompts it had missed, so tuning-set numbers are optimistic; the held-out numbers are the honest signal.
