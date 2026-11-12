# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: build, test, release, architecture, and sharp-edge notes that should travel with the code.

- Add durable project-specific notes here as they are discovered through real work.
- `README.md` is a short overview; `docs/manual.md` is the one manual (setup, workers, the board, hooks, and component and data flow).
- Keep the skill instructions, `scripts/pm.py`, `scripts/pm_icm.py` (walk test, index, refs, and places checks), `icm/` (the ICM method, the project shapes behind `AGENTS.md` › Where things go, and the templates the skills follow), hook registrations, `docs/placement.md` (the single guide to where knowledge goes; skills link to it rather than copy it), and `docs/manual.md` aligned when changing the workflow. Skill `description:` lines are what models use to choose a skill: keep them short with a "Use when" clause (enforced by tests); after changing one, re-run the routing evals in `evals/README.md` on several models. Run `python3 -m unittest discover -s tests -v` to check the board CLI, skill descriptions, and that the manual names every command.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
