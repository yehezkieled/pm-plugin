# Skill-routing evals

47 single-turn cases: a tuning set of 37 (4 per skill, 8 near-miss prompts, 5 non-pm prompts) and a held-out set of 10 (`held-*`, tag `held-out`). Each case pre-approves only the `Skill` tool (`allowed_tools: [Skill]`); the model can still use read-only built-ins such as Glob, but only its **first** Skill call is graded: it must be the expected `pm:*` skill, or no pm skill for the non-pm prompts. Later chained calls (e.g. plan then init) are not counted.

Run (about $1.5-3.5 per model):

    claude plugin eval . --model claude-sonnet-5-5 --ablation none --trust-plugin -j 4 --no-publish

The skill descriptions were tuned on the 37 tuning cases: the last description round borrowed wording from the prompts Haiku missed. So tuning-set gains were measured on the same prompts the descriptions were tuned on and are optimistic. The held-out cases were written afterwards as fresh paraphrases, and the descriptions were not changed after seeing their results. The held-out numbers are the honest signal.

Results (1 run per case, full suite, committed descriptions):

| Model | Tuning set | Held-out set |
|---|---|---|
| Haiku 4.5 | 35/37 (24/37 with PR #3's descriptions, 32/37 before the last description round) | 8/10 |
| Sonnet 5.5 | 37/37 | 10/10 |
| Opus 5.5 | 37/37 | 10/10 |

Haiku misses in the final run (traces were not kept, so only the turn count is known):

| Set | Prompt | Expected | Haiku's first move |
|---|---|---|---|
| held-out | `commands?` | help | no tool; answers directly |
| held-out | `note for later: we need to rotate the API keys before launch` | plan | another tool first; hit the 2-turn limit |
| tuning | `help` | help | no tool; answers directly (passed in the previous run) |
| tuning | `implement the flaky login test task we queued yesterday` | work | another tool first; hit the 2-turn limit (passed in the previous run) |

Across runs Haiku still sometimes answers help-style and "for later" prompts directly instead of calling a skill. Results are noisy at 1 run per case: single cases flip between runs (in the previous run Haiku missed `I'm new to this plugin, how do I use this` and `remember to bump the dependency versions before release` instead).
