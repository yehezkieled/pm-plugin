---
name: {skill-name}
description: "{What this workflow produces, in one sentence}. Use when the user asks to \"{trigger phrase}\" or {another trigger}."
---

# {Workflow name}

{One sentence: what goes in, what leaves.} Each stage's `CONTEXT.md` is its contract; each run's files are the state.

## Stages

| Stage | Job | Reads | Writes | Human check |
| --- | --- | --- | --- | --- |
| [01_{name}](stages/01_{name}/CONTEXT.md) | {five words} | {the run's input} | `runs/{run}/01_{name}/{file}` | {what a person checks} |
| [02_{name}](stages/02_{name}/CONTEXT.md) | {five words} | 01's output | `runs/{run}/02_{name}/{file}` | {what a person checks} |

Factory, the same every run: this folder (`_shared/`, each stage's `references/`). Product, new each run: `runs/{run}/` in the project, outside this folder, so it never ships with the skill.

## Route by what just happened

| If | Do | Then stop at |
| --- | --- | --- |
| starting a run | name it with a short slug and follow stage 01's contract | the person reads 01's output |
| a stage's output was approved | follow the next stage's contract | the person reads that output |
| asked for status | list what exists in `runs/{run}/` | report it |

## The one rule

Nothing moves to the next stage until a person has read the last one's output, after its Verify has run.
