---
type: regex
target: {source: file, path: .git/pm-workers/sessions/word-count-3f9a1c.json}
pattern: '"checkout": "[^"]*/\.claude/worktrees/pm-word-count-3f9a1c"'
---

---
type: regex
target: {source: file, path: .git/pm-workers/sessions/title-case-7d2e4b.json}
pattern: '"checkout": "[^"]*/\.claude/worktrees/pm-title-case-7d2e4b"'
---

Each item's worker session ran in its own git worktree, per the session record `pm.py worker start` keeps.
