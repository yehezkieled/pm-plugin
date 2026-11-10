---
type: regex
target: trace
pattern: 'Its board commands this turn: [^;"]*\bclaim\b'
---
---
type: regex
target: trace
pattern: 'Its board commands this turn: [^;"]*\bfinish\b'
---

The worker's own session claimed and finished the item: the report `pm.py worker` prints lists the board commands read from that session's log.
