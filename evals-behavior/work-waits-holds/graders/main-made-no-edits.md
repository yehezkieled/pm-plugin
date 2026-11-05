---
type: regex
target: trace
match: not_contains
pattern: '"name":"(Edit|Write|NotebookEdit)","input":[^\n]*"parent_tool_use_id":null'
---

The coordinating session itself never edits or writes a file: only a subagent (a pm:worker) does. In the trace a main-session message has `"parent_tool_use_id":null`.
