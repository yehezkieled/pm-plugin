---
name: map
description: Inspect a codebase and explain its infrastructure, dependencies, data flow, logic, inputs, and outputs with diagrams. Use when the user asks how a codebase works or wants an architecture overview.
argument-hint: "[area, optional]"
---

# /pm:map

Create or refresh `docs/pm/CODEBASE.md` for the current project. If `/pm:init` has not been run, create `docs/pm/` for this map without inventing project-management items.

Inspect the repository structure, entry points, package/build metadata, configuration, tests, scripts, and docs. Trace imports, commands, requests/events, persisted data, and generated outputs from the actual source. For a large repository, map the main system and the requested area in more detail. Cite source paths near each diagram node or flow.

Write a compact, accurate report with:

1. A Mermaid component diagram showing major folders/services and their dependencies.
2. A Mermaid flow diagram from user/system input through the main logic to persisted or returned output.
3. A table of important components with responsibility, inputs, outputs, and dependencies.
4. The main commands or runtime entry points and where their output goes.
5. Unknowns or inferred edges, clearly labeled `[UNSURE]`.

Keep the map focused on architecture a maintainer needs; do not list every file. Re-read the source for changed components whenever refreshing the document. Print the diagrams and the report's main paths in the response.
