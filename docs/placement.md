# Where knowledge goes

Put each fact in the most specific place that owns it, once, and link to it from anywhere else. Anything useful to every contributor lives in the repo, so it travels with the code. The layout follows ICM ([icm/](../icm/README.md)): small routing files point at the files that hold the facts, and an agent loads only what its task needs.

| Kind of knowledge | File |
| --- | --- |
| Where things live, where to go for a task, and the few rules every session needs (build and test commands, claim before coding) | `AGENTS.md`, the catalog: under 60 lines; it routes rather than explains. `CLAUDE.md` holds only `@AGENTS.md`. |
| Product overview: what it is, who it is for, goals, how to run it (never private context) | `README.md`. The catalog links to it. |
| What one part of the code is, why it has that shape, what a change to it hits, its gotchas | That part's card in `docs/pm/map/` (`objects/` for things, `processes/` for movements), written by `/pm:map`. Without a map, the doc that already owns that area, linked from the catalog. |
| Which cards to open before a change | `docs/pm/map/effects/CONTEXT.md` |
| Domain vocabulary; product words versus code names | The Names table in `docs/pm/map/AGENTS.md` |
| How a working folder's job is done: inputs, process, outputs, verify, human check | That folder's `CONTEXT.md`. A `CONTEXT.md` is always a folder's contract or router, never a glossary or overview. |
| A workflow being built | Its skill folder, `.claude/skills/<name>/`: `SKILL.md` routes, `stages/NN_<step>/CONTEXT.md` are the contracts, `_shared/` and `references/` the stable material. Each run's files go in `runs/<run>/`, outside the skill. |
| One task: the requester's exact words, the cards or stages it touches, progress, decisions, corrections | `docs/pm/items/<id>.md`: intent under `## Requester intent`, `touches` and `corrections` in its frontmatter, the rest under `## Current notes`. |
| Generated lists: the board, the map's card index | Rebuilt by `pm.py board` and `pm.py index`; never edited by hand. |

## Recording decisions

| Stage | What to do |
| --- | --- |
| Question is open | `pm.py hold ITEM_ID` with the question on stdin. The item moves to Waiting and keeps its owner. |
| Answer arrives | Resume with the decider's exact words: `pm.py resume ITEM_ID --answer` with the answer on stdin. They are saved at the top of the item's `## Current notes`, in the same commit as the resume. Do not paraphrase them. |
| Decision shapes future work (a convention, a constraint, a design choice) | Put it on the card or contract of the part it governs, or in `AGENTS.md` if every session needs it, through the normal change for the item. |
| Decision only explains this change | Leave it in the item's notes and in the PR description. |

## Fix the source when a correction repeats

When a person corrects an agent's output, record it with `pm.py correct ITEM_ID --kind KIND --where PATH`. At the third correction of one kind on one source, change that source instead of the next output: the contract, card, or reference file it came from; `AGENTS.md` if it applies to every session; this file if it is about where knowledge goes. Then record `--fixed`.

## Where pm and ICM differed, the rule now

| Question | Rule |
| --- | --- |
| Which entry file is edited | `AGENTS.md`; `CLAUDE.md` is the pointer `@AGENTS.md`. The same pair holds in `docs/pm/map/`. ICM's generated twin files are not used. |
| What `CONTEXT.md` is | A folder's contract or router, as in ICM. pm's old glossary use moves to the Names table. |
| Where architecture goes | The System map's cards, replacing `docs/pm/CODEBASE.md`; `/pm:map` absorbs and retires that file. |
| Where lasting rules go | The card or contract of the part they govern; `AGENTS.md` keeps only what every session needs. |
| Stages | Only for a workflow being built, inside its skill folder. An ordinary project never gets stage folders. |
| The unit of work | A board item. It names the cards or stages it touches; its contract is the requester's words plus those files. |
| Templates | Ship with the plugin in `icm/templates/`; a map keeps copies in `_templates/` so a new card is a copy. |
| Removing files | `git rm` after the owner's yes; git history replaces ICM's `_archive/` folder. |

Before writing anywhere, check the file already covers the fact; update it instead of adding a duplicate. Mark claims you have not verified `[UNSURE]`.
