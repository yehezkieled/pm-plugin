# Skill-routing evals

37 single-turn cases (4 per skill, 8 near-miss prompts, 5 non-pm prompts). Each gives the model only the `Skill` tool and grades the **first** Skill call: it must be the expected `pm:*` skill, or no pm skill for the non-pm prompts. Later chained calls (e.g. plan then init) are not counted.

Run (about $1-2.5 per model):

    claude plugin eval . --model claude-sonnet-5-5 --ablation none --trust-plugin -j 4 --no-publish

Results (1 run per case, confirmed by a second full run with the committed descriptions):

| Model | Passed |
|---|---|
| Haiku 4.5 | 32/37 (was 24/37 before description changes) |
| Sonnet 5.5 | 37/37 (was 36/37) |
| Opus 5.5 | 37/37 (was 36/37) |

Haiku misses (observed across runs; 5 per run in the confirming run, 7 in a later noisy run):

| Prompt | Expected | Haiku's first move |
|---|---|---|
| `help` | help | no skill; answers directly |
| `remember to bump the dependency versions before release` | plan | no skill; writes to its own memory |
| `implement the flaky login test task we queued yesterday` | work | `status` first, or built-in Glob/TaskList |
| `go ahead and do the refactor of the parser task on the board` | work | `status` first (then `work`) |
| `is there a board yet? if not create one` | init | `status` first (then `init`) |
| `write up an architecture doc of how the modules fit together` | map | no skill; Glob (flips between runs) |

Results are noisy at 1 run per case; a few other cases (e.g. `set up pm in this repo`, `what's next?`) also flipped once.
