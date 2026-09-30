# Skill-routing evals

37 single-turn cases (4 per skill, 8 near-miss prompts, 5 non-pm prompts). Each case pre-approves only the `Skill` tool (`allowed_tools: [Skill]`); the model can still use read-only built-ins such as Glob, but only its **first** Skill call is graded: it must be the expected `pm:*` skill, or no pm skill for the non-pm prompts. Later chained calls (e.g. plan then init) are not counted.

Run (about $1-2.5 per model):

    claude plugin eval . --model claude-sonnet-5-5 --ablation none --trust-plugin -j 4 --no-publish

Results (1 run per case, with the committed descriptions):

| Model | Passed |
|---|---|
| Haiku 4.5 | 35/37 (24/37 with PR #3's descriptions, 32/37 before the last description round) |
| Sonnet 5.5 | 37/37 |
| Opus 5.5 | 37/37 |

Haiku misses in the final run (both answered directly without calling any tool):

| Prompt | Expected | Haiku's first move |
|---|---|---|
| `I'm new to this plugin, how do I use this` | help | no skill; answers directly (passed in earlier runs) |
| `remember to bump the dependency versions before release` | plan | no skill; answers directly (missed in every run) |

The last description round fixed Haiku's earlier misses on bare `help`, the two work prompts (it used to call `status` first), `is there a board yet? if not create one` (init), and the architecture-doc map prompt. Results are noisy at 1 run per case: single cases flip between runs.
