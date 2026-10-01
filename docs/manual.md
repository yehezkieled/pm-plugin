# Setup and migration manual

How to install the plugin, set it up on a new project, and move a project that already tracks work somewhere else (an older pm board, a `TODO.md`, a tasks folder, Beads, GitHub Issues, a Linear export) onto the pm board. For what the board is, see the [README](../README.md); for where knowledge goes, [placement.md](placement.md).

## 1. Install and update

```bash
claude plugin marketplace add yehezkieled/pm-plugin     # or a local path: /path/to/pm-plugin
claude plugin install pm@pm-plugin
```

Update (restart Claude Code afterwards so the new skills load):

```bash
claude plugin marketplace update pm-plugin
claude plugin update pm@pm-plugin
```

For local development of the plugin itself: `claude --plugin-dir /path/to/pm-plugin`. The helper CLI needs Python 3 and Git; nothing else is installed. `gh` is needed only for the GitHub mirror and for reading GitHub Issues during a migration.

Each project keeps its own board in `docs/pm/`, so installing the plugin once covers every project; setting up a project is a separate step (below).

## 2. A fresh project

Open Claude Code in the repository and run `/pm:init`. It:

1. Creates `docs/pm/config.json` (with a Git remote it commits and pushes this to the default branch so every clone sees the board).
2. Adds a short `AGENTS.md`, or a board pointer in the existing one, and a one-line `CLAUDE.md` containing `@AGENTS.md` when absent. It never replaces either.
3. Scans for an existing system (next section). On a fresh project it reports none.
4. Shows the board and the three commands to use next: `/pm:plan` to add work, `/pm:work` to build an item, `/pm:status` to see the board.

## 3. A project that already has a system

Run `/pm:init` (or `/pm:migrate` directly). The agent detects what is there, shows you what it found and how it will map, and only then writes items.

```text
scan ──> plan ──> you confirm ──> apply ──> route other knowledge ──> verify counts ──> you confirm removal
(read)   (read)                   (writes     (AGENTS.md, README,                       (git rm, only on yes)
                                   items)      CODEBASE.md)
```

What is guaranteed, whatever the source:

| Guarantee | How |
| --- | --- |
| Nothing changes before you say yes | `scan` and `plan` only read; the plan is saved outside the repository |
| Your words are not rewritten | The original text of each task is copied verbatim into `## Requester intent` |
| Open work becomes items | Queued, in flight (with its owner), or waiting on a decision (a hold); dependencies and issue numbers are kept |
| Finished work does not clutter the board | It stays in git history and is not imported; the counts say how much |
| Knowledge that is not a task is not dropped | Roadmaps, epics, decisions, and settings are listed with the file they should go to, per [placement.md](placement.md); the agent proposes each edit and you approve it |
| The old system is never deleted without your yes | The CLI never deletes; after you confirm, the agent runs `git rm` on exactly the paths the plan lists, so history keeps them |
| Counts add up | The plan and the apply output show entries before, items imported, entries left in history, and the board now |
| Re-running is safe | Each item id ends in a hash of the source and the old key, so a second `apply` skips what is already there, even after a title was edited |

Steps the agent follows (`skills/migrate/SKILL.md`):

1. **Scan**: `pm.py migrate scan` lists each system it recognises, with counts and the importer to use. GitHub Issues and tracker exports are checked with `gh` or by reading the export.
2. **Plan**: `pm.py migrate plan --from pm-0x --out PLAN.json` (or `--from checklist --file TODO.md`). For any other system the agent writes the plan itself (section 4.3).
3. **Review with you**: counts before and after, the field mapping, items that need a decision, what is not carried over, where non-task knowledge goes. You answer questions and the agent edits `PLAN.json`.
4. **Apply**: `pm.py migrate apply PLAN.json` creates `docs/pm/config.json` if needed and the items, records every old key the plan accounted for (imported or left in history) under `migrated_from` in that file, keeping its other settings, committing and pushing them to the default branch the same way `/pm:plan` does. `--dry-run` shows the items without writing.
5. **Route other knowledge**: with your approval, lasting rules and the test command go to `AGENTS.md`, product goals to `README.md`, architecture to `docs/pm/CODEBASE.md` (`/pm:map`).
6. **Verify**: `pm.py board` and the counts.
7. **Retire**: you decide whether the old files go. On a yes, they are removed with `git rm`.

