# Plugin architecture

The plugin uses Claude Code skills for conversational workflow, a Python standard-library CLI for shared board operations, and project-owned Markdown for state. It starts no reviewer agents and has no scheduled runner.

## Components and dependencies

```mermaid
flowchart LR
  U[User request] --> S[Claude Code skills<br/>skills/*/SKILL.md]
  S --> C[scripts/pm.py<br/>board operations]
  C --> M[scripts/pm_migrate.py<br/>source readers, plan checks]
  OLD[Old system<br/>0.x tickets, TODO.md, tasks, issues] -. read only .-> M
  C --> I[docs/pm/items/slug-random.md<br/>intent, status, owner, notes]
  C --> K[docs/pm/config.json<br/>board marker, mirror setting,<br/>migration record]
  S -. read .-> PG[docs/placement.md<br/>where knowledge and decisions go]
  S -. read .-> ICM[icm/<br/>method guides, templates]
  C --> W[scripts/pm_icm.py<br/>walk test, card index, refs]
  W -. read only .-> R[AGENTS.md, CONTEXT.md contracts,<br/>docs/pm/map/, workflow skills]
  I --> B[Rendered board<br/>pm.py board output]
  H[Claude Code hooks<br/>hooks/hooks.json] --> SH[hooks/session-start.sh<br/>hooks/stop.sh]
  SH --> C
  G{Mirror enabled?} -->|yes| GH[GitHub Issues via gh]
  C -. sync command .-> G
```

Sources: [plugin manifest](../.claude-plugin/plugin.json), [skills](../skills/), [CLI](../scripts/pm.py), [migration readers](../scripts/pm_migrate.py), [structure checks](../scripts/pm_icm.py), [ICM guides and templates](../icm/README.md), [hooks](../hooks/), [placement guide](placement.md), [setup and migration manual](manual.md).

## Work and data flow

```mermaid
sequenceDiagram
  actor Person
  participant Skill as Claude Code skill
  participant CLI as scripts/pm.py
  participant Lock as local file lock
  participant Remote as remote default branch
  participant Item as docs/pm/items/slug-random.md
  Person->>Skill: request or start work
  Skill->>CLI: init / add / set / hold / resume / claim
  CLI->>Lock: acquire exclusive local file lock
  CLI->>Remote: fetch the latest default branch
  CLI->>Item: check and change the item in a temporary checkout
  CLI->>Remote: push the item commit without force
  Remote-->>CLI: accept one update or reject a race
  CLI->>Remote: fetch and re-check after rejection
  CLI->>Item: fast-forward the local default branch when checked out
  Skill->>CLI: finish on the work branch
  CLI->>Item: commit only the item file; the PR merge publishes it
  CLI-->>Skill: item path and rendered board
  Skill-->>Person: work result and next ready item
```

`init`, `plan`, `work`, `map`, and `help` read the single [placement guide](placement.md) instead of restating it. For decisions, `hold` stores the question on the item and takes it to Waiting; `resume --answer` saves the decider's exact words at the top of `## Current notes` in the same commit as the resume, which matters because a notes edit made by hand on the default branch would block the CLI's fast-forward. Lasting decisions go on the card or contract they govern, or `AGENTS.md`, through the normal change.

`next` selects only queued items with no hold and with all dependencies done. Claim changes a queued item to In flight while holding the same lock used by other CLI writes. Hold and resume never change the owner, so a held claim returns to In flight for the same person and no one else can claim it. Without a remote, writes change the local item files and only `finish` commits. Finishing records a UTC completion time; the rendered board shows the newest ten Done items and counts older ones. Because each change touches only its own item file, parallel work branches merge without board conflicts.

## Structure flow (ICM)

The skills apply ICM at fixed moments so the user never runs a second skill; the method, its templates, and its MIT credit live in [`icm/`](../icm/README.md). `scripts/pm_icm.py` holds the read-only checks behind the CLI's `walk`, `index`, and `refs` commands, and `pm.py` adds `--touches` on items and `correct`.

```mermaid
flowchart LR
  INIT["/pm:init"] -->|ordinary project| CAT[AGENTS.md catalog<br/>CLAUDE.md = @AGENTS.md]
  INIT -->|workflow being built| SK[.claude/skills/NAME/<br/>numbered stages, contracts]
  MAP["/pm:map"] --> SM[docs/pm/map/<br/>catalog, cards, effects]
  SM -->|pm.py index| IX[_index.md, generated]
  CAT --> WALK{pm.py walk<br/>+ cold walk}
  SK --> WALK
  IX --> WALK
  PLAN["/pm:plan"] -->|touches| IT[item: requester words<br/>+ cards or stages touched]
  IT --> WORK["/pm:work"]
  WORK -->|loads only| TC[touched cards or contracts<br/>and their named inputs]
  WORK --> VER[Verify against intent,<br/>Hits and Does not hit]
  WORK -->|pm.py correct| CO[corrections on the item]
  CO -->|3 of one kind, one source| FIX[Fix the source<br/>on the board]
```

