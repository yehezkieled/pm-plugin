---
name: map
description: "Map the codebase with diagrams and an architecture overview (docs/pm/map), with what a change to each part hits. Use when the user asks \"how does this codebase work\", \"map the code\", \"what would changing X break\", or how the modules fit. Use this, not your own file search. Not for tracking tasks."
argument-hint: "[area, optional]"
---

# /pm:map

Builds or refreshes the System map in `docs/pm/map/`, ICM's form for a repository that agents will edit. Read `${CLAUDE_PLUGIN_ROOT}/icm/system-map.md` first; starters for the catalog, contract, and cards are in `${CLAUDE_PLUGIN_ROOT}/icm/templates/`. `pm.py` below means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm.py"`. If `/pm:init` has not been run, create only `docs/pm/map/`, without board items. With an area argument, map or refresh that cluster and the cards its change-impact rows name.

1. Inventory, read-only: the tree, entry points, package and build metadata, configuration, tests, scripts, and docs; trace imports, commands, requests and events, persisted data, and outputs from the source. Read `docs/pm/CODEBASE.md` if it exists; its facts are absorbed into cards. Propose the clusters, the nouns in each with their universe (live, leftover, ghost), and the movements that repeat. Stop for the owner's yes, and stop the same way after each later step unless they said to go straight through.
2. Catalog: write `docs/pm/map/AGENTS.md` from `map-AGENTS.md` (the Names table of product words and code names, the clusters, where to go; under 60 lines), `docs/pm/map/CLAUDE.md` as the one line `@AGENTS.md`, `CONTEXT.md` from `map-CONTEXT.md`, copy `object.md` and `process.md` into `_templates/`, and a stub card for every noun. Run `pm.py index`. Add one row to the root `AGENTS.md` pointing at `docs/pm/map/AGENTS.md`, and show the edit.
3. Cards: fill each object card from the source, citing `path:line`; when a comment and the code disagree, the code wins and the card says so. Write process cards only for movements that run. Once the map has two or more cards, write `effects/CONTEXT.md` (if you change X, open these cards) and link it from the map's `AGENTS.md`; and ask the owner what points into the repository from outside.
4. Verify: re-read the cited lines behind every Hits and Does not hit, and behind every card you mark verified. Mark a card `verified` only with today's date, the commit (`git rev-parse --short HEAD`), and citations.
5. Run `pm.py index`, then `pm.py walk`, then answer each cold-walk question in `${CLAUDE_PLUGIN_ROOT}/icm/method.md` and `system-map.md` from the files alone, noting the file you opened and the answer in one line each. This cold walk is required; a passing `pm.py walk` is only the first half. Fix the structure until both pass; the map is not done, and you must not reply, until the cold walk is answered.
6. When every fact from `docs/pm/CODEBASE.md` is on a card, run `pm.py refs docs/pm/CODEBASE.md`, point each referrer at the map, and on the owner's yes remove the old file with `git rm`.

When refreshing, re-read the source of the changed components, update their cards with a new date and commit, and set `status: stale` on any card you know is behind but did not re-verify. Architecture belongs on the cards and nowhere else: do not copy it into `AGENTS.md` or `README.md` (see `${CLAUDE_PLUGIN_ROOT}/docs/placement.md`). Map what a maintainer needs; do not card every file.

## Reply

Talk in outcomes, not mechanics: plain words, no internal jargon (say "waiting on your decision", not "hold"). The reply must stand alone: lead with the result, then any decision needed. No progress narration. Mark unverified claims `[UNSURE]`. Lead with a two-line summary of how the system works, then the diagrams drawn in ASCII so they read as plain text in a terminal (the clusters and how they connect, and the main flow; use Mermaid only when the user asks for it); prefer diagrams over prose. Then the cards written or refreshed, by status, and the walk test result (both halves, the cold answers in one line each; a reply without the cold answers is incomplete).