### Rolling out to several projects

Do the plugin install or update once, then per project: open Claude Code there and run `/pm:init`, review the plan, say yes, approve the knowledge edits, decide on removal. Each project is independent. Once the plugin is updated, a project still on an old pm-plugin 0.x board prints a one-line reminder at session start while any of its tickets is missing from the `migrated_from` record in `docs/pm/config.json`, whether or not `/pm:init` already ran there, so a project that was missed shows itself. Once applied, keeping the old `docs/pm/tickets` folder or finishing the migrated items does not bring the reminder back; a ticket added to the old folder later does.

## 4. Source systems

| Source | Detected by `scan` | How it is converted |
| --- | --- | --- |
| pm-plugin 0.x | `docs/pm/tickets/T*.md` | Built-in importer `pm-0x`, exact (4.1) |
| Markdown checklist: `TODO.md`, `ROADMAP.md`, `BACKLOG.md`, `TASKS.md`, `PLAN.md` in the root or `docs/` | Checkbox lines `- [ ]` / `- [x]` | Built-in importer `checklist` (4.2) |
| Task files with plain bullets or prose | Listed as a notes file, no checkboxes | Hand-made plan (4.3) |
| `tasks/`, `backlog/`, `.taskmaster/`, `.beads/`, `issues/` folders | Folder of text or data files (a folder of code is ignored) | Hand-made plan (4.3) |
| GitHub Issues only | A GitHub remote | Hand-made plan from `gh issue list` (4.3) |
| Linear or other tracker export (CSV, JSON) | A `.csv` named like an issues export | Hand-made plan (4.3) |

### 4.1 pm-plugin 0.x, exactly

0.x kept `docs/pm/tickets/Txxx-slug.md` with frontmatter, plus `epics/`, `roadmap.md`, `decisions.md`, and a `## pm` settings block in `CONTEXT.md`. 1.x does not read that layout, so nothing on the old board shows until it is migrated.

| 0.x ticket | 1.x item |
| --- | --- |
| `status: todo` | Queued. A `ready: no` ticket (not yet clarified) gets a hold saying so, so it shows under Waiting |
| `status: in progress` or `review` | In flight, with its `owner`. With no owner it becomes Queued and a warning says so, because 1.x needs an owner to be in flight |
| `status: done` | Left in git history |
| `status: dismissed` | Left in git history; it was closed without being done, so it is never imported |
| An unknown status | Queued, with a warning |
| `owner` on a todo ticket | Kept as the item's owner, which reserves it the way a claim does |
| `depends_on: [T001]` | The matching item. A dependency on finished work is dropped (already satisfied); a dismissed or unknown one is dropped with a warning |
| `issue: 12`, `#12`, or `.../issues/12` | `github_issue: "12"`. Any other value goes into the notes |
| `pr` | Noted in the item's notes |
| `epic`, `milestone`, `priority` | Noted in the notes (`Migrated from pm-plugin 0.x ticket T002 (epic E01 Login, milestone M1, priority P1)`), with the epic's goal. 1.x has no hierarchy or priority |
| Body, except `## Plan`, `## Notes`, `## Proposed changes` | `## Requester intent`, verbatim (the title when the body is empty) |
| `## Plan` (unless an empty template), `## Notes`, `## Proposed changes` | `## Current notes`, labelled `(0.x)` |
| `auto`, `plan`, `tests`, `confidence` | Not carried over; the plan lists them |
| Roadmap `## Backlog` lines | One Queued item each, with the line as the requester's words |
| Roadmap milestones | Not items. Routed to `README.md` if they still describe the product |
| `decisions.md` entries | Not items. Decisions that shape future work go to `AGENTS.md` (architectural ones to `CODEBASE.md`); one that only explains a past change stays in git history |
| `CONTEXT.md` `## pm` block | The `check:` command goes to `AGENTS.md`; the block is then removed, the rest of the file stays. A `mirror: on` setting is not carried over: enabling the 1.x mirror is a separate choice (`pm.py mirror github`) |
| Files under `docs/pm/` this importer does not know | Left alone and listed in the warnings |

