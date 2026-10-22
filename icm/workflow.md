# Building a workflow as a skill

For the second kind of project in [method.md](method.md): the repository exists to build a repeatable, multi-step process that Claude runs, and the result should package as a Claude skill. It is ICM's Pipeline form (adapted from icm-architect's Build mode and `forms.md`, MIT, © 2026 Jake Van Clief; see [LICENSE](LICENSE)) with one change: the factory is a skill folder, so it can be copied into `~/.claude/skills/` or a plugin's `skills/` as is.

## 1. Find the structure in how the owner describes the work

Ask a few at a time, not all at once:

- What is the repeating unit of work (an episode, a report, a client, a release)?
- Walk me through one run, start to finish. Where do you stop and check something before going on?
- What stays the same every run (rules, voice, schema, templates), and what is new every run?
- What leaves at the end, and what does done look like?
- Who else touches it, and what must they find without asking?

Their pauses become stage boundaries. "I always check X before Y" becomes a Human check. "It always has to follow Z" becomes factory reference material. If the whole job fits in one saved prompt, make it a single `SKILL.md` without stages and say so. If the unit is not a run (records that accumulate, several pipelines sharing one voice), read [forms.md](forms.md) before choosing.

## 2. The tree

```
.claude/skills/<name>/          the factory: everything that ships with the skill
├─ SKILL.md                     routing: what it does, the stage table, what to do next (templates/workflow-SKILL.md)
├─ stages/
│  ├─ 01_<step>/
│  │  ├─ CONTEXT.md             the contract: Inputs, Process, Outputs, Verify, Human check (templates/stage-CONTEXT.md)
│  │  └─ references/            reference material only this stage reads
│  └─ 02_<step>/ ...
├─ _shared/                     reference material several stages read
└─ setup/questionnaire.md       only when the factory must be configured once per owner
runs/<run>/                     the product: one folder per run, outside the skill
└─ 01_<step>/<artifact>.md      what stage 01 wrote; stage 02 reads it from here
```

- `.claude/skills/<name>/` makes the workflow runnable in this repository while it is built (`/<name>` in Claude Code). Packaging is copying that folder; `runs/` stays behind, because outputs are product, not factory.
- Stage contracts name inputs as exact paths: the previous stage's output under `runs/<run>/`, and reference files by relative path inside the skill. Nothing in the skill links outside its folder, or it breaks once copied.
- The handoff is one stage's output file being the next stage's input. A person may edit it in between; the next stage reads whatever is there.
- Status is what exists under `runs/<run>/`.

## 3. Write the contracts

Copy each starter from [templates/](templates/) and fill it in. Inputs split into working (this run) and reference (every run), with a "Do not load" line for what an eager agent would wrongly pull in. The Process is short and numbered; constraints live in reference files, not in the contract. Verify names the earlier output or input to compare against and the criteria. Exactly one Human check, stated as something a person does.

## 4. Validate and package

Run `pm.py walk`: it checks that `SKILL.md` has a `name` matching its folder and a description with "Use when", stays a router, that every stage is numbered with a contract, that nothing links outside the skill, and that no run output sits inside it. Then do the cold walk in [method.md](method.md), and run the workflow once on a real input. Corrections to that run's outputs are recorded with `pm.py correct` and, when they repeat, become changes to the stage's contract or references.
