#!/usr/bin/env python3
"""Small markdown-backed project board used by the /pm Claude Code skills."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import secrets
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

import pm_icm
import pm_migrate
import pm_workers

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


def config_path(root: Path) -> Path:
    return pm_dir(root) / "config.json"


def read_items(root: Path) -> list[dict]:
    items = []
    if not item_dir(root).exists():
        return items
    for path in sorted(item_dir(root).glob("*.md")):
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
    keys = ("id", "status", "owner", "depends_on", "hold", "hold_until", "done_at", "intent_length", "github_issue")
    lines = ["---"]
    lines.extend(f"{key}: {json.dumps(item.get(key, [] if key == 'depends_on' else 0 if key == 'intent_length' else ''), ensure_ascii=False)}" for key in keys)
    # Later list fields are written only when set, so older item files stay unchanged and merge cleanly.
    lines.extend(f"{key}: {json.dumps(item[key], ensure_ascii=False)}" for key in ("touches", "corrections") if item.get(key))
    lines.extend(("---", f"# {item['title']}", "", "## Requester intent", item["intent"], "", "## Current notes", item.get("notes", ""), ""))
    return "\n".join(lines)


def save_item(item: dict) -> None:
    path = item["path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(item_text(item), encoding="utf-8")


def read_literal_stdin() -> str:
    value = sys.stdin.read()
    return value[:-1] if value.endswith("\n") else value


def mirror_setting(root: Path) -> str:
    if not config_path(root).exists():
        return "off"
    return json.loads(config_path(root).read_text(encoding="utf-8")).get("mirror", "off")


def render_board(root: Path, items: list[dict]) -> str:
    lines = ["# Project board", "", "Rendered from `docs/pm/items/`, which holds each item's requester intent and current notes.", ""]
    groups = (("In flight", "in-flight"), ("Queued", "queued"), ("Waiting", "waiting"), ("Done", "done"))
    by_id = {i["id"]: i for i in items}
    for heading, status in groups:
        lines.extend((f"## {heading}", ""))
        selected = [i for i in items if i.get("status", "queued") == status]
        if status == "queued":
            selected = [i for i in selected if not i.get("hold")]
        older = 0
        if status == "done":
            selected = sorted(selected, key=lambda item: str(item.get("done_at", "")))
            older = max(len(selected) - 10, 0)
            selected = selected[older:]
        if not selected:
            lines.extend(("- None.", ""))
            continue
        for item in selected:
            notes = []
            current_note = " ".join((item.get("notes") or item.get("intent", "")).split())
            if current_note:
                notes.append(current_note if len(current_note) <= 120 else current_note[:119] + "…")
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
            lines.append(f"- [{item['id']}]({item['path'].relative_to(root).as_posix()}) {item['title']}{suffix}")
        if older:
            lines.append(f"- {older} older done item{'s' if older > 1 else ''} kept in `docs/pm/items/`.")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


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


def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(["git", "-C", str(root), *args], text=True, capture_output=True)
    if check and result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ValueError(detail or f"git {' '.join(args)} failed")
    return result


def remote_default(root: Path) -> tuple[str, str] | None:
    listed = git(root, "remote", check=False)  # fails outside a Git repository, which has no remote either
    remotes = listed.stdout.splitlines() if listed.returncode == 0 else []
    if not remotes:
        return None
    remote = "origin" if "origin" in remotes else sorted(remotes)[0]
    result = git(root, "ls-remote", "--symref", remote, "HEAD")
    match = re.search(r"^ref: refs/heads/(.+)\tHEAD$", result.stdout, re.M)
    if not match:
        raise ValueError(f"Remote {remote} does not advertise a default branch; cannot coordinate claims safely.")
    return remote, match.group(1)


def fetch_default(root: Path, remote: str, branch: str) -> str:
    tracking_ref = f"refs/remotes/{remote}/{branch}"
    git(root, "fetch", "--no-tags", remote, f"+refs/heads/{branch}:{tracking_ref}")
    return git(root, "rev-parse", tracking_ref).stdout.strip()


def sync_default_checkout(root: Path, tracking_ref: str) -> None:
    merged = git(root, "merge", "--ff-only", tracking_ref, check=False)
    if merged.returncode:
        raise ValueError("Local default branch cannot fast-forward to the shared board. Sync it first.")
    head = git(root, "rev-parse", "HEAD").stdout.strip()
    remote_head = git(root, "rev-parse", tracking_ref).stdout.strip()
    if head != remote_head:
        raise ValueError("Local default branch has unpublished commits. Sync it first.")


def board_checkout(root: Path) -> Path:
    """Without a remote, the board lives in the clone's main checkout, so every worktree of it (a worker's) shares it."""
    listed = git(root, "remote", check=False)
    if listed.returncode or listed.stdout.strip():
        return root
    worktrees = git(root, "worktree", "list", "--porcelain", check=False)
    first = worktrees.stdout.split("\n\n", 1)[0].splitlines() if worktrees.returncode == 0 else []
    if not first or not first[0].startswith("worktree ") or "bare" in first:
        return root
    main = Path(first[0][len("worktree "):])
    return root if main.resolve() == root.resolve() else main


def publish(root: Path, change) -> str:
    remote = remote_default(root)
    if not remote:
        paths, text = change(root)
        if paths and git(root, "rev-parse", "--is-inside-work-tree", check=False).returncode == 0:
            relative = [path.relative_to(root).as_posix() for path in paths]
            git(root, "add", "--", *relative)
            git(root, "commit", "--only", "-m", f"pm: {text.splitlines()[0]}", "--", *relative)
        return text
    name, branch = remote
    tracking_ref = f"refs/remotes/{name}/{branch}"
    last_error = ""
    for _ in range(3):
        base = fetch_default(root, name, branch)
        current = git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        if current == branch:
            sync_default_checkout(root, tracking_ref)
        with tempfile.TemporaryDirectory(prefix="pm-publish-") as temp:
            checkout = Path(temp) / "checkout"
            git(root, "worktree", "add", "--quiet", "--detach", str(checkout), base)
            try:
                paths, text = change(checkout)
                if not paths:
                    return text
                git(checkout, "add", "--", *(path.relative_to(checkout).as_posix() for path in paths))
                git(checkout, "commit", "-m", f"pm: {text.splitlines()[0]}")
                pushed = git(checkout, "push", "--porcelain", name, f"HEAD:refs/heads/{branch}", check=False)
                if pushed.returncode:
                    last_error = pushed.stderr.strip() or pushed.stdout.strip() or "push rejected"
                    continue
            finally:
                git(root, "worktree", "remove", "--force", str(checkout), check=False)
        fetch_default(root, name, branch)
        if current == branch:
            sync_default_checkout(root, tracking_ref)
            return f"{text}\nPublished to shared {name}/{branch}."
        return f"{text}\nPublished to shared {name}/{branch}; branch {current} shows it only after syncing with {name}/{branch}."
    raise ValueError(f"Could not publish to {name}/{branch} after three attempts: {last_error}")


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


def repo_paths(root: Path, value: str) -> list[str]:
    """Comma-separated repo-relative paths that must exist in the current checkout."""
    paths = []
    for raw in (part.strip() for part in value.split(",")):
        if not raw:
            continue
        path = PurePosixPath(raw.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"{raw} must be a path inside this repository, relative to its root.")
        name = path.as_posix().rstrip("/")
        if not (root / name).exists():
            raise ValueError(f"{name} does not exist in this checkout.")
        if name not in paths:
            paths.append(name)
    return paths


CORRECTION_REPEATS = 3


def correction_counts(items: list[dict]) -> dict[tuple[str, str], int]:
    """Corrections of each kind at each place since the source was last fixed for it."""
    events = [entry for item in items for entry in item.get("corrections", []) if isinstance(entry, dict)]
    counts: dict[tuple[str, str], int] = {}
    for entry in sorted(events, key=lambda entry: str(entry.get("at", ""))):
        key = (entry.get("where", ""), entry.get("kind", ""))
        counts[key] = 0 if entry.get("fixed") else counts.get(key, 0) + 1
    return counts


def require_board(root: Path) -> None:
    if not config_path(root).exists():
        raise ValueError("No project board. Run /pm:init first.")


def cmd_init(root: Path, args) -> None:
    def change(board: Path):
        config = config_path(board)
        if config.exists():
            raise ValueError(f"{config.relative_to(board).as_posix()} already exists.")
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(json.dumps({"mirror": "off"}) + "\n", encoding="utf-8")
        return [config], "Initialized docs/pm. Add the first item with /pm:plan."
    with write_lock(root):
        print(publish(root, change))


def item_slug(title: str) -> str:
    """The title slug used inside the item ID; the item's file is named after the ID alone."""
    return pm_migrate.slugify(title)[:32].rstrip("-") or "item"


