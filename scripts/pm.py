#!/usr/bin/env python3
"""Small markdown-backed project board used by the /pm Claude Code skills."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - exercised on Windows
    fcntl = None
    import msvcrt


def root_dir() -> Path:
    try:
        return Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path.cwd()


def pm_dir(root: Path) -> Path:
    return root / "docs" / "pm"


def item_dir(root: Path) -> Path:
    return pm_dir(root) / "items"


def read_items(root: Path) -> list[dict]:
    items = []
    if not item_dir(root).exists():
        return items
    for path in sorted(item_dir(root).glob("PM-*.md")):
        raw = path.read_text(encoding="utf-8")
        match = re.match(r"\A---\n(.*?)\n---\n(.*)\Z", raw, re.S)
        if not match:
            continue
        meta = {}
        for line in match.group(1).splitlines():
            key, sep, value = line.partition(":")
            if sep:
                try:
                    meta[key.strip()] = json.loads(value.strip())
                except json.JSONDecodeError:
                    meta[key.strip()] = value.strip()
        title = re.search(r"^# (.+)$", match.group(2), re.M)
        if title:
            body = match.group(2)
            section = "## Requester intent\n"
            start = body.find(section)
            if start >= 0 and isinstance(meta.get("intent_length"), int):
                intent_start = start + len(section)
                intent_length = meta["intent_length"]
                intent_text = body[intent_start:intent_start + intent_length]
                notes_header = body.find("## Current notes\n", intent_start + intent_length)
                notes_text = body[notes_header + len("## Current notes\n"):] if notes_header >= 0 else ""
            else:
                intent = re.search(r"^## Requester intent\n(.*?)(?=^## Current notes\n|\Z)", body, re.M | re.S)
                notes = re.search(r"^## Current notes\n(.*)\Z", body, re.M | re.S)
                intent_text = intent.group(1).rstrip("\n") if intent else ""
                notes_text = notes.group(1) if notes else ""
            meta.update(path=path, body=body, title=title.group(1),
                        intent=intent_text, notes=notes_text.rstrip("\n"))
            items.append(meta)
    return items


def item_text(item: dict) -> str:
    keys = ("id", "status", "owner", "depends_on", "hold", "hold_until", "github_issue", "done_order", "intent_length")
    lines = ["---"]
    lines.extend(f"{key}: {json.dumps(item.get(key, [] if key == 'depends_on' else 0 if key == 'intent_length' else ''), ensure_ascii=False)}" for key in keys)
    lines.extend(("---", f"# {item['title']}", "", "## Requester intent", item["intent"], "", "## Current notes", item.get("notes", ""), ""))
    return "\n".join(lines)


def save_item(item: dict) -> None:
    path = item["path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(item_text(item), encoding="utf-8")


def mirror_setting(root: Path) -> str:
    board = pm_dir(root) / "BOARD.md"
    if not board.exists():
        return "off"
    match = re.search(r"^<!-- pm-mirror: (off|github) -->$", board.read_text(), re.M)
    return match.group(1) if match else "off"


def render_board(root: Path, items: list[dict]) -> str:
    lines = ["# Project board", "", f"<!-- pm-mirror: {mirror_setting(root)} -->", "",
             "Short status index. Full item context lives in `items/`; older completed summaries are in `archive.md`.", ""]
    groups = (("In flight", "in-flight"), ("Queued", "queued"), ("Waiting", "waiting"), ("Done", "done"))
    by_id = {i["id"]: i for i in items}
    for heading, status in groups:
        lines.extend((f"## {heading}", ""))
        selected = [i for i in items if i.get("status", "queued") == status]
        if status == "queued":
            selected = [i for i in selected if not i.get("hold")]
        if status == "done":
            selected = sorted(selected, key=lambda item: int(item.get("done_order", 0)))[-10:]
        if not selected:
            lines.extend(("- None.", ""))
            continue
        for item in selected:
            notes = []
            current_note = " ".join((item.get("notes") or item.get("intent", "")).split())
            if current_note:
                notes.append(current_note[:119] + ("…" if len(current_note) > 120 else ""))
            if item.get("owner"):
                notes.append(f"claimed by {item['owner']}")
            waiting = [dep for dep in item.get("depends_on", []) if dep in by_id and by_id[dep].get("status") != "done"]
            if waiting:
                notes.append("blocked by " + ", ".join(waiting))
            if item.get("hold"):
                notes.append("held: " + item["hold"])
                if item.get("hold_until"):
                    notes[-1] += f" (review after {item['hold_until']})"
            suffix = f" — {'; '.join(notes)}" if notes else ""
            lines.append(f"- [{item['id']}]({item['path'].relative_to(pm_dir(root))}) {item['title']}{suffix}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def archive_old_done(root: Path, items: list[dict]) -> None:
    done = sorted((i for i in items if i.get("status") == "done"), key=lambda item: int(item.get("done_order", 0)))
    older = done[:-10]
    if not older:
        return
    archive = pm_dir(root) / "archive.md"
    existing = archive.read_text(encoding="utf-8") if archive.exists() else "# Completed item archive\n\n"
    known = set(re.findall(r"\[(PM-\d+)\]", existing))
    added = [f"- [{i['id']}]({i['path'].relative_to(pm_dir(root))}) {i['title']} — "
             f"{' '.join((i.get('notes') or i.get('intent', '')).split())[:100]}"
             for i in older if i["id"] not in known]
    if added:
        archive.write_text(existing.rstrip() + "\n" + "\n".join(added) + "\n", encoding="utf-8")


def refresh(root: Path) -> list[dict]:
    items = read_items(root)
    archive_old_done(root, items)
    (pm_dir(root) / "BOARD.md").write_text(render_board(root, items), encoding="utf-8")
    return items


@contextmanager
def write_lock(root: Path):
    try:
        git_common = subprocess.check_output(["git", "rev-parse", "--git-common-dir"], cwd=root, text=True, stderr=subprocess.DEVNULL).strip()
        lock_dir = Path(git_common)
        if not lock_dir.is_absolute():
            lock_dir = root / lock_dir
    except (subprocess.CalledProcessError, FileNotFoundError):
        digest = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:20]
        lock_dir = Path(tempfile.gettempdir()) / "pm-plugin-locks"
        lock_dir = lock_dir / digest
    lock_dir.mkdir(parents=True, exist_ok=True)
    with (lock_dir / "board.lock").open("a+") as lock:
        if fcntl:
            fcntl.flock(lock, fcntl.LOCK_EX)
        else:
            lock.seek(0, 2)
            if lock.tell() == 0:
                lock.write("\0")
                lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        try:
            yield
        finally:
            if fcntl:
                fcntl.flock(lock, fcntl.LOCK_UN)
            else:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def find_item(items: list[dict], item_id: str) -> dict:
    found = next((i for i in items if i["id"].upper() == item_id.upper()), None)
    if not found:
        raise ValueError(f"Unknown item {item_id}; run /pm:status to see the board.")
    return found


def ready(item: dict, by_id: dict[str, dict]) -> tuple[bool, str]:
    if item.get("status") != "queued":
        return False, f"status is {item.get('status')}"
    if item.get("hold"):
        return False, f"held: {item['hold']}"
    blocked = [dep for dep in item.get("depends_on", []) if dep not in by_id or by_id[dep].get("status") != "done"]
    if blocked:
        return False, "blocked by " + ", ".join(blocked)
    return True, "ready"


def next_items(items: list[dict]) -> list[dict]:
    by_id = {i["id"]: i for i in items}
    return [i for i in items if ready(i, by_id)[0]]


def cmd_init(root: Path, args) -> None:
    with write_lock(root):
        folder = item_dir(root)
        folder.mkdir(parents=True, exist_ok=True)
        board = pm_dir(root) / "BOARD.md"
        if board.exists():
            raise ValueError(f"{board.relative_to(root)} already exists.")
        board.write_text("# Project board\n\n<!-- pm-mirror: off -->\n", encoding="utf-8")
        (pm_dir(root) / "archive.md").write_text("# Completed item archive\n", encoding="utf-8")
        refresh(root)
    print(f"Initialized {pm_dir(root).relative_to(root)}. Add the first item with /pm:plan.")


def cmd_add(root: Path, args) -> None:
    with write_lock(root):
        if not (pm_dir(root) / "BOARD.md").exists():
            raise ValueError("No project board. Run /pm:init first.")
        items = read_items(root)
        number = max((int(re.search(r"\d+$", i["id"]).group()) for i in items), default=0) + 1
        item_id = f"PM-{number:03}"
        slug = re.sub(r"[^a-z0-9]+", "-", args.title.lower()).strip("-")[:50] or "item"
        intent = sys.stdin.read() if args.intent_stdin else args.intent
        item = {"id": item_id, "title": args.title.strip(), "status": "queued", "owner": "",
                "depends_on": [], "hold": "", "hold_until": "", "github_issue": "",
                "intent": intent, "intent_length": len(intent), "notes": "", "done_order": 0,
                "path": item_dir(root) / f"{item_id}-{slug}.md"}
        item["path"].parent.mkdir(parents=True, exist_ok=True)
        save_item(item)
        refresh(root)
    print(f"Created {item_id}: {args.title}\nDetail: {item['path'].relative_to(root)}")


def cmd_board(root: Path, args) -> None:
    if not (pm_dir(root) / "BOARD.md").exists():
        print("No project board. Run /pm:init to create one.")
        return
    print((pm_dir(root) / "BOARD.md").read_text(encoding="utf-8"), end="")
    items = read_items(root)
    print("\nReady next: " + (", ".join(f"{i['id']} {i['title']}" for i in next_items(items)) or "none"))


def cmd_next(root: Path, args) -> None:
    items = next_items(read_items(root))
    for i in items:
        print(f"{i['id']} {i['title']} — {i['path'].relative_to(root)}")
    if not items:
        print("No queued items are ready. Check dependencies or decisions in Waiting.")


def cmd_claim(root: Path, args) -> None:
    with write_lock(root):
        items = read_items(root)
        item = find_item(items, args.id)
        if item.get("owner"):
            if item.get("status") == "in-flight" and item["owner"].casefold() == args.person.casefold():
                print(f"{item['id']} is already in flight for {args.person}; resuming the existing claim.")
                return
            raise ValueError(f"{item['id']} is already claimed by {item['owner']}.")
        can_start, reason = ready(item, {i["id"]: i for i in items})
        if not can_start:
            raise ValueError(f"Cannot claim {item['id']}: {reason}.")
        item.update(status="in-flight", owner=args.person, hold="", hold_until="")
        save_item(item)
        refresh(root)
    print(f"Claimed {item['id']} for {args.person}. Claim is saved before work starts.")


def cmd_finish(root: Path, args) -> None:
    with write_lock(root):
        item = find_item(read_items(root), args.id)
        if item.get("status") != "in-flight":
            raise ValueError(f"{item['id']} is not in flight.")
        next_order = max((int(i.get("done_order", 0)) for i in read_items(root)), default=0) + 1
        item.update(status="done", owner="", notes=args.note or item.get("notes", ""), done_order=next_order)
        save_item(item)
        refresh(root)
    print(f"Finished {item['id']}; board refreshed.")


def cmd_hold(root: Path, args) -> None:
    with write_lock(root):
        item = find_item(read_items(root), args.id)
        if item.get("status") == "done":
            raise ValueError(f"{item['id']} is already done and cannot be held.")
        item.update(status="waiting", owner="", hold=args.reason, hold_until=args.until or "")
        save_item(item)
        refresh(root)
    print(f"Parked {item['id']}: {args.reason}")


def cmd_resume(root: Path, args) -> None:
    with write_lock(root):
        item = find_item(read_items(root), args.id)
        if item.get("status") != "waiting":
            raise ValueError(f"{item['id']} is not waiting on a decision.")
        item.update(status="queued", hold="", hold_until="")
        save_item(item)
        refresh(root)
    print(f"Returned {item['id']} to Queued.")


def cmd_set(root: Path, args) -> None:
    with write_lock(root):
        items = read_items(root)
        item = find_item(items, args.id)
        if args.depends is not None:
            deps = [v.strip().upper() for v in args.depends.split(",") if v.strip()]
            known = {i["id"] for i in items}
            missing = [d for d in deps if d not in known]
            if missing:
                raise ValueError("Unknown dependencies: " + ", ".join(missing))
            if item["id"] in deps:
                raise ValueError("An item cannot depend on itself.")
            graph = {i["id"]: set(i.get("depends_on", [])) for i in items}
            graph[item["id"]] = set(deps)
            def reaches(start: str, target: str, seen: set[str]) -> bool:
                if start == target:
                    return True
                if start in seen:
                    return False
                seen.add(start)
                return any(reaches(child, target, seen) for child in graph.get(start, set()))
            if any(reaches(dependency, item["id"], set()) for dependency in deps):
                raise ValueError("These dependencies create a cycle.")
            item["depends_on"] = deps
        if args.note is not None:
            item["notes"] = args.note
        save_item(item)
        refresh(root)
    print(f"Updated {item['id']}.")


def cmd_mirror(root: Path, args) -> None:
    if args.mode == "show":
        print(f"GitHub Issues mirror: {mirror_setting(root)}")
        return
    if args.mode not in ("off", "github"):
        raise ValueError("Mirror mode must be off or github.")
    with write_lock(root):
        current = (pm_dir(root) / "BOARD.md").read_text(encoding="utf-8")
        current = re.sub(r"^<!-- pm-mirror: (off|github) -->$", f"<!-- pm-mirror: {args.mode} -->", current, count=1, flags=re.M)
        (pm_dir(root) / "BOARD.md").write_text(current, encoding="utf-8")
        refresh(root)
    if args.mode == "github":
        print("GitHub Issues mirror enabled: syncing publishes item requester intent and current notes to this repository's GitHub Issues audience.")
    else:
        print("GitHub Issues mirror: off")


def cmd_sync(root: Path, args) -> None:
    if mirror_setting(root) != "github":
        raise ValueError("GitHub Issues mirror is off. Enable it with `pm.py mirror github` first.")
    with write_lock(root):
        items = read_items(root)
        for item in items:
            body = f"Requester intent (verbatim):\n\n{item['intent']}\n\nCurrent notes:\n\n{item.get('notes', '')}\n\nLocal status: {item.get('status')}"
            if item.get("github_issue"):
                number = str(item["github_issue"])
                command = ["gh", "issue", "edit", number, "--title", item["title"], "--body", body]
            else:
                number = ""
                command = ["gh", "issue", "create", "--title", item["title"], "--body", body]
            result = subprocess.run(command, cwd=root, text=True, capture_output=True)
            if result.returncode:
                raise ValueError(result.stderr.strip() or "gh issue sync failed")
            issue_url = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
            number_match = re.search(r"/(\d+)$", issue_url)
            if number_match and not number:
                number = number_match.group(1)
                item["github_issue"] = number
                save_item(item)
            if number:
                details = subprocess.run(["gh", "issue", "view", number, "--json", "url,state"], cwd=root, text=True, capture_output=True)
                if details.returncode:
                    raise ValueError(details.stderr.strip() or f"could not read GitHub issue {number}")
                issue = json.loads(details.stdout)
                issue_url = issue["url"]
                desired_state = "closed" if item.get("status") == "done" else "open"
                if issue["state"].lower() != desired_state:
                    verb = "close" if desired_state == "closed" else "reopen"
                    changed = subprocess.run(["gh", "issue", verb, number], cwd=root, text=True, capture_output=True)
                    if changed.returncode:
                        raise ValueError(changed.stderr.strip() or f"could not {verb} GitHub issue {number}")
            print(f"{item['id']} -> {issue_url}")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Manage the docs/pm markdown board.")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="create an empty board")
    sub.add_parser("board", help="show status at a glance")
    sub.add_parser("next", help="list queued items whose dependencies are done")
    add = sub.add_parser("add", help="create an item with the requester's exact words")
    add.add_argument("title")
    intent = add.add_mutually_exclusive_group(required=True)
    intent.add_argument("--intent", help="requester words supplied as one already-safe argv value")
    intent.add_argument("--intent-stdin", action="store_true", help="read exact requester words from stdin")
    claim = sub.add_parser("claim", help="atomically claim an item before work")
    claim.add_argument("id"); claim.add_argument("person")
    for command, help_text in (("finish", "mark an in-flight item done"), ("resume", "return a held item to queue")):
        item = sub.add_parser(command, help=help_text); item.add_argument("id")
        if command == "finish": item.add_argument("--note", default="")
    hold = sub.add_parser("hold", help="park an item for a decision")
    hold.add_argument("id"); hold.add_argument("reason"); hold.add_argument("--until", default="")
    update = sub.add_parser("set", help="set dependencies or replace current notes")
    update.add_argument("id"); update.add_argument("--depends"); update.add_argument("--note")
    mirror = sub.add_parser("mirror", help="configure the optional GitHub Issues mirror")
    mirror.add_argument("mode", choices=("show", "off", "github"))
    sub.add_parser("sync", help="sync items to GitHub Issues when enabled")
    return p


def main() -> int:
    args = parser().parse_args()
    root = root_dir()
    try:
        {"init": cmd_init, "board": cmd_board, "next": cmd_next, "add": cmd_add,
         "claim": cmd_claim, "finish": cmd_finish, "hold": cmd_hold, "resume": cmd_resume,
         "set": cmd_set, "mirror": cmd_mirror, "sync": cmd_sync}[args.command](root, args)
    except (ValueError, OSError) as exc:
        print(f"pm: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
