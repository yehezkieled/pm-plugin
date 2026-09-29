---
name: help
description: Show the short pm plugin command guide. Use when the user asks how to use project tracking.
---

# /pm:help

```text
/pm:init             Set up docs/pm and concise AGENTS.md guidance
/pm:plan <request>   Record a request verbatim as a queued item
/pm:work [item-id]   Claim first, then implement and update notes
/pm:status           Show owners, waiting items, and what's ready
/pm:map [area]       Write a codebase overview with diagrams
/pm:help             Show this guide
```

The project board is `docs/pm/BOARD.md`; item details are in `docs/pm/items/`; completed summaries older than the latest ten are in `docs/pm/archive.md`. `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm.py" next` shows queued items with completed dependencies. A hold keeps an item in Waiting until the decision is resolved. GitHub Issues sync is optional and off by default. `pm.py mirror github` enables it and authorizes publishing requester intent and current notes to the repository's GitHub Issues audience when `pm.py sync` runs.
