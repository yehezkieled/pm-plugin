"""Shared fixture: builds a small docs/pm tree in a temp folder."""
from pathlib import Path

CONTEXT = """# Sample project

Some intro text.

## pm
flow: branch-pr
host: github
mirror: off
merge: ask
gates: tdd, checks, review, docs
check: make test
milestone: M1
tools: python3=yes gh=yes
routines: work=off audit=off
auto_cap: 2

## Other section
Not pm.
"""

ROADMAP = """# Roadmap

Milestones are ordered versions. Work moves top to bottom.

## M1: First usable version
Goal: a person can log in and see their list.
Epics: E01

## M2: Sharing
Goal: lists can be shared with another person.
Epics: E02

## Backlog
- Dark mode
- Export to CSV
"""

DECISIONS = """# Decisions

## 2026-09-01: Keep tickets in markdown
Context: agents and people both need to read them.
Decision: markdown files under docs/pm.
Consequences: GitHub is a mirror, not the source.
"""


def ticket(tid, title, epic, milestone, status, priority, depends_on="[]",
           owner="", auto="no", plan="none", issue="", pr="", extra_body=""):
    return f"""---
id: {tid}
title: {title}
epic: {epic}
milestone: {milestone}
status: {status}
priority: {priority}
depends_on: {depends_on}
owner: {owner}
auto: {auto}
plan: {plan}
issue: {issue}
pr: {pr}
---
## What
{title}.

## Why
Because the fixture says so.

## Acceptance
- [ ] Something testable happens.

## Subtasks
- [ ] first step

## Plan
{extra_body}
## Notes

## Proposed changes
"""


def epic(eid, title, milestone, status="in progress"):
    return f"""---
id: {eid}
title: {title}
milestone: {milestone}
status: {status}
---
## Goal
{title} so the milestone can ship.

## Tickets
(will be redrawn)

## Flow
(will be redrawn)
"""


def make_repo(root: Path) -> Path:
    root = Path(root)
    pm = root / "docs" / "pm"
    (pm / "epics").mkdir(parents=True)
    (pm / "tickets").mkdir(parents=True)
    (root / "CONTEXT.md").write_text(CONTEXT)
    (pm / "roadmap.md").write_text(ROADMAP)
    (pm / "decisions.md").write_text(DECISIONS)
    (pm / "epics" / "E01-login.md").write_text(epic("E01", "Login", "M1"))
    (pm / "epics" / "E02-sharing.md").write_text(epic("E02", "Sharing", "M2", "todo"))
    t = pm / "tickets"
    (t / "T001-counter.md").write_text(ticket("T001", "Add login attempt counter", "E01", "M1", "done", "P1"))
    (t / "T002-rate-limit.md").write_text(ticket("T002", "Rate-limit login attempts", "E01", "M1", "todo", "P1", "[T001]"))
    (t / "T003-lockout.md").write_text(ticket("T003", "Lock account after limit", "E01", "M1", "todo", "P0", "[T002]"))
    (t / "T004-log-format.md").write_text(ticket("T004", "Tidy login log format", "E01", "M1", "todo", "P2", "[]", auto="yes"))
    (t / "T005-session.md").write_text(ticket("T005", "Session cookie flags", "E01", "M1", "in progress", "P1", "[]", owner="agent-a", pr="34"))
    (t / "T006-share-link.md").write_text(ticket("T006", "Share link", "E02", "M2", "todo", "P1", "[]", auto="yes", plan="required"))
    (t / "T007-share-revoke.md").write_text(ticket("T007", "Revoke share", "E02", "M2", "todo", "P3", "[]", owner="agent-b"))
    return root
