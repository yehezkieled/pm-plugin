# pm: a small project board for Claude Code

The plugin keeps a team's work as one Markdown file per item under `docs/pm/items/`. Each item is done by its own full, interactive Claude Code worker session on your usual sign-in, and checked by a separate validator before Done. It also structures the repository so an agent loads only what a task needs, following ICM (below).

```text
AGENTS.md             # The catalog: where things go (each place a link), what to update when a task finishes, every-session rules (CLAUDE.md is @AGENTS.md)
docs/pm/
├── config.json       # Board marker and the worker model defaults
├── items/            # One file per item: exact requester intent, what it touches, status, owner, current notes
└── map/              # Optional System map from /pm:map: one card per part, what a change hits
```

| Skill | Use |
| --- | --- |
| `/pm:init` | Set up the board and a small `AGENTS.md` catalog whose Where things go table fits the project's shape and links every folder, so the structure stays current |
| `/pm:plan` | Record a request in the requester's exact words |
| `/pm:work` | Do any project work: each item goes to its own worker session, which claims, builds, commits, and gets it validated |
| `/pm:status` | See what is in flight, waiting, and ready |
| `/pm:map` | Map the code as cards that say what a change hits |
| `/pm:help` | The short command guide |

```text
you ──▶ coordinating session ──▶ worker session (full session, own copy of the project)
         ▲   files, relays, checks        claim ─▶ build ─▶ commit ─▶ validator subagent ─▶ finish
         └──────── report, or a question for you ◀──┘
```

**Everything else is in the [manual](docs/manual.md):** install and update, setup, project shapes, the System map, worker sessions and their settings, how the board is shared, hooks, how the plugin is built, and troubleshooting. Where each kind of knowledge goes is in [placement.md](docs/placement.md).

## Install

```bash
claude plugin marketplace add yehezkieled/pm-plugin     # or a local path
claude plugin install pm@pm-plugin
```

Then run `/pm:init` in a project. Needs Python 3 and Git.

## Credit

The structure follows Jake Van Clief and David McDermott, *Interpretable Context Methodology: Folder Structure as Agent Architecture* ([arXiv:2603.16021](https://arxiv.org/abs/2603.16021)). The guides and templates in [`icm/`](icm/README.md) are adapted from [icm-architect](https://github.com/RinDig/icm-architect) (MIT, © 2026 Jake Van Clief) and the [ICM repository](https://github.com/RinDig/Interpretable-Context-Methodology) (MIT); see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Develop

```bash
claude --plugin-dir /path/to/pm-plugin
python3 -m unittest discover -s tests -v
```

Skill-routing evals across models: [`evals/README.md`](evals/README.md).
