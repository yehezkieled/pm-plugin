#!/usr/bin/env python3
"""Command line for the pm plugin. Standard library only.

  pm.py board                      one-page board
  pm.py line                       one-line summary (empty when no docs/pm)
  pm.py next [--routine] [--json]  pick the next ticket
  pm.py flow <Exx> | --all         redraw Tickets + Flow sections of an epic
  pm.py claim <Txxx> <owner>       set owner and status in progress
  pm.py release <Txxx>             clear owner, status back to todo
  pm.py ready <Txxx> [--early]     grilled: What, Why, Acceptance settled (--early: blocked ticket, on the user's word)
  pm.py set <Txxx> key=value ...   change frontmatter fields
  pm.py validate                   list problems; exit 1 if any
  pm.py backup                     forks only: copy docs/pm and CONTEXT.md to $PM_BACKUP_DIR or ~/.pm-backup
  pm.py next-id ticket|epic|milestone
  pm.py config [--json]            the pm block of CONTEXT.md with defaults
  pm.py new ticket|epic|milestone  create a file from the template
  pm.py sync [--dry-run]           mirror to the host named in the pm block
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_lib  # noqa: E402

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"


def fill(template: str, **values) -> str:
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", str(value))
    return template


def fail(message: str, code: int = 1):
    print(message, file=sys.stderr)
    sys.exit(code)


def need_pm(root: Path):
    if not pm_lib.has_pm(root):
        fail(f"no docs/pm/roadmap.md under {root}. Run /pm:init first.")


def ticket_summary(t: pm_lib.Ticket) -> str:
    deps = f" after {', '.join(t.depends_on)}" if t.depends_on else ""
    return f"{t.id}  {t.title}  ({t.epic}, {t.milestone}, {t.priority}, plan: {t.plan}{deps})"


def ticket_json(t: pm_lib.Ticket) -> dict:
    return {
        "id": t.id, "title": t.title, "epic": t.epic, "milestone": t.milestone,
        "status": t.status, "priority": t.priority, "depends_on": t.depends_on,
        "owner": t.owner, "auto": t.auto, "plan": t.plan, "plan_approved": t.plan_approved, "ready": t.ready,
        "issue": t.issue, "pr": t.pr, "path": str(t.path),
    }


# ---------------------------------------------------------------- commands

def cmd_board(root, args):
    need_pm(root)
    print(pm_lib.render_board(root))


def cmd_line(root, args):
    print(pm_lib.board_line(root))


def cmd_next(root, args):
    need_pm(root)
    tickets = pm_lib.load_tickets(root)
    t = pm_lib.pick_next(tickets, root, routine=args.routine)
    if args.json:
        print(json.dumps(ticket_json(t) if t else {}))
    else:
        grill = [g.id for g in pm_lib.to_grill(tickets)]
        if t:
            print(ticket_summary(t))
        elif grill:
            print(f"none (to grill: {', '.join(grill)}; a ticket is worked only after /pm:grill marks it ready)")
        else:
            print("none")
        if t and args.routine:
            print(f"routine: claim with `pm.py claim {t.id} routine-{t.id.lower()}`; never merge, stop at status=review")


def cmd_flow(root, args):
    need_pm(root)
    epic_ids = [e.id for e in pm_lib.load_epics(root)] if args.all else [args.epic]
    if not epic_ids or epic_ids == [None]:
        fail("give an epic id or --all", 2)
    for epic_id in epic_ids:
        try:
            text = pm_lib.update_epic(root, epic_id)
        except KeyError as exc:
            fail(str(exc))
        print(f"{epic_id}\n{text}\n")


def cmd_claim(root, args):
    need_pm(root)
    tickets = {t.id: t for t in pm_lib.load_tickets(root)}
    t = tickets.get(args.ticket)
    if not t:
        fail(f"unknown ticket {args.ticket}")
    if t.owner and t.owner != args.owner and not args.force:
        fail(f"{t.id} already claimed by {t.owner} (use --force to take it over)")
    if t.status == "done":
        fail(f"{t.id} is already done")
    open_deps = [f"{d} ({tickets[d].status})" for d in t.depends_on if d in tickets and tickets[d].status != "done"]
    if open_deps and not args.force:
        fail(f"{t.id} depends on {', '.join(open_deps)}: finish that first, or use --force to start it out of order")
    if not t.ready and not args.force:
        fail(f"{t.id} is not grilled yet (ready: no): run /pm:grill {t.id} first so What, Why and Acceptance are settled, or use --force to skip the grill")
    pm_lib.set_fields(root, t.id, owner=args.owner, status="in progress")
    print(f"{t.id} claimed by {args.owner}: {t.title}")
    if t.plan == "required" and not t.plan_approved:
        print("plan: required and not approved -> write the ## Plan section first, then get the user's approval before any code edit. Headless run: stop after the plan.")
    cfg = pm_lib.read_config(root)
    commit = f'git add docs/pm && git commit -m "pm: claim {t.id}"'
    if cfg.get("flow") == "branch-pr":
        commit += " && git push"
    print(f"next: {commit}")
    if cfg.get("flow") in ("branch-pr", "branch-local"):
        slug = t.path.stem.split("-", 1)[1] if t.path and "-" in t.path.stem else pm_lib.slug(t.title)
        print(f"then: git switch -c {t.id.lower()}-{slug}")


def cmd_backup(root, args):
    """Forks keep docs/pm out of git; copy it somewhere a reset cannot reach."""
    exclude = root / ".git" / "info" / "exclude"
    if not (exclude.exists() and "docs/pm" in exclude.read_text()):
        print("not a fork: docs/pm is tracked by git, no backup needed")
        return
    dest = Path(os.environ.get("PM_BACKUP_DIR") or Path.home() / ".pm-backup") / root.name
    shutil.copytree(root / "docs" / "pm", dest / "docs" / "pm", dirs_exist_ok=True)
    if (root / "CONTEXT.md").exists():
        shutil.copy2(root / "CONTEXT.md", dest / "CONTEXT.md")
    print(f"backup copy: {dest}")


def cmd_release(root, args):
    need_pm(root)
    try:
        t = pm_lib.set_fields(root, args.ticket, owner="", status="todo")
    except KeyError as exc:
        fail(str(exc))
    print(f"{t.id} released")


def cmd_freeze(root, args):
    need_pm(root)
    try:
        t = pm_lib.set_fields(root, args.ticket, tests="frozen")
    except (KeyError, ValueError) as exc:
        fail(str(exc))
    print(f"{t.id}: tests frozen. Test files stay as they are while the fix is written; `pm.py unfreeze {t.id} --reason \"...\"` lifts it.")


def cmd_unfreeze(root, args):
    need_pm(root)
    try:
        t = pm_lib.set_fields(root, args.ticket, tests="open")
        pm_lib.add_note(root, t.id, f"Test change: {args.reason.strip()}")
    except (KeyError, ValueError) as exc:
        fail(str(exc))
    print(f"{t.id}: tests open again; reason recorded under Notes")


def cmd_dismiss(root, args):
    need_pm(root)
    try:
        t = pm_lib.set_fields(root, args.ticket, status="dismissed", owner="")
        pm_lib.add_note(root, t.id, f"Dismissed: {args.reason.strip()}")
    except (KeyError, ValueError) as exc:
        fail(str(exc))
    if t.epic in {e.id for e in pm_lib.load_epics(root)}:
        pm_lib.update_epic(root, t.epic)
    print(f"{t.id} dismissed: {args.reason.strip()}")


def cmd_ready(root, args):
    need_pm(root)
    tickets = {t.id: t for t in pm_lib.load_tickets(root)}
    if args.ticket not in tickets:
        fail(f"unknown ticket {args.ticket}")
    try:
        t = pm_lib.set_fields(root, args.ticket, early=args.early, ready="yes")
    except ValueError as exc:
        fail(str(exc))
    waits = pm_lib.open_deps(t, tickets)
    if waits:
        print(f"{t.id} ready (grilled early: waits on {', '.join(waits)}; re-check with /pm:grill {t.id} once that is done)")
    else:
        print(f"{t.id} ready: start it with /pm:work {t.id}")


def cmd_set(root, args):
    need_pm(root)
    fields = {}
    for pair in args.pairs:
        key, sep, value = pair.partition("=")
        if not sep:
            fail(f"expected key=value, got {pair}", 2)
        fields[key.strip()] = value.strip()
    try:
        t = pm_lib.set_fields(root, args.ticket, **fields)
    except (KeyError, ValueError) as exc:
        fail(str(exc))
    if "status" in fields or "depends_on" in fields:
        pm_lib.update_epic(root, t.epic) if t.epic in {e.id for e in pm_lib.load_epics(root)} else None
    print(f"{t.id}: " + ", ".join(f"{k}={v}" for k, v in fields.items()))


def cmd_validate(root, args):
    need_pm(root)
    problems = pm_lib.validate(root)
    if problems:
        print("\n".join(problems))
        sys.exit(1)
    print("ok")


def cmd_next_id(root, args):
    need_pm(root)
    print(pm_lib.next_id(root, args.kind))


def cmd_config(root, args):
    cfg = pm_lib.read_config(root)
    if args.json:
        print(json.dumps(cfg))
    else:
        print("\n".join(f"{k}: {v}" for k, v in cfg.items()))


def cmd_new(root, args):
    need_pm(root)
    if args.kind == "ticket":
        epics = {e.id: e for e in pm_lib.load_epics(root)}
        if args.epic not in epics:
            fail(f"unknown epic {args.epic}")
        tid = pm_lib.next_id(root, "ticket")
        deps = [d.strip() for d in (args.depends or "").split(",") if d.strip()]
        known = {t.id for t in pm_lib.load_tickets(root)}
        for d in deps:
            if d not in known:
                fail(f"depends on unknown ticket {d}")
        text = fill((TEMPLATES / "ticket.md").read_text(),
                    id=tid, title=args.title, epic=args.epic,
                    milestone=args.milestone or epics[args.epic].milestone,
                    priority=args.priority, depends_on=", ".join(deps),
                    auto="yes" if args.auto else "no", plan=args.plan, ready="yes" if args.ready else "no",
                    what=args.what or "(fill in)", why=args.why or "(fill in)",
                    acceptance=args.acceptance or "(one testable line per item)",
                    subtask="(first step)")
        path = pm_lib.ticket_path(root, tid, args.title)
        path.write_text(text)
        if args.confidence:
            pm_lib.set_fields(root, tid, confidence=args.confidence)
        pm_lib.update_epic(root, args.epic)
        print(f"created {path}")
    elif args.kind == "epic":
        milestones = [m.id for m in pm_lib.load_milestones(root)]
        if args.milestone not in milestones:
            fail(f"unknown milestone {args.milestone}; roadmap has {', '.join(milestones) or 'none'}")
        eid = pm_lib.next_id(root, "epic")
        text = fill((TEMPLATES / "epic.md").read_text(), id=eid, title=args.title,
                    milestone=args.milestone, goal=args.goal or "(fill in)")
        path = pm_lib.epic_path(root, eid, args.title)
        path.write_text(text)
        _add_epic_to_roadmap(root, args.milestone, eid)
        print(f"created {path}")
    elif args.kind == "milestone":
        mid = pm_lib.next_id(root, "milestone")
        roadmap = pm_lib.pm_dir(root) / "roadmap.md"
        block = f"## {mid}: {args.title}\nGoal: {args.goal or '(fill in)'}\nEpics: (none yet)\n\n"
        text = roadmap.read_text()
        idx = text.find("## Backlog")
        text = (text[:idx] + block + text[idx:]) if idx != -1 else text.rstrip() + "\n\n" + block
        roadmap.write_text(text)
        print(f"added {mid}: {args.title} to {roadmap}")


def _add_epic_to_roadmap(root: Path, milestone_id: str, epic_id: str):
    roadmap = pm_lib.pm_dir(root) / "roadmap.md"
    lines = roadmap.read_text().splitlines()
    in_block = False
    for i, line in enumerate(lines):
        if line.startswith(f"## {milestone_id}"):
            in_block = True
            continue
        if in_block and line.startswith("## "):
            lines.insert(i, f"Epics: {epic_id}")
            break
        if in_block and line.startswith("Epics:"):
            current = [e.strip() for e in line[len("Epics:"):].split(",") if e.strip() and not e.strip().startswith("(")]
            ids = [re.match(r"[EM]\d+", e).group(0) if re.match(r"[EM]\d+", e) else e for e in current]
            if epic_id not in ids:
                current.append(epic_id)
            lines[i] = "Epics: " + ", ".join(current)
            break
    else:
        if in_block:
            lines.append(f"Epics: {epic_id}")
    roadmap.write_text("\n".join(lines) + "\n")


def cmd_sync(root, args):
    need_pm(root)
    import pm_sync  # noqa: WPS433
    cfg = pm_lib.read_config(root)
    if cfg.get("mirror", "off") != "on" and not args.dry_run:
        fail("mirror is off in the pm block; set `mirror: on` or use --dry-run")
    if cfg.get("host") != "github":
        fail(f"host is '{cfg.get('host')}'; only github has an adapter for now")
    from adapters.github import GithubAdapter
    log = pm_sync.sync(root, GithubAdapter(), dry_run=args.dry_run)
    print("\n".join(log) or "nothing to do")


# ---------------------------------------------------------------- parser

def build_parser():
    p = argparse.ArgumentParser(prog="pm.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", help="repo root (default: git top level of the current folder)")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("board").set_defaults(func=cmd_board)
    sub.add_parser("line").set_defaults(func=cmd_line)

    s = sub.add_parser("next")
    s.add_argument("--routine", action="store_true", help="only tickets a routine may take")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_next)

    s = sub.add_parser("flow")
    s.add_argument("epic", nargs="?")
    s.add_argument("--all", action="store_true")
    s.set_defaults(func=cmd_flow)

    s = sub.add_parser("claim")
    s.add_argument("ticket")
    s.add_argument("owner")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_claim)

    s = sub.add_parser("release")
    s.add_argument("ticket")
    s.set_defaults(func=cmd_release)

    s = sub.add_parser("freeze", help="bug fix in progress: test files may not be edited until unfreeze")
    s.add_argument("ticket")
    s.set_defaults(func=cmd_freeze)

    s = sub.add_parser("unfreeze", help="allow test edits again; the reason goes under Notes")
    s.add_argument("ticket")
    s.add_argument("--reason", required=True)
    s.set_defaults(func=cmd_unfreeze)

    s = sub.add_parser("dismiss", help="close a ticket without doing it; the reason goes under Notes")
    s.add_argument("ticket")
    s.add_argument("--reason", required=True)
    s.set_defaults(func=cmd_dismiss)

    s = sub.add_parser("set")
    s.add_argument("ticket")
    s.add_argument("pairs", nargs="+")
    s.set_defaults(func=cmd_set)

    s = sub.add_parser("ready", help="mark a grilled ticket ready for /pm:work")
    s.add_argument("ticket")
    s.add_argument("--early", action="store_true", help="the ticket is blocked and the user said to grill it anyway")
    s.set_defaults(func=cmd_ready)

    sub.add_parser("validate").set_defaults(func=cmd_validate)
    sub.add_parser("backup", help="forks only: copy docs/pm and CONTEXT.md to $PM_BACKUP_DIR or ~/.pm-backup").set_defaults(func=cmd_backup)

    s = sub.add_parser("next-id")
    s.add_argument("kind", choices=["ticket", "epic", "milestone"])
    s.set_defaults(func=cmd_next_id)

    s = sub.add_parser("config")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_config)

    s = sub.add_parser("new")
    s.add_argument("kind", choices=["ticket", "epic", "milestone"])
    s.add_argument("--title", required=True)
    s.add_argument("--epic")
    s.add_argument("--milestone")
    s.add_argument("--priority", default="P2", choices=pm_lib.PRIORITIES)
    s.add_argument("--depends", help="comma-separated ticket ids")
    s.add_argument("--auto", action="store_true", help="a routine may take this ticket")
    s.add_argument("--plan", default="none", choices=["none", "required"])
    s.add_argument("--ready", action="store_true", help="already grilled: What, Why and a testable Acceptance line are settled")
    s.add_argument("--confidence", choices=pm_lib.CONFIDENCE, help="audit findings: how sure the finding is")
    s.add_argument("--goal")
    s.add_argument("--what")
    s.add_argument("--why")
    s.add_argument("--acceptance")
    s.set_defaults(func=cmd_new)

    s = sub.add_parser("sync")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_sync)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve() if args.root else pm_lib.find_root()
    if args.command == "new" and args.kind == "ticket" and not args.epic:
        fail("--epic is required for a ticket", 2)
    if args.command == "new" and args.kind == "epic" and not args.milestone:
        fail("--milestone is required for an epic", 2)
    args.func(root, args)


if __name__ == "__main__":
    main()