def cmd_add(root: Path, args) -> None:
    title, _, intent = read_literal_stdin().partition("\n")
    title = title.strip()
    if not title:
        raise ValueError("The first stdin line must be the item title.")
    if not intent.strip():
        intent = title + "\n"  # a one-line request is its own verbatim intent, so a worker and validator have criteria
    id_slug = item_slug(title)
    touches = repo_paths(root, args.touches or "")

    def change(board: Path):
        require_board(board)
        existing_ids = {item["id"].casefold() for item in read_items(board)}
        while True:
            item_id = f"{id_slug}-{secrets.token_hex(3)}"
            if item_id.casefold() not in existing_ids:
                break
        item = {"id": item_id, "title": title, "status": "queued", "owner": "",
                "depends_on": [], "hold": "", "hold_until": "", "github_issue": "",
                "intent": intent, "intent_length": len(intent), "notes": "", "done_at": "", "touches": touches,
                "path": item_dir(board) / f"{item_id}.md"}
        save_item(item)
        return [item["path"]], f"Created {item_id}: {title}\nDetail: {item['path'].relative_to(board).as_posix()}"
    with write_lock(root):
        print(publish(root, change))


def cmd_board(root: Path, args) -> None:
    if not config_path(root).exists():
        print("No project board. Run /pm:init to create one.")
        return
    items = read_items(root)
    print(render_board(root, items), end="")
    print("\nReady next: " + (", ".join(f"{i['id']} {i['title']}" for i in next_items(items)) or "none"))
    for (where, kind), count in sorted(correction_counts(items).items()):
        if count >= CORRECTION_REPEATS:
            print(f"Fix the source: {kind} was corrected {count} times on {where or 'the whole project'}. "
                  "Change the source so it stops, then record it with pm.py correct --fixed.")


