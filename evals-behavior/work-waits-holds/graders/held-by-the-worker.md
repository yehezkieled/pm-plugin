---
type: regex
target: trace
pattern: 'Its board commands this turn: [^;"]*\bhold\b'
---

The `pm.py hold` came from the worker's own session (read from its log by `pm.py worker`), not from the coordinating session.
