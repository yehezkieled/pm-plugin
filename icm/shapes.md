# Project shapes: where every kind of file goes

Every project gets the same spine, plus the rows of its shape (or shapes). `/pm:init` stamps these rows into the `## Where things go` table of the root `AGENTS.md` ([template](templates/root-AGENTS.md)). From then on that table is the one place an agent looks before it creates a file, and `pm.py places` and the Stop hook check new files against it. Each shape is an ICM form that keeps the factory (code, rules, reference data) apart from the product (generated outputs, deliverables).

Pick by the project's repeating unit of work. A project can be two shapes, such as an analysis that also runs daily; then take the union of their rows. A path the project already uses for a kind of thing stays: the table records `sources/` rather than moving it to `data/raw/`. The table in `AGENTS.md` wins over this file.

## Spine: every project

| Kind of thing | Place | Rule |
| --- | --- | --- |
| Tasks: what is being done and what is next | `docs/pm/items/` | `/pm:plan` adds them and `/pm:work` claims them; never made by hand |
| How it works, decisions, gotchas | `docs/` | one file per topic; update it, don't duplicate it |
| Deliverables for people: memos, reports, findings | `reports/` | written by a person or an agent; `YYYY-MM-DD-<topic>.md`; cite the data and the command behind each number |
| Generated outputs | `out/` | written only by code, even when it is a Markdown report; never hand-edited; gitignored |
| Project files at the root | `README.md`, `AGENTS.md`, `CLAUDE.md`, `.gitignore`, the dependency file | nothing else at the root |

Files a tool expects at the root (the dependency and lock files, `LICENSE`, dotfiles and dot-folders such as `.github/`) always pass the check.

## Shape rows

**analysis**: data analysis, reconciliation, exploration (unit: a question answered from data)

| Kind of thing | Place | Rule |
| --- | --- | --- |
| Raw data as received | `data/raw/<source>/` | never edited; keep the publisher's file name |
| Where each dataset came from | `data/README.md` | one line per file: source, date received, what reads it |
| Hand-curated reference data | `data/ref/` | mappings and lookups edited by hand; listed in `data/README.md` |
| Reusable code | `src/` | loaders, checks, transforms; run from the root |
| Tests | `tests/` | |
| Exploration | `notebooks/` | `YYYY-MM-DD-<question>.ipynb` or `.py`; reads `data/` and `src/`; findings worth keeping go to `reports/` |

**automation**: a job that runs on a schedule or a trigger (unit: a run)

| Kind of thing | Place | Rule |
| --- | --- | --- |
| Job code | `src/` | |
| Tests | `tests/` | |
| Schedule and CI | `.github/workflows/` | |
| Settings the job reads | `config/` | no secrets |
| Each run's output | `out/runs/YYYY-MM-DD/` | generated; gitignored or published as a release |
| How to run, recover, and check it | `docs/runbook.md` | |

**skill**: a Claude skill or workflow being built (unit: a run of the workflow); the stages follow [workflow.md](workflow.md)

| Kind of thing | Place | Rule |
| --- | --- | --- |
| The skill (the factory) | `.claude/skills/<name>/` | `SKILL.md` routes; `stages/NN_<step>/CONTEXT.md` are the contracts; `_shared/` holds reference material |
| Each run's files (the product) | `runs/<run>/` | one folder per run, outside the skill |
| Example inputs and expected outputs | `evals/` | |

**app**: an app, library, service, or site (unit: a change to the code)

| Kind of thing | Place | Rule |
| --- | --- | --- |
| Source | `src/` | or the folder the language or framework expects; write the real one in the table |
| Tests | `tests/` | |
| Architecture, part by part | `docs/pm/map/` | the optional System map from `/pm:map` ([system-map.md](system-map.md)) |

**research**: writing or investigation without much code (unit: a question or a source)

| Kind of thing | Place | Rule |
| --- | --- | --- |
| Sources as found | `sources/` | never edited |
| Where each source came from | `sources/README.md` | one line per source: where, when, why it matters |
| Working notes | `notes/` | one file per question; a finished answer goes to `reports/` |

Only the skill shape gets stage folders. Do not climb the ladder early: a thing done twice is a saved prompt or a single `SKILL.md`, not a staged workflow.

## Tie-breakers

- **Whoever writes the file decides its home.** Code writes it: `out/` (or the run's folder). A person or an agent writes it for people: `reports/`.
- **Keep the names the project already uses**, for folders and files alike, and record them in the table: a file that moves keeps its name. Rename only when the owner asks.
- **Name new dated files `YYYY-MM-DD-<topic>`**, lowercase with hyphens, dated the day the file is written (run `date +%F`), not a date from the data.
- **The more specific row wins**: raw data goes to `data/raw/<source>/`, not `data/`.

## Links keep the structure current

The table is also the map's index of links, so the structure cannot go stale unseen. A place that holds a file is a link from its row, to the folder's `README.md` when it has one (`` [`data/`](data/README.md) ``), else to the folder (`` [`src/`](src/) ``); a place with no file yet stays a plain path until its first file lands, and `docs/pm/items/` and the gitignored `out/` always do. A folder's `README.md` ([template](templates/folder-README.md)) says what it holds, links each file it describes, and links back to `AGENTS.md` (`../AGENTS.md` from a top-level folder). A `CONTEXT.md` links up to the `AGENTS.md` or `SKILL.md` that routes to it, and a nested `AGENTS.md` to the one above it. `AGENTS.md` › When you finish a task says which of these files a change updates. `pm.py walk` fails on a broken link, a place that holds a file but is not linked, and a file that does not link back up.

## When nothing fits

Ask the owner once where this kind of thing should live, recommend a place, then add the row to `AGENTS.md` in the same change, linked to the new folder's `README.md`. Never put a new kind of file at the root.