def cmd_next(root: Path, args) -> None:
    items = next_items(read_items(root))
    for i in items:
        print(f"{i['id']} {i['title']} — {i['path'].relative_to(root)}")
    if not items:
        print("No queued items are ready. Check dependencies or decisions in Waiting.")


def cmd_claim(root: Path, args) -> None:
    person = read_literal_stdin().strip()
    if not person:
        raise ValueError("A person's name is required on stdin.")

    def change(board: Path):
        items = read_items(board)
        item = find_item(items, args.id)
        if item.get("owner") and item["owner"].casefold() != person.casefold():
            raise ValueError(f"{item['id']} is already claimed by {item['owner']}.")
        if item.get("owner") and item.get("status") == "in-flight":
            if not args.resume:
                raise ValueError(f"{item['id']} is already in flight for {item['owner']}, so another worker may be on it. "
                                 "Only to continue that same claim, run claim again with --resume.")
            return [], f"{item['id']} is already in flight for {person}; resuming the existing claim."
        can_start, reason = ready(item, {i["id"]: i for i in items})
        if not can_start:
            raise ValueError(f"Cannot claim {item['id']}: {reason}.")
        item.update(status="in-flight", owner=person, hold="", hold_until="")
        save_item(item)
        return [item["path"]], f"Claimed {item['id']} for {person}. Claim is saved before work starts."
    with write_lock(root):
        print(publish(root, change))


def uncommitted_work(root: Path, item_path: Path) -> list[str]:
    """Changed or new files other than the item being finished and config.json, which the CLI writes."""
    item = item_path.relative_to(root).as_posix()
    return [path for _, path in pm_icm.git_status(root)
            if path not in {item, "docs/pm/config.json"}]


def cmd_validated(root: Path, args) -> None:
    summary = " ".join(read_literal_stdin().split())
    if not summary:
        raise ValueError("A validator summary is required on stdin.")
    with write_lock(root):
        item = find_item(read_items(root), args.id)
        if item.get("status") != "in-flight":
            raise ValueError(f"{item['id']} is not in flight.")
        dirty = [path for _, path in pm_icm.git_status(root) if not path.startswith("docs/pm/")]
        if dirty:
            shown = ", ".join(dirty[:10]) + (f", and {len(dirty) - 10} more" if len(dirty) > 10 else "")
            raise ValueError(f"Cannot record validation while non-board files are uncommitted ({shown}). Commit the work first.")
        head = git(root, "rev-parse", "HEAD").stdout.strip()
        validation = f"Validation: {args.verdict} at {head}: {summary}"
        notes = [line for line in item.get("notes", "").splitlines() if not line.startswith("Validation:")]
        item["notes"] = "\n".join(notes + [validation]).strip()
        save_item(item)
        path = item["path"].relative_to(root).as_posix()
        git(root, "add", "--", path)
        git(root, "commit", "--only", "-m", f"pm: validation {item['id']}", "--", path)
    print(f"Recorded {args.verdict} validation for {item['id']} at {head}.")


