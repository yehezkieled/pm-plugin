# pm: a small project board for Claude Code

The plugin keeps a team's current work in `docs/pm/BOARD.md` and one Markdown detail file per item. It uses Claude Code skills as the workflow, so the active Claude model can be Sonnet, Opus, or another supported model.

```text
docs/pm/
├── BOARD.md          # In flight, Queued, Waiting, and the latest 10 Done items
├── items/             # One file per item: exact requester intent and current notes
└── archive.md         # Older completed item summaries
```

## Skills

| Skill | Use | Main result |
| --- | --- | --- |
| `/pm:init` | Set up the board and concise `AGENTS.md` guidance | Board and project instructions |
| `/pm:plan` | Record a request in the requester's exact words | Queued item with a separate detail file |
| `/pm:work` | Claim and build one item | In-flight claim, code changes, updated item notes |
| `/pm:status` | See current work, owners, holds, and what is ready | Board and dependency-aware next items |
| `/pm:map` | Understand the current codebase | `docs/pm/CODEBASE.md` with Mermaid diagrams |
| `/pm:help` | See the short command guide | Skill and CLI reference |

## Collaboration and item flow

New item IDs use a short title slug plus a random suffix, re-rolled if already present locally. This makes independently added items across clones unlikely to collide without shared ID coordination. `/pm:work` claims an item before inspecting or changing product code. With a remote configured, the CLI fetches the remote default branch, creates a claim commit there, and pushes it without force. Git accepts only one competing update; a rejected claimant fetches again and sees the winner's owner. The work branch is created after the claim push succeeds. Without a remote, a local file lock prevents simultaneous claims in the same clone. Items can depend on other item IDs; `pm.py next` skips dependencies that are not done. A decision hold moves an item to Waiting with a reason and an optional review date. Finishing items keeps the newest ten on the board and adds older summaries to `archive.md`; the full item detail stays under `items/`.

GitHub Issues sync is off by default. Enabling it with `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm.py" mirror github` authorizes publishing each item's requester intent and current notes to this repository's GitHub Issues audience when `.../pm.py sync` runs. The command prints this disclosure when enabled. The local Markdown files remain the source of truth.

Hooks print the board at session start and remind the agent at stop when code changed without an item detail update. They do not block ordinary coding sessions.

## Install

```bash
claude plugin marketplace add /path/to/pm-plugin
claude plugin install pm@pm-plugin
```

For local development:

```bash
claude --plugin-dir /path/to/pm-plugin
```

The helper CLI uses Python 3's standard library. Skills can still guide a manual edit if Python is unavailable, except atomic claiming and GitHub sync, which require the CLI.

## Verify

```bash
python3 -m unittest discover -s tests -v
```

For a map of the plugin's own files and runtime flow, see [`docs/architecture.md`](docs/architecture.md). `/pm:map` creates a corresponding map for the project where the plugin is installed.
