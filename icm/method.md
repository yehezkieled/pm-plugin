# The ICM method, as pm applies it

Adapted from icm-architect's `SKILL.md` (MIT, © 2026 Jake Van Clief; see [LICENSE](LICENSE)). Read this before structuring or restructuring a repository.

Think of the repository as a library. The routing files are the catalog: small, stable, pointing at everything and storing almost nothing. The facts live on the shelves. One agent walks the building, and the task decides which shelf it walks to. Nobody photocopies the library into the agent's context; the catalog is small on purpose.

## The invariants

1. **One folder, one job.** Each working folder does one step or holds one kind of thing, and says so in a file inside itself.
2. **A small, stable entry file.** `AGENTS.md` at the root answers "where am I, where does everything live, where do I go for task X" and holds only the rules every session needs. Under 60 lines. `CLAUDE.md` is the one line `@AGENTS.md`.
3. **Numbering encodes order** where order matters (`01_`, `02_`). Renaming a folder reorders the run.
4. **Every working folder has an explicit contract**: its `CONTEXT.md` names Inputs (exact paths), Process, Outputs, Verify, and one Human check.
5. **Factory apart from product.** Reference material that stays the same across runs lives apart from what each run produces.
6. **Every output is an edit surface.** Outputs are plain files a person can open and fix before the next step reads them.
7. **Load only what the step needs**: its contract, its references, its inputs. About 2,000 to 8,000 tokens a step.
8. **Plain text, one home per fact.** Markdown with frontmatter; a link beats a copy.
9. **The filesystem is the state.** Status is what exists. Generated indexes are rebuilt by script (`pm.py index`, `pm.py board`), never edited by hand.
10. **Instantiate by copying** a template, not a blank page ([templates/](templates/)).

## Two kinds of project

pm serves two uses, and the structure differs. `/pm:init` detects which one this is and confirms it with the owner in one question.

| Kind | Signals | Structure |
| --- | --- | --- |
| **Ordinary project**: an app, library, service, site, or docs | Package metadata (`package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`), `src/`, tests | The light parts only: the small catalog `AGENTS.md`, one home per fact ([placement](../docs/placement.md)), an optional System map from `/pm:map` ([system-map.md](system-map.md)), Verify, and fixing the source. **Never stage folders.** |
| **Workflow being built**: a repeatable multi-step process Claude will run, to be packaged as a skill | Mostly prompts and Markdown, step-by-step notes, "workflow", "pipeline", or "skill" in the README, an existing `SKILL.md` or `stages/` | An ICM Pipeline inside a skill folder, with each run's files kept outside it ([workflow.md](workflow.md)) |

When the signals disagree (a code repo whose product is a workflow), ask. Do not climb the ladder early: a thing done twice is a saved prompt or a single `SKILL.md`, not a staged workflow.

## Restructure gate

Use it whenever existing files would move: an entry file carrying payload, a docs folder that grew without a skeleton, an old architecture file. Nothing moves before the owner's yes.

1. **Inventory, read-only.** List the tree (`git ls-files`), and for each area note what it is, when it was last touched (`git log -1 --format=%cs -- PATH`), and what refers to it. Run `pm.py walk` to see where the structure fails today.
2. **Classify every instruction and doc file** as Catalog (routing), Contract (how a step works), Factory (stable reference), Product (what one run or task produced), or Dead (stale, duplicated, superseded).
3. **Check reference integrity** for every file that would move: `pm.py refs OLD=NEW ...` lists what points at it and whether the destination is taken when compared case-folded ([reference-integrity.md](reference-integrity.md)). Ask the owner about consumers outside the repository. A file with a live referrer moves only if every referrer is updated in the same change. Apparent disuse is not proof.
4. **Propose**: the target tree, a migration map (old path, new path, role, referrers found), and the new `AGENTS.md` in full. Ask once for a yes, against that report.
5. **Move, verify, then remove.** For tracked files, `git mv OLD NEW`, then confirm `git diff --cached -M100% --name-status` lists each one as `R100`: the content is identical, so nothing was lost. Edit the moved files only after that check. Untracked files: copy, compare `sha256sum`, then delete the original. Update every referrer in the same change. Dead files are removed with `git rm` only on the owner's yes; git history is the archive.
6. **Validate with the walk test.**

## The walk test

Run it after `/pm:init` and after `/pm:map`, and after any restructure.

1. **Mechanical**: `pm.py walk`. It checks the entry file's size and the `CLAUDE.md` pointer, that every link in routing files and cards resolves, that each working folder's `CONTEXT.md` has its five sections, the map's catalog, cards, citations, change-impact index, and generated index, a workflow skill's packaging, every item's `touches`, and the token budget. Fix every FAIL; read every WARN.
2. **Cold**: answer these from the files alone, as an agent with no memory, opening only what each answer needs:
   - From `AGENTS.md` plus at most two more reads: where am I, and where do I go for the most common task here?
   - Pick one contract or card. Does it name exact input paths, the job, the output, what to verify, and the human check (a card: what it is, why, and what a change hits)?
   - Can you state status by listing files (the board, a workflow run's folder, the cards' status)?
   - Is any routing file carrying content? Is any fact in two places?
   - System map: can you say what X is and what else moves if X changes, from `docs/pm/map/AGENTS.md` plus one card?

If a step fails, fix the structure by moving or splitting files, not by explaining more.

## Verify before the human check

Every contract carries a `## Verify` section between Outputs and Human check: which earlier outputs or inputs to re-read and what must still match. The agent runs it and lists each mismatch at the top of its output, so the person reviews a checked result. For a board item, the contract is the item itself: `/pm:work` re-reads the requester's exact words and each touched card's or stage's contract before showing the change. (ICM paper, section 6.2.)

## Fix the source, not only the output

A correction a person makes to an output fixes one run; a change to the file that produced it fixes every run. When the person corrects the agent's output, record it with `pm.py correct ITEM_ID --kind KIND --where PATH`. When the same kind of correction reaches three on the same source, the CLI and the board say so: propose a lasting change to that source (the contract, card, or reference file it came from; `AGENTS.md` if it applies to every session; `docs/placement.md` if it is about where knowledge goes), and after it lands record it with `--fixed`. Some corrections are taste no rule would capture; leave those as output edits. (ICM paper, section 6.3.)

## Guardrails

- **Smallest structure that carries the work.** Three real stages beat seven imagined ones. No empty folders, no "misc" buckets, no speculative depth.
- **Where ICM loses**: tight real-time multi-agent loops, high-concurrency serving, and automated mid-run branching need framework code.
- **Anti-patterns**: two hand-edited entry files that drift; a schema or contract naming files that no longer exist; hand edits to a generated index; patterns declared top-down before they recur three times.
