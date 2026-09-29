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

Each item is one file in `docs/pm/items/`, the only board state stored in git. `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm.py" board` renders In flight, Queued, Waiting, and the latest ten Done items from those files. `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm.py" next` shows queued items with completed dependencies. A hold keeps an item in Waiting, still owned by any claimer, until the decision is resolved. See the README for GitHub mirror behavior and its publication disclosure.

## Reply

Print the guide as is, then stop.
