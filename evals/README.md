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

Haiku still misses about five cases per run. Across runs the recurring ones are help-2 (bare "help"), plan-2 ("remember to ..." goes to memory), work-4 and near-4-work, with map-3, near-5-init and work-1 flipping between runs; it sometimes reaches for built-in tools or `status` first. Results are noisy at 1 run per case.