def cmd_finish(root: Path, args) -> None:
    note = read_literal_stdin()
    with write_lock(root):
        item = find_item(read_items(root), args.id)
        if item.get("status") != "in-flight":
            raise ValueError(f"{item['id']} is not in flight.")
        verdict = re.search(r"^Validation: (pass|findings) at ([0-9a-f]{40}|[0-9a-f]{64}): .+$", item.get("notes", ""), re.M)
        if not verdict:
            raise ValueError(f"{item['id']} has no recorded validation. Run the pm:validator agent, then record its verdict with `pm.py validated {item['id']} --verdict pass|findings`.")
        if verdict.group(1) != "pass":
            raise ValueError(f"{item['id']} has validation findings. Fix them, commit, and validate again, or after 2 fix rounds hold it with `pm.py hold {item['id']}`.")
        stale = git(root, "diff", "--quiet", verdict.group(2), "HEAD", "--", ".", ":(exclude)docs/pm", check=False)
        if stale.returncode:
            raise ValueError(f"{item['id']} changed since validation at {verdict.group(2)[:7]}; validate again.")
        dirty = uncommitted_work(root, item["path"])
        if dirty:
            shown = ", ".join(dirty[:10]) + (f", and {len(dirty) - 10} more" if len(dirty) > 10 else "")
            raise ValueError(f"{item['id']} is not finished: {len(dirty)} file{'s' if len(dirty) != 1 else ''} "
                             f"uncommitted ({shown}). Commit the work on this branch first (or remove what does not "
                             "belong to it), then run finish again; the board says Done only for committed work.")
        validation_line = verdict.group(0)
        completion = note.strip() or "Work complete."
        item.update(status="done", owner="", notes=f"{completion}\n{validation_line}",
                    done_at=datetime.now(timezone.utc).isoformat(timespec="microseconds"))
        save_item(item)
        path = item["path"].relative_to(root).as_posix()
        is_git_repo = git(root, "rev-parse", "--is-inside-work-tree", check=False).returncode == 0
        if is_git_repo:
            git(root, "add", "--", path)
            git(root, "commit", "--only", "-m", f"pm: finish {item['id']}", "--", path)
    suffix = " and committed locally" if is_git_repo else ""
    print(f"Finished {item['id']}{suffix}.")


def cmd_hold(root: Path, args) -> None:
    reason = read_literal_stdin()
    if not reason.strip():
        raise ValueError("A decision question is required on stdin.")

    def change(board: Path):
        item = find_item(read_items(board), args.id)
        if item.get("status") == "done":
            raise ValueError(f"{item['id']} is already done and cannot be held.")
        item.update(status="waiting", hold=reason, hold_until=args.until)
        save_item(item)
        return [item["path"]], f"Parked {item['id']}: {reason}"
    with write_lock(root):
        print(publish(root, change))


def cmd_resume(root: Path, args) -> None:
    answer = read_literal_stdin() if args.answer else ""
    if args.answer and not answer.strip():
        raise ValueError("--answer needs the decider's words on stdin.")

    def change(board: Path):
        item = find_item(read_items(board), args.id)
        if item.get("status") != "waiting":
            raise ValueError(f"{item['id']} is not waiting on a decision.")
        status = "in-flight" if item.get("owner") else "queued"
        if answer:
            old = item.get("notes", "")
            item["notes"] = f'Decision on "{item["hold"]}": {answer}' + (f"\n\n{old}" if old else "")
        item.update(status=status, hold="", hold_until="")
        save_item(item)
        return [item["path"]], f"Returned {item['id']} to {'In flight' if item.get('owner') else 'Queued'}."
    with write_lock(root):
        print(publish(root, change))


def cmd_set(root: Path, args) -> None:
    if args.depends is None and args.touches is None:
        raise ValueError("Give --depends, --touches, or both.")
    touches = repo_paths(root, args.touches) if args.touches is not None else None

    def change(board: Path):
        items = read_items(board)
        item = find_item(items, args.id)
        if touches is not None:
            item["touches"] = touches
        if args.depends is None:
            save_item(item)
            return [item["path"]], f"Updated {item['id']} touches: {', '.join(touches) or 'none'}."
        requested = [value.strip() for value in args.depends.split(",") if value.strip()]
        known = {i["id"].casefold(): i["id"] for i in items}
        missing = [dependency for dependency in requested if dependency.casefold() not in known]
        if missing:
            raise ValueError("Unknown dependencies: " + ", ".join(missing))
        deps = [known[dependency.casefold()] for dependency in requested]
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
        save_item(item)
        return [item["path"]], f"Updated {item['id']} dependencies" + (" and touches." if touches is not None else ".")
    with write_lock(root):
        print(publish(root, change))


