"""One-way mirror of docs/pm to an issue host. The markdown is the source.

milestone -> host milestone, epic -> issue labelled `epic` with a task list,
ticket -> issue with epic and priority labels. Numbers are written back into
the `issue:` field so the next sync updates instead of creating.
"""
from __future__ import annotations

from pathlib import Path

import pm_lib


def milestone_title(m: pm_lib.Milestone) -> str:
    return f"{m.id}: {m.title}"


def ticket_body(t: pm_lib.Ticket) -> str:
    parts = [f"Epic: {t.epic} | Milestone: {t.milestone} | Priority: {t.priority}"]
    if t.depends_on:
        parts[0] += " | Depends on: " + ", ".join(t.depends_on)
    for heading in ("What", "Why", "Acceptance"):
        text = pm_lib.section_text(t.body, heading).strip()
        if text:
            parts.append(f"## {heading}\n{text}")
    parts.append(f"Source: docs/pm/tickets/{t.path.name}" if t.path else "")
    return "\n\n".join(p for p in parts if p)


def epic_body(e: pm_lib.Epic, tickets: list[pm_lib.Ticket]) -> str:
    goal = pm_lib.section_text(e.body, "Goal").strip()
    lines = []
    for t in tickets:
        box = "x" if t.status in pm_lib.CLOSED else " "
        ref = f"#{t.issue} " if t.issue else ""
        tail = " (dismissed)" if t.status == "dismissed" else ""
        lines.append(f"- [{box}] {ref}{t.id} {t.title}{tail}")
    body = f"## Goal\n{goal}\n\n## Tickets\n" + ("\n".join(lines) or "(none yet)")
    if e.path:
        body += f"\n\nSource: docs/pm/epics/{e.path.name}"
    return body


def sync(root: Path, adapter, dry_run: bool = False) -> list[str]:
    root = Path(root)
    log: list[str] = []
    milestones = pm_lib.load_milestones(root)
    tickets = pm_lib.load_tickets(root)
    epics = pm_lib.load_epics(root)
    by_milestone = {m.id: milestone_title(m) for m in milestones}

    existing = adapter.list_milestones()
    for m in milestones:
        title = milestone_title(m)
        if title in existing:
            continue
        goal = pm_lib.milestone_goal(root, m.id)
        if dry_run:
            log.append(f"would create milestone {title}")
        else:
            adapter.create_milestone(title, goal)
            log.append(f"milestone {title} created")

    labels = {"epic"} | {t.priority for t in tickets} | {t.epic for t in tickets if t.epic}
    if not dry_run:
        for name in sorted(labels):
            adapter.ensure_label(name)

    for t in tickets:
        title = f"{t.id}: {t.title}"
        body = ticket_body(t)
        lbls = [t.epic, t.priority] if t.epic else [t.priority]
        ms = by_milestone.get(t.milestone)
        if not t.issue:
            if dry_run:
                log.append(f"would create issue for {t.id}")
                continue
            number = adapter.create_issue(title, body, lbls, ms)
            pm_lib.set_fields(root, t.id, issue=str(number))
            t.issue = str(number)
            log.append(f"{t.id} created as #{number}")
        elif not dry_run:
            adapter.update_issue(int(t.issue), title, body, lbls, ms)
            log.append(f"{t.id} updated #{t.issue}")
        else:
            log.append(f"would update #{t.issue} for {t.id}")
        if t.status == "done" and t.issue and not dry_run:
            adapter.close_issue(int(t.issue))
        elif t.status == "dismissed" and t.issue and not dry_run:
            adapter.close_issue(int(t.issue), reason="not planned")

    for e in epics:
        e_tickets = [t for t in tickets if t.epic == e.id]
        try:
            e_tickets = pm_lib.flow_order(e_tickets)
        except ValueError:
            pass
        title = f"{e.id}: {e.title}"
        body = epic_body(e, e_tickets)
        ms = by_milestone.get(e.milestone)
        number = str(e.meta.get("issue", "") or "")
        if not number:
            if dry_run:
                log.append(f"would create issue for {e.id}")
                continue
            number = str(adapter.create_issue(title, body, ["epic"], ms))
            meta = dict(e.meta)
            meta["issue"] = number
            e.path.write_text(pm_lib.dump_frontmatter(meta, e.body))
            log.append(f"{e.id} created as #{number}")
        elif not dry_run:
            adapter.update_issue(int(number), title, body, ["epic"], ms)
            log.append(f"{e.id} updated #{number}")
        else:
            log.append(f"would update #{number} for {e.id}")
        if e_tickets and all(t.status in pm_lib.CLOSED for t in e_tickets) and not dry_run:
            adapter.close_issue(int(number))
    return log
