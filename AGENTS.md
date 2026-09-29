# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: build, test, release, architecture, and sharp-edge notes that should travel with the code.

- Add durable project-specific notes here as they are discovered through real work.
- Product scope and installation are documented in `README.md`; component and data flow are mapped in `docs/architecture.md`.
- Keep the skill instructions, `scripts/pm.py`, hook registrations, and those two docs aligned when changing the workflow. Run `python3 -m unittest discover -s tests -v` to check the board CLI.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