def cmd_correct(root: Path, args) -> None:
    note = read_literal_stdin().strip()
    if not note:
        raise ValueError("Describe the correction on stdin (with --fixed, the source change that fixes it).")
    kind = pm_migrate.slugify(args.kind)
    if not kind:
        raise ValueError("--kind needs a short name for this kind of correction, such as missing-tests.")
    where = (repo_paths(root, args.where) or [""])[0]
    label = f"`{where}`" if where else "the whole project"

    def change(board: Path):
        items = read_items(board)
        item = find_item(items, args.id)
        entry = {"at": datetime.now(timezone.utc).isoformat(timespec="microseconds"), "kind": kind, "where": where, "note": note}
        if args.fixed:
            entry["fixed"] = True
        item["corrections"] = [*item.get("corrections", []), entry]
        save_item(item)
        if args.fixed:
            return [item["path"]], f"Recorded the source fix for {kind} on {label}; its count starts again."
        counts = correction_counts(items)
        count = counts[(where, kind)]
        fixed_before = any(c.get("fixed") and (c.get("where"), c.get("kind")) == (where, kind)
                           for i in items for c in i.get("corrections", []) if isinstance(c, dict))
        lines = [f"Recorded correction {kind} on {label} for {item['id']}: {count} of this kind {'there' if where else 'in the project'}"
                 + (" since the source was last fixed for it." if fixed_before else " so far.")]
        if count >= CORRECTION_REPEATS:
            fixed = f"pm.py correct {item['id']} --kind {kind}" + (f" --where {where}" if where else "") + " --fixed"
            source = (f"{label} (or AGENTS.md if it applies to every session)" if where else
                      "the source behind it: AGENTS.md if it applies to every session, docs/placement.md if it is about "
                      "where knowledge goes, or the contract or reference file that produced it")
            lines.append(f"Same correction {count} times: fix the source, not the output. Propose a lasting change to {source}; "
                         f"once it is in, record it with {fixed} and the change on stdin.")
        else:
            others = [f"{other} ({n})" for (place, other), n in sorted(counts.items()) if place == where and other != kind and n]
            if others:
                lines.append("Other kinds recorded here: " + ", ".join(others) + ". Reuse a kind's name when it is the same correction.")
        return [item["path"]], "\n".join(lines)
    with write_lock(root):
        print(publish(root, change))


def cmd_walk(root: Path, args) -> None:
    results = pm_icm.walk(root, read_items(root))
    print(pm_icm.render_walk(results), flush=True)
    failed = sum(level == "FAIL" for level, _ in results)
    if failed:
        raise ValueError(f"walk test failed: {failed} thing{'s' if failed > 1 else ''} to fix.")


def cmd_places(root: Path, args) -> None:
    found = pm_icm.strays(root)
    if args.paths:
        if found:
            print("\n".join(found))
        return
    if found is None:
        raise ValueError(f"AGENTS.md has no `## {pm_icm.WHERE}` table; /pm:init stamps one from the project's shape.")
    if not found:
        print(f"Every new file is in a place AGENTS.md > {pm_icm.WHERE} names.")
        return
    print(f"New files outside the places in AGENTS.md > {pm_icm.WHERE}:")
    print("\n".join(f"- {path}" for path in found))
    print("Move each to the place for its kind (git mv, then update anything that reads or writes it), or, for a new "
          "kind of thing, ask the owner once and add a row.", flush=True)
    raise ValueError(f"{len(found)} new file{'s' if len(found) != 1 else ''} outside the places.")


def cmd_index(root: Path, args) -> None:
    print(pm_icm.write_index(root))


def cmd_refs(root: Path, args) -> None:
    pairs = []
    for raw in args.paths:
        old, _, new = raw.partition("=")
        pairs.append((old.strip().strip("/").removeprefix("./"), new.strip().strip("/").removeprefix("./")))
    report, collisions = pm_icm.refs(root, pairs)
    print(report, flush=True)
    if collisions:
        raise ValueError(f"{collisions} destination{'s are' if collisions > 1 else ' is'} already taken; pick another name first.")


def cmd_mirror(root: Path, args) -> None:
    if args.mode == "show":
        print(f"GitHub Issues mirror: {mirror_setting(root)}")
        return

    def change(board: Path):
        require_board(board)
        config = json.loads(config_path(board).read_text(encoding="utf-8"))
        config["mirror"] = args.mode
        config_path(board).write_text(json.dumps(config) + "\n", encoding="utf-8")
        if args.mode == "github":
            return [config_path(board)], ("GitHub Issues mirror enabled: syncing publishes item requester intent "
                                          "and current notes to this repository's GitHub Issues audience.")
        return [config_path(board)], "GitHub Issues mirror: off"
    with write_lock(root):
        print(publish(root, change))


def read_config(root: Path) -> dict:
    return json.loads(config_path(root).read_text(encoding="utf-8")) if config_path(root).exists() else {}


def cmd_defaults(root: Path, args) -> None:
    changes = {("workers", "model"): args.worker_model, ("workers", "effort"): args.worker_effort,
               ("validators", "model"): args.validator_model, ("validators", "effort"): args.validator_effort}
    changes = {key: value for key, value in changes.items() if value}
    if not changes:
        require_board(root)
        config = read_config(root)
        print(pm_workers.defaults_text(config))
        missing = pm_workers.missing_defaults(config)
        if missing:
            print("Not recorded yet: " + ", ".join(missing) + ". Ask the person; do not pick them.")
        return

    def change(board: Path):
        require_board(board)
        config = read_config(board)
        for (role, key), value in changes.items():
            config.setdefault(role, {})[key] = value
        config_path(board).write_text(json.dumps(config) + "\n", encoding="utf-8")
        return [config_path(board)], "Recorded defaults.\n" + pm_workers.defaults_text(config)
    with write_lock(root):
        print(publish(root, change))


PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def cmd_worker(root: Path, args) -> int:
    action = args.action
    if action == "mode":
        return pm_workers.cmd_mode(root, args)
    if action == "list":
        return pm_workers.cmd_list(root, {item["id"]: item for item in read_items(board_checkout(root))})
    if action == "start":
        require_board(board_checkout(root))
        person, _, note = read_literal_stdin().partition("\n")
        if not person.strip():
            raise ValueError("The person's name is required on the first stdin line; the worker claims under it.")
        find_item(read_items(board_checkout(root)), args.id)
        return pm_workers.cmd_start(root, args, PLUGIN_ROOT, read_config(board_checkout(root)), person.strip(), note)
    if action == "answer":
        message = read_literal_stdin()
        if not message.strip():
            raise ValueError("The message for the worker is required on stdin.")
        return pm_workers.cmd_answer(root, args, PLUGIN_ROOT, message)
    return {"wait": pm_workers.cmd_wait, "stop": pm_workers.cmd_stop, "remove": pm_workers.cmd_remove}[action](root, args)


def cmd_sync(root: Path, args) -> None:
    created: dict[str, str] = {}
    failure: list[ValueError] = []

    def change(board: Path):
        if mirror_setting(board) != "github":
            raise ValueError("GitHub Issues mirror is off. Enable it with `pm.py mirror github` first.")
        failure.clear()
        items = read_items(board)
        recorded = {item["id"]: item.get("github_issue", "") for item in items}
        lines = []
        try:
            for item in items:
                item["github_issue"] = recorded[item["id"]] or created.get(item["id"], "")
                lines.append(sync_issue(root, item, created))
        except ValueError as exc:
            failure.append(exc)
        paths = []
        for item in items:
            if item["id"] in created and not recorded[item["id"]]:
                item["github_issue"] = created[item["id"]]
                save_item(item)
                paths.append(item["path"])
        return paths, "\n".join([f"Synced {len(lines)} items to GitHub Issues", *lines])
    with write_lock(root):
        print(publish(root, change))
    if failure:
        raise failure[0]


def sync_issue(root: Path, item: dict, created: dict[str, str]) -> str:
    body = f"Requester intent (verbatim):\n\n{item['intent']}\n\nCurrent notes:\n\n{item.get('notes', '')}\n\nStatus: {item.get('status')}"
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
        created[item["id"]] = number
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
    return f"{item['id']} -> {issue_url}"


def count_line(items: list[dict]) -> str:
    counts = pm_migrate.status_counts(item.get("status", "queued") for item in items)
    return f"{len(items)} items ({pm_migrate.format_counts(counts)})"


def cmd_migrate(root: Path, args) -> None:
    if args.action == "scan":
        remote = git(root, "remote", "get-url", "origin", check=False).stdout.strip()
        findings = pm_migrate.scan(root, remote)
        if config_path(root).exists():
            print(f"A 1.x board already exists here: {count_line(read_items(root))}.")
        if not findings:
            print("No existing project-management system found." if not config_path(root).exists() else "No other system found.")
            return
        print("Existing systems found:")
        for number, found in enumerate(findings, 1):
            print(f"{number}. {found['label']}: {found['detail']}")
            print("   " + (f"Importer: {found['importer']}. Next: {found['command']}" if found["importer"]
                           else "No built-in importer: map it by hand with the owner (docs/manual.md)."))
        return
    if args.action == "plan":
        reader = pm_migrate.SOURCES[args.source]
        plan = reader(root, file=args.file)
        problems = pm_migrate.validate_plan(plan)
        if problems:
            raise ValueError("The generated plan is invalid:\n" + "\n".join(f"  - {p}" for p in problems))
        Path(args.out).write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(pm_migrate.render_plan(plan))
        print(f"\nPlan saved to {args.out}. Nothing was changed. Edit it if the owner asks, then run: pm.py migrate apply {args.out}")
        return
    try:
        plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read plan {args.plan}: {exc}")
    problems = pm_migrate.validate_plan(plan)
    if problems:
        raise ValueError("The plan is not safe to apply:\n" + "\n".join(f"  - {p}" for p in problems))
    source = plan["source"].strip()
    planned = []
    for entry in plan["items"]:
        digest = hashlib.sha256(f"{source}:{entry['key']}".encode()).hexdigest()[:6]
        planned.append((entry, digest, f"{item_slug(entry['title'])}-{digest}"))

    def board_ids(board: Path) -> tuple[dict[str, str], dict[str, str]]:
        existing = {item["id"].rsplit("-", 1)[-1].casefold(): item["id"] for item in read_items(board)}
        return {entry["key"]: existing.get(digest, item_id) for entry, digest, item_id in planned}, existing

    if args.dry_run:
        ids, existing = board_ids(root)
        print(f"Dry run: {sum(digest not in existing for _, digest, _ in planned)} items would be created from {source}; nothing written.")
        for entry, digest, _ in planned:
            print(f"  {entry['key']} -> {ids[entry['key']]} ({'already on the board' if digest in existing else pm_migrate.plan_status(entry)})")
        return

    def change(board: Path):
        paths = []
        config = json.loads(config_path(board).read_text(encoding="utf-8")) if config_path(board).exists() else {"mirror": "off"}
        record = config.setdefault("migrated_from", {})
        accounted = sorted({entry["key"] for entry in plan["items"]} | {entry["key"] for entry in plan.get("history", [])}
                           | set(record.get(source, [])))
        if record.get(source) != accounted:
            record[source] = accounted
            config_path(board).parent.mkdir(parents=True, exist_ok=True)
            config_path(board).write_text(json.dumps(config) + "\n", encoding="utf-8")
            paths.append(config_path(board))
        ids, existing = board_ids(board)
        created = skipped = 0
        for entry, digest, item_id in planned:
            if digest in existing:
                skipped += 1
                continue
            item = {"id": item_id, "title": entry["title"].strip(), "owner": entry.get("owner", ""),
                    "status": pm_migrate.plan_status(entry),
                    "depends_on": [ids[dep] for dep in entry.get("depends_on", [])], "hold": entry.get("hold", ""),
                    "hold_until": entry.get("hold_until", ""), "github_issue": entry.get("github_issue", ""),
                    "intent": entry["intent"], "intent_length": len(entry["intent"]), "notes": entry.get("notes", ""),
                    "done_at": "", "path": item_dir(board) / f"{item_id}.md"}
            save_item(item)
            paths.append(item["path"])
            created += 1
        after = read_items(board)
        history = plan.get("history", [])
        lines = [f"Migrated {created} items from {source}" + (f" ({skipped} already on the board, left as they were)" if skipped else ""),
                 f"Before: {plan.get('before', {}).get('total', 'unknown')} entries in the old system.",
                 f"Imported {len(planned)}, left in git history {len(history)}; accounted for {len(planned) + len(history)}.",
                 f"Board now: {count_line(after)}.",
                 "Nothing in the old system was deleted. Remove it only after the owner confirms."]
        return paths, "\n".join(lines)
    with write_lock(root):
        print(publish(root, change))