Retire list: `docs/pm/tickets`, `docs/pm/epics`, `docs/pm/roadmap.md`, `docs/pm/decisions.md`. The `docs/pm/` folder itself stays, since the 1.x board lives there too.

### 4.2 Markdown checklist

Each top-level checkbox line, with everything indented under it (including nested checkboxes), becomes one item. The text is the requester's words exactly; the title is its first line, shortened to about 80 characters. `- [ ]` is Queued; `- [x]` goes to git history. The nearest heading is recorded in the notes. Text that is not a checklist item is counted and listed as knowledge to route, and then the file is not offered for removal: delete the migrated lines by hand.

Owners, dates, labels, and `#123` references stay inside the intent text. If you want them mapped (an assignee as `owner`, an issue number as `github_issue`), the agent edits the plan.

### 4.3 Anything else: a hand-made plan

The agent reads the source, proposes a mapping, you confirm it, and the agent writes the plan JSON (section 5). The mapping rules are the same for every system:

| Source concept | Plan field |
| --- | --- |
| The requester's text: description, body, or the line itself | `intent`, copied verbatim. Never a summary; if there is only a title, use it |
| Its identifier | `key`. It makes the item id stable, so re-running is safe |
| Short name | `title` |
| Open / to do / backlog | `status: "queued"` |
| In progress / started / assigned | `status: "in-flight"` with an `owner` (required), or `queued` if nobody holds it |
| Blocked on a question or decision | `hold` with the question, optionally `hold_until` |
| Blocked on another task | `depends_on` with that task's key |
| Closed / done | Leave out of `items` and list in `history` |
| Cancelled / won't do | `history` |
| Issue number in GitHub | `github_issue`, digits only |
| Labels, priority, estimate, parent, sprint | The `notes`: one short line each, since 1.x has no such fields |
| Comments with decisions or progress | `notes` if current; lasting decisions are routed per placement.md |

Hints per system. The field names of third-party tools are from their documented formats and have not been checked against current versions here, so the agent confirms them against the export in front of it [UNSURE].

- **GitHub Issues**: `gh issue list --state open --limit 200 --json number,title,body,labels,assignees`. Title to `title`, body to `intent`, number to `github_issue` and `key` (`#12`), assignee on an in-progress issue to `owner`, labels to `notes`. "Blocked by #N" to `depends_on` only when you confirm it. Closed issues stay on GitHub, so they go in `history`. Enabling the mirror later makes `sync` rewrite these issues' bodies, so decide that on purpose.
- **Beads** (`.beads/`): export with the tool's own list command (for example `bd list --json`) rather than reading its database files [UNSURE]. Map open, in progress, and closed as above, dependency links to `depends_on`, and priority to the notes.
- **Backlog.md-style `backlog/` and Task Master `.taskmaster/`**: each task is a file or a JSON record with a title, description, status, assignee, and dependencies [UNSURE]. The same table applies; the status names differ (`To Do` is queued, `In Progress` is in flight, `Done` is history).
- **Linear or another tracker export**: columns such as identifier, title, description, status, assignee, and priority [UNSURE]. Identifier to `key`, description to `intent`, and the workflow state names are mapped to the three statuses with your confirmation, since each team names them differently.
- **`TODO.md` with plain bullets**: each bullet is one item with the bullet text as `intent`. Section headings (`## Next up`, `## Someday`) go in the notes. Ask whether "Someday" items should be queued at all.

For a large source, the agent reads it in pieces and builds the plan file incrementally, but shows you the finished plan once and applies it once.

## 5. The plan file

`plan` writes it and `apply` reads it, so a hand-made plan uses the same shape. It is plain JSON, saved outside the repository (a temp directory):

