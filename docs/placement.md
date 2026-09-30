# Where knowledge goes

Put each fact in the most specific place that owns it. Anything useful to every contributor lives in the repo, so it travels with the code.

| Kind of knowledge | File |
| --- | --- |
| Lasting agent rules: build/test/lint commands, gotchas, board workflow, private or agent-only context | `AGENTS.md`. `CLAUDE.md` holds only the pointer `@AGENTS.md`. |
| Product overview: what it is, who it is for, goals, how to run it (never private context) | `README.md`. `AGENTS.md` points to it, not copies it. |
| Domain vocabulary, only when the project has its own terms | `CONTEXT.md` as a glossary. Not an overview: that duplicates the README and drifts. |
| Architecture: components, data flow, entry points | `docs/pm/CODEBASE.md`, written by `/pm:map`. |
| One task: the requester's exact words, progress, decisions, what is left | `docs/pm/items/<id>.md`: intent under `## Requester intent`, the rest under `## Current notes`. |

## Recording decisions

| Stage | What to do |
| --- | --- |
| Question is open | `pm.py hold ITEM_ID` with the question on stdin. The item moves to Waiting and keeps its owner. |
| Answer arrives | Resume with the decider's exact words: `pm.py resume ITEM_ID --answer` with the answer on stdin. They are saved at the top of the item's `## Current notes`, in the same commit as the resume. Do not paraphrase them. |
| Decision shapes future work (a convention, a constraint, a design choice) | Add it as durable guidance to `AGENTS.md`, or to `docs/pm/CODEBASE.md` if it is architectural, through the normal change for the item. |
| Decision only explains this change | Leave it in the item's notes and in the PR description. |

Before writing anywhere, check the file already covers the fact; update it instead of adding a duplicate. Mark claims you have not verified `[UNSURE]`.
