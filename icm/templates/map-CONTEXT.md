# docs/pm/map: the System map of {project name}

One job: keep a walkable edit map of this repository, so an agent loads one card instead of the tree.

## Inputs

- Working (this run): the request or item that asked for the map, and the source files it names.
- Reference (every run): `_templates/object.md` and `_templates/process.md`; their frontmatter is the schema.
- Reference (every run): [AGENTS.md](AGENTS.md) for the names and clusters already chosen.

Do not load: the whole `objects/` folder; open the cards the change is about.

## Process

1. Inventory the area: entry points, types, tables, modules, and the movements that repeat. Stop for the owner's yes on the clusters.
2. Copy a template for each noun; fill it from the source, citing `path:line`.
3. Write process cards only for movements that run; update `effects/CONTEXT.md`.
4. Run `pm.py index`, then `pm.py walk`.

## Outputs

- Cards under `objects/` and `processes/`, `effects/CONTEXT.md`, the regenerated `_index.md`.

## Verify

Re-read the cited source lines for every Hits and Does not hit claim, and for every card marked verified; a claim the source no longer supports makes the card stale.

## Human check

The owner picks one card about code they know well and confirms its "If you change this" matches what they would expect to break.