`walk` reads only what Git tracks or would track (`git ls-files --cached --others --exclude-standard`), so ignored build output never counts. It fails on a missing or oversized entry file, two hand-maintained entry files in one folder, links that do not resolve, a numbered stage or map contract without its five sections, an oversized `CONTEXT.md`, a workflow skill that would not package, map cards with bad frontmatter, a map of two or more cards without its change-impact index, unfilled template lines, citations past the end of a file, a verified card without its evidence, a stale `_index.md`, a `touches` path on an item that is not done that no longer exists, and one walk (entry, catalog, largest card or contract) over about 8,000 tokens; softer findings are warnings. `index` renders `_index.md` from card frontmatter, so it is never hand-edited. `refs` lists what points at a file before a move (links, path mentions, bare-name mentions, symlinks) and refuses a destination already taken when names are compared case-folded. `correct` appends to the item's `corrections` list through the same `publish` transaction as `hold`; counts group by kind and source across all items, and a `fixed` entry resets that group. `touches` and `corrections` are written only when set, so items without them keep their exact format.

## Migration flow

`/pm:migrate` (reached from `/pm:init` when its scan finds an existing system) moves another task system onto the board in three separate commands, so the owner confirms between reading and writing.

```mermaid
flowchart LR
  OLD[Old system] -->|pm.py migrate scan| F[Findings and counts]
  OLD -->|pm.py migrate plan --from SOURCE| P[Plan JSON outside the repo]
  A[Agent, hand-made plan<br/>for sources without a reader] --> P
  P --> O{Owner confirms<br/>mapping and counts}
  O -->|yes| AP[pm.py migrate apply]
  AP -->|publish| I[docs/pm/items/ and config.json]
  O -->|knowledge that is not a task| PG[AGENTS.md, README.md, System map<br/>per placement.md]
  I --> V[Counts before and after]
  V --> R{Owner confirms removal}
  R -->|yes| GR[git rm the plan's retire paths]
```

`scan` and `plan` only read. A reader in `scripts/pm_migrate.py` (registered in `SOURCES`: `pm-0x` and `checklist`) returns a plan: items with the requester's words verbatim, a status of queued or in-flight, an optional hold, dependencies as old keys, and an optional issue number, plus the entries left in git history, knowledge to route, warnings, and the paths to retire. Sources without a reader get a hand-made plan of the same shape. `validate_plan` rejects a malformed plan before anything is written; the rules are listed in `docs/manual.md` section 5. `apply` ends each item id with a hash of the plan's `source` and the item's `key`, so a repeat run skips items whose id ends with that hash even if the title changed, writes through the same `publish` transaction as `add`, records every key the plan accounted for (items and history) under `migrated_from.<source>` in `docs/pm/config.json`, merged into the existing settings, and prints the board's counts afterwards. No command deletes the old system; removal is a separate step the agent takes with `git rm` after the owner's yes. The `SessionStart` hook prints a one-line pointer to `/pm:init` (or `/pm:migrate` when `docs/pm/config.json` exists) while any `docs/pm/tickets/T*.md` ticket id is missing from `migrated_from.pm-0x`, and a pointer to `/pm:map` while `docs/pm/CODEBASE.md` exists without `docs/pm/map/`.

## Inputs, outputs, and external dependencies

| Component | Input | Output | Depends on |
| --- | --- | --- | --- |
| `/pm:init` | Current project and existing instructions, the owner's choice of project kind | `docs/pm/`, a catalog `AGENTS.md` (or a workflow skill's stages), moves only after the owner's yes, a passing walk test; hands off to `/pm:migrate` when `migrate scan` finds an existing system | Claude Code file tools, `pm.py walk` and `refs`, `icm/` |
| `/pm:migrate` | The old system, its plan edited by the owner, the owner's yes | Items written from the plan, counts before and after, knowledge routed per the placement guide, old files removed only on confirmation | `scripts/pm.py migrate`, `scripts/pm_migrate.py`, `gh` for GitHub Issues |
| `/pm:plan` | Requester's exact words, optional dependencies, touched cards or stages, decision question or answer | Queued item detail published to the shared default branch | `scripts/pm.py add`, `set`, `hold`, `resume` |
| `/pm:work` | Queued item, its touched cards or contracts, and person's name | Claim before changes, code/doc and card updates, verify result, recorded corrections, current item notes, Done or In flight status | CLI lock, project checks, `pm.py walk`, `correct` |
| `/pm:status` | Project board | In flight owners, Queued, Waiting, Done, ready items, sources to fix | `scripts/pm.py board` |
| `/pm:map` | Repository source, metadata, docs, tests, an old `docs/pm/CODEBASE.md` | System map in `docs/pm/map/`: catalog, cards with citations and change impact, effects index, generated `_index.md`; the old file retired on the owner's yes | Claude Code read/write tools, `pm.py index`, `walk`, `refs` |
| `SessionStart` hook | Current project directory | Rendered board plus a note to claim items with `/pm:work` and add work with `/pm:plan`, in session context; a pointer to `/pm:init` for an unmigrated 0.x board, and to `/pm:map` for a 1.0 `CODEBASE.md` | `python3`; otherwise points to `docs/pm/items/` |
| `Stop` hook | Git status and item files | Reminder when code changed without an item update | `git`, bash |
| Optional `sync` | Item Markdown and GitHub repo | GitHub Issues created/updated; new issue numbers published in item files | `gh` CLI and opt-in mirror setting |

The model is selected by the Claude Code session. The plugin does not name a model or launch subagents. Its persistent data is plain Markdown; the CLI uses only Python's standard library. New item IDs combine a short title slug and random suffix, with a local duplicate check. The CLI uses OS file locking (`fcntl` on Unix-like systems and `msvcrt` on Windows); its remote claim path fetches the default branch and retries ownership checks after a rejected push. See the [README](../README.md) for the user-facing collaboration and GitHub mirror contract.