# Without a remote these read or write the main checkout's board from any worktree; finish stays on the work branch.
BOARD_WRITES = {"add", "claim", "hold", "resume", "set", "correct"}
SHARED_BOARD_COMMANDS = BOARD_WRITES | {"board", "next", "defaults"}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Manage the docs/pm markdown board. Text values are read literally from stdin.")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="create an empty board")
    sub.add_parser("board", help="show status at a glance")
    sub.add_parser("next", help="list queued items whose dependencies are done")
    add = sub.add_parser("add", help="create an item; stdin is the title line followed by the requester's exact words")
    add.add_argument("--touches", help="comma-separated map cards or stage folders the item touches")
    claim = sub.add_parser("claim", help="claim an item before work; stdin is the person's name")
    claim.add_argument("id")
    claim.add_argument("--resume", action="store_true", help="continue your own in-flight claim (after a hold or a new session)")
    sub.add_parser("finish", help="mark an in-flight item done; stdin is the completion note").add_argument("id")
    validated = sub.add_parser("validated", help="record a pm:validator verdict for committed work; stdin is its summary")
    validated.add_argument("id")
    validated.add_argument("--verdict", choices=("pass", "findings"), required=True)
    resume = sub.add_parser("resume", help="release a hold; a claimed item returns to its owner In flight, others to queue")
    resume.add_argument("id")
    resume.add_argument("--answer", action="store_true", help="stdin is the decider's exact words; saved at the top of the item's current notes")
    hold = sub.add_parser("hold", help="park an item for a decision; stdin is the question")
    hold.add_argument("id"); hold.add_argument("--until", default="")
    update = sub.add_parser("set", help="set dependencies and the map cards or stage folders an item touches")
    update.add_argument("id"); update.add_argument("--depends"); update.add_argument("--touches")
    correct = sub.add_parser("correct", help="record a correction of the agent's output; stdin says what was corrected")
    correct.add_argument("id"); correct.add_argument("--kind", required=True, help="short name, reused for the same kind")
    correct.add_argument("--where", default="", help="the contract, card, or file the output came from")
    correct.add_argument("--fixed", action="store_true", help="the source was changed for this kind; stdin says how")
    sub.add_parser("walk", help="check the ICM structure: entry file, contracts, map cards, links, token budget (read-only)")
    sub.add_parser("index", help="rebuild docs/pm/map/_index.md from the cards' frontmatter")
    places = sub.add_parser("places", help="list new files outside the places in AGENTS.md > Where things go (read-only)")
    places.add_argument("--paths", action="store_true", help="print only the paths, one per line, and always exit 0")
    refs = sub.add_parser("refs", help="before moving files: what points at each path, and whether its destination is free (read-only)")
    refs.add_argument("paths", nargs="+", metavar="OLD[=NEW]")
    mirror = sub.add_parser("mirror", help="configure the optional GitHub Issues mirror")
    mirror.add_argument("mode", choices=("show", "off", "github"))
    sub.add_parser("sync", help="sync items to GitHub Issues when enabled")
    defaults = sub.add_parser("defaults", help="show or record the model and effort worker sessions and their validators use")
    defaults.add_argument("--worker-model", help="model alias or full name for worker sessions")
    defaults.add_argument("--worker-effort", choices=pm_workers.EFFORTS)
    defaults.add_argument("--validator-model", choices=pm_workers.VALIDATOR_MODELS,
                          help="model for the validator subagent; inherit uses the worker's")
    defaults.add_argument("--validator-effort", choices=pm_workers.EFFORTS)
    worker = sub.add_parser("worker", help="run board items in their own Claude Code worker sessions")
    wactions = worker.add_subparsers(dest="action", required=True)
    start = wactions.add_parser("start", help="start a worker session for an item and wait for its turn to end; "
                                "stdin is the person's name, then an optional note")
    start.add_argument("id")
    start.add_argument("--here", action="store_true", help="run in this checkout instead of the item's own worktree")
    start.add_argument("--resume", action="store_true", help="the worker continues an existing claim")
    start.add_argument("--fresh", action="store_true", help="replace the item's earlier worker session with a new one")
    start.add_argument("--model", help="the person's model for this worker, instead of the default")
    start.add_argument("--effort", choices=pm_workers.EFFORTS, help="the person's effort for this worker")
    start.add_argument("--validator-model", choices=pm_workers.VALIDATOR_MODELS)
    start.add_argument("--validator-effort", choices=pm_workers.EFFORTS)
    start.add_argument("--no-wait", action="store_true", help="return once started; `worker wait` reads the report")
    answer = wactions.add_parser("answer", help="continue an item's worker session with a message, keeping its context; "
                                 "stdin is the message")
    answer.add_argument("id")
    answer.add_argument("--allow", action="append", metavar="TOOL",
                        help="a tool the person allowed for this worker, e.g. 'Bash(npm test)' (repeatable)")
    answer.add_argument("--no-wait", action="store_true")
    for name, text in (("wait", "wait for a running worker session and print its report"),
                       ("stop", "stop a running worker session; its conversation is kept"),
                       ("remove", "remove a finished item's worker worktree and session record; its branch is kept")):
        wactions.add_parser(name, help=text).add_argument("id")
    wactions.add_parser("list", help="each worker session: its item, what it is doing or waiting on")
    mode = wactions.add_parser("mode", help="show or choose this clone's permission setting for worker sessions")
    mode.add_argument("mode", nargs="?", choices=pm_workers.PERMISSION_MODES)
    migrate = sub.add_parser("migrate", help="move an existing task system onto the board; never deletes the old one")
    actions = migrate.add_subparsers(dest="action", required=True)
    actions.add_parser("scan", help="list the task systems found in this repository (read-only)")
    plan = actions.add_parser("plan", help="read the old system and save a migration plan (read-only)")
    plan.add_argument("--from", dest="source", required=True, choices=sorted(pm_migrate.SOURCES))
    plan.add_argument("--file", help="the file to read, for --from checklist")
    plan.add_argument("--out", required=True, help="where to save the plan JSON, outside the repository")
    apply = actions.add_parser("apply", help="create the items a confirmed plan describes")
    apply.add_argument("plan", help="plan JSON from `migrate plan`, or one written by hand")
    apply.add_argument("--dry-run", action="store_true", help="validate and list the items without writing")
    return p


def main() -> int:
    args = parser().parse_args()
    root = root_dir()
    try:
        note = ""
        shared = board_checkout(root) if args.command in SHARED_BOARD_COMMANDS else root
        if shared != root:
            here = git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
            there = git(shared, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
            if args.command in BOARD_WRITES:
                note = (f"No remote, so the board is in the main checkout {shared}: saved on {there}; "
                        f"branch {here} shows it only after syncing with {there}.")
            root = shared
        code = {"init": cmd_init, "board": cmd_board, "next": cmd_next, "add": cmd_add,
                "claim": cmd_claim, "finish": cmd_finish, "validated": cmd_validated, "hold": cmd_hold, "resume": cmd_resume,
                "set": cmd_set, "correct": cmd_correct, "walk": cmd_walk, "index": cmd_index, "places": cmd_places,
                "refs": cmd_refs, "mirror": cmd_mirror, "sync": cmd_sync, "migrate": cmd_migrate,
                "defaults": cmd_defaults, "worker": cmd_worker}[args.command](root, args)
        if note:
            print(note)
        if isinstance(code, int):
            return code
    except (ValueError, OSError) as exc:
        print(f"pm: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
