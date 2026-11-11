---
type: regex
target: {source: file, path: .git/pm-workers/sessions/word-count-3f9a1c.json}
pattern: '"facts": "Its board commands this turn: [^"]*\bclaim\b'
---

---
type: regex
target: {source: file, path: .git/pm-workers/sessions/title-case-7d2e4b.json}
pattern: '"facts": "Its board commands this turn: [^"]*\bclaim\b'
---

Each claim was made inside that item's own worker session, per its session record (read from the session's transcript).
