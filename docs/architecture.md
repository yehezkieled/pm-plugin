# Plugin architecture

The plugin uses Claude Code skills for conversational workflow, a Python standard-library CLI for shared board operations, and project-owned Markdown for state. It starts no reviewer agents and has no scheduled runner.

## Components and dependencies

```mermaid
flowchart LR
  U[User request] --> S[Claude Code skills<br/>skills/*/SKILL.md]
  S --> C[scripts/pm.py<br/>board operations]
  C --> B[docs/pm/BOARD.md<br/>generated status view]
  C --> I[docs/pm/items/slug-random.md<br/>intent and current notes]
  C --> A[docs/pm/archive.md<br/>older completed summaries]
  H[Claude Code hooks<br/>hooks/hooks.json] --> SH[hooks/session-start.sh<br/>hooks/stop.sh]
  SH --> C
  G{Mirror enabled?} -->|yes| GH[GitHub Issues via gh]
  C -. sync command .-> G
  I --> B
  I --> A
```

Sources: [plugin manifest](../.claude-plugin/plugin.json), [skills](../skills/), [CLI](../scripts/pm.py), [hooks](../hooks/).

## Work and data flow

```mermaid
sequenceDiagram
  actor Person
  participant Skill as Claude Code skill
  participant CLI as scripts/pm.py
  participant Lock as local file lock
  participant Remote as remote default branch
  participant Item as docs/pm/items/slug-random.md
  participant Board as docs/pm/BOARD.md
  Person->>Skill: request or start work
  Skill->>CLI: add / claim / hold / finish
  CLI->>Lock: acquire exclusive local file lock
  CLI->>Remote: fetch and read latest board
  CLI->>Item: check claim, status, and dependencies
  CLI->>Remote: push claim commit without force
  Remote-->>CLI: accept one update or reject a race
  CLI->>Remote: fetch and re-check after rejection
  CLI->>Board: fast-forward local default branch after accepted claim
  CLI-->>Skill: item path and current board state
  Skill-->>Person: work result and next ready item
```

`next` selects only queued items with no hold and with all dependencies done. Claim changes a queued item to In flight while holding the same lock used by other CLI writes. Finishing assigns an increasing completion order; the board shows the newest ten Done summaries and older summaries move to `archive.md`. The detail files remain available.

## Inputs, outputs, and external dependencies

| Component | Input | Output | Depends on |
| --- | --- | --- | --- |
| `/pm:init` | Current project and existing instructions | `docs/pm/`, concise `AGENTS.md` when absent | Claude Code file tools, Python CLI |
| `/pm:plan` | Requester's exact words, optional dependencies or decision question | Queued item detail and regenerated board | `scripts/pm.py add`, `set`, `hold` |
| `/pm:work` | Queued item and person's name | Claim before changes, code/doc updates, current item notes, Done or In flight status | CLI lock and project checks |
| `/pm:status` | Project board | In flight owners, Queued, Waiting, Done, ready items | `scripts/pm.py board` |
| `/pm:map` | Repository source, metadata, docs, tests | `docs/pm/CODEBASE.md` with component and flow diagrams | Claude Code read/write tools |
| `SessionStart` hook | Current project directory | Board text in session context | `python3`; falls back to raw board Markdown |
| `Stop` hook | Git status and board files | Reminder when code changed without an item update | `git`, bash |
| Optional `sync` | Item Markdown and GitHub repo | GitHub Issues created/updated; issue ID saved in item | `gh` CLI and opt-in mirror setting |

The model is selected by the Claude Code session. The plugin does not name a model or launch subagents. Its persistent data is plain Markdown; the CLI uses only Python's standard library. New item IDs combine a short title slug and random suffix, with a local duplicate check. The CLI uses OS file locking (`fcntl` on Unix-like systems and `msvcrt` on Windows); its remote claim path fetches the default branch and retries ownership checks after a rejected push. See the [README](../README.md) for the user-facing collaboration and GitHub mirror contract.
