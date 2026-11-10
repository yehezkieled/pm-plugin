---
type: regex
target: trace
match: not_contains
pattern: '"name":"(Edit|Write|NotebookEdit)"'
---

The coordinating session never edits or writes a file. Since 1.4 the work happens in separate worker sessions, whose calls are in their own logs, not in this trace.
