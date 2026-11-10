---
type: regex
target: trace
match: not_contains
pattern: '"name":"Agent"'
---

The coordinating session starts no subagent: ticket work goes to worker sessions, and only a worker starts a validator subagent.
