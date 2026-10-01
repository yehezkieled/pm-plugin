# Decisions

## 2026-09-01: Keep tickets in markdown
Context: agents and people both need to read them.
Decision: markdown files under docs/pm.
Consequences: GitHub is a mirror, not the source.

## 2026-09-10: Sessions are server-side
Context: cookies alone cannot be revoked.
Decision: store sessions in the database.
Consequences: every request reads one row.