```json
{
  "source": "beads",
  "before": {"total": 3, "by_status": {"open": 2, "closed": 1}},
  "items": [
    {"key": "bd-1", "title": "Fix login", "intent": "login is broken\non mobile", "status": "queued"},
    {"key": "bd-2", "title": "Fix signup", "intent": "signup too", "status": "in-flight", "owner": "Ari",
     "depends_on": ["bd-1"], "github_issue": "7", "hold": "Which provider?", "hold_until": "2026-12-01",
     "notes": "Labels: auth. Priority: high."}
  ],
  "history": [{"key": "bd-0", "title": "Old task", "status": "closed", "why": "closed"}],
  "knowledge": [{"from": "docs/roadmap.md", "what": "3 milestones", "route": "README.md"}],
  "warnings": ["bd-3 had no description; its title is the intent."],
  "retire": ["docs/old-tasks.md"]
}
```

| Field | Meaning |
| --- | --- |
| `source` (required) | Names the old system; with each item's `key` it makes the item id, so the same plan never creates an item twice |
| `items[].key`, `title`, `intent` (required) | The old identifier, a short name, and the requester's exact words |
| `items[].status` | `queued` (default) or `in-flight` (needs `owner`); finished work goes in `history`, not `items` |
| `items[].hold`, `hold_until` | A question that parks the item under Waiting; a date to revisit it |
| `items[].depends_on` | Keys of other items in the plan, with no cycles |
| `items[].github_issue`, `owner`, `notes` | Optional strings; the issue number as digits, the person, a short current-state note |
| `before` | Entries in the old system by status; used to check the counts add up |
| `history` | Old entries not imported, each with a `key` and a reason; counted in "accounted for" and recorded with the item keys under `migrated_from` in `docs/pm/config.json` |
| `knowledge`, `warnings`, `retire` | Shown to the owner. `retire` lists the paths removed after confirmation, and `apply` never touches them |

`pm.py migrate apply` refuses a plan with an unknown status (including `done`), an in-flight item without an owner, a missing intent, a title longer than one line, an optional field that is not a string (leave it out rather than writing `null`), a duplicate key, a dependency that is not in the plan, a dependency cycle, or an issue that is not a number. Nothing is written when a plan is refused.

## 6. Adding a new source system

Do this when a source is common enough that a hand-made plan each time is wasteful.

1. Write a reader in `scripts/pm_migrate.py`: a function `read_<name>(root, file=None, **_) -> dict` that only reads and returns a plan (section 5). Fill `before` and `history` so the counts add up, put everything the board has no field for in `notes`, and list every non-task file in `knowledge` with its destination from [placement.md](placement.md). Raise `ValueError` with a plain message for input it cannot read.
2. Register it in `SOURCES` (this makes `--from <name>` available) and add a detector for it in `scan`, with the command to run.
3. Add a fixture under `tests/fixtures/<name>/` that covers every status, a dependency, a missing or odd value, and non-task files. In `tests/test_migrate.py` assert the plan, then apply it and assert the board, that the intent matches the source's text character for character, that nothing in the old system was changed, and that a second apply adds nothing.
4. Document the mapping as a table in section 4, add the source to the detection table there, and re-run the routing evals if a skill description changed (`evals/README.md`).
5. Run `python3 -m unittest discover -s tests -v`.

## 7. When something looks wrong

| Symptom | Cause and fix |
| --- | --- |
| The board is empty after updating from 0.x | 1.x does not read `docs/pm/tickets/`. Run `/pm:init` and migrate |
| `scan` says nothing found but you have a backlog | It is somewhere `scan` does not look (a wiki, a Notion page, a differently named file). Point the agent at it; it builds a plan by hand |
| `plan` fails with "not a file inside this repository" | `--file` must be a path inside the repository |
| `apply` refuses the plan | The message lists each problem; fix `PLAN.json` and run it again |
| The same plan was applied twice | Safe: existing items are skipped and left as they were |
| `apply` says the local default branch cannot fast-forward | Sync the default branch with the remote first; a migration is published like any other board change |
| An item shows as claimed by someone | The old system had an owner on it. The owner keeps the claim; nobody else can claim it |
| You regret removing the old files | `git log --diff-filter=D --name-only` finds them; `git checkout <commit>^ -- <path>` restores them |
