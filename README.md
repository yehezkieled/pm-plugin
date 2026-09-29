# pm: a small project board for Claude Code

The plugin keeps a team's work as one Markdown file per item under `docs/pm/items/`; `/pm:status` renders the board from those files. It uses Claude Code skills as the workflow, so the active Claude model can be Sonnet, Opus, or another supported model.

```text
docs/pm/
├── config.json       # Board marker and GitHub mirror setting
└── items/            # One file per item: exact requester intent, status, owner, and current notes
```

## Skills

New here? The [step-by-step guide](docs/guide.html) walks one sample project through every command with real output. Open the file in a browser.

| Skill | Use | Main result |
| --- | --- | --- |
| `/pm:init` | Set up the board and concise `AGENTS.md` guidance | Board and project instructions |
| `/pm:plan` | Record a request in the requester's exact words | Queued item with a separate detail file |
| `/pm:work` | Claim and build one item | In-flight claim, code changes, updated item notes |
| `/pm:status` | See current work, owners, holds, and what is ready | Board and dependency-aware next items |
| `/pm:map` | Understand the current codebase | `docs/pm/CODEBASE.md` with Mermaid diagrams |
| `/pm:help` | See the short command guide | Skill and CLI reference |

## Collaboration and item flow

The item files are the only board state in git. The board is rendered on demand, showing In flight, Queued, Waiting, and the latest ten Done items; no generated file is committed. When a remote is configured, `/pm:plan` and the other board updates (`add`, `set`, `hold`, `resume`, and `claim`) commit the item file and push it to the default branch, so every clone sees the same items. `/pm:work` claims an item before code changes, and the claim is published the same way before work starts; completion is committed on the work branch and becomes shared when its PR is merged. Items can depend on other items, and a decision hold moves an item to Waiting without releasing its claim; resuming returns a claimed item to its owner In flight. The [architecture guide](docs/architecture.md) documents the coordination and board lifecycle details.

GitHub Issues sync is off by default. Enabling it with `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm.py" mirror github` authorizes publishing each item's requester intent and current notes to this repository's GitHub Issues audience when `.../pm.py sync` runs. The command prints this disclosure when enabled, and the setting is stored in `docs/pm/config.json`. New issue numbers are saved in the item files and published to the shared default branch like other board updates, so other clones update the same issues. The local Markdown files remain the source of truth.

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
