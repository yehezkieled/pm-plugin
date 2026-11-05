---
type: regex
target: trace
pattern: '"name":"Bash","input":\{"command":"[^\n]*pm\.py[^\n]*\bhold\s+[^-\s][^\n]*"parent_tool_use_id":"toolu_'
---

The `pm.py hold` call comes from a worker (a subagent message, whose `parent_tool_use_id` is a tool use id), not from the coordinating session.
