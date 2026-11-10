---
type: regex
target: {source: file, path: .git/pm-workers/sessions/word-count-3f9a1c.log}
pattern: '"subagent_type":\s*"pm:validator"'
---
---
type: regex
target: trace
pattern: 'On branch pm/word-count-3f9a1c: status done; validation pass at'
---

---
type: regex
target: {source: file, path: .git/pm-workers/sessions/title-case-7d2e4b.log}
pattern: '"subagent_type":\s*"pm:validator"'
---
---
type: regex
target: trace
pattern: 'On branch pm/title-case-7d2e4b: status done; validation pass at'
---

Each worker session started its own validator subagent, and each item's branch records a pass and Done.
