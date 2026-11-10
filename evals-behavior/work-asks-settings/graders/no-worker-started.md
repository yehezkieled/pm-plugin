---
type: regex
target: trace
match: not_contains
pattern: 'Started worker session'
---
---
type: regex
target: {source: file, path: docs/pm/config.json}
match: not_contains
pattern: '"workers"'
---

No worker session starts and no default is recorded until the person chooses: the plugin never picks a model or effort.
