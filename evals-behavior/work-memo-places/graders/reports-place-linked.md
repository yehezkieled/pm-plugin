---
type: regex
pattern: '\[`reports/[^`]*`\]\(reports/'
match: contains
target:
  source: file
  path: AGENTS.md
---
