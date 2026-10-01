"""Readers that turn another task system into a migration plan for the docs/pm board.

Everything here is read-only and returns plain data. A *plan* is a JSON-serialisable dict that
`scripts/pm.py migrate apply` validates and writes as items; see `docs/manual.md` for its shape.
To support a new source system, add a reader to SOURCES and a detector to `scan`.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

PLAN_STATUSES = ("queued", "in-flight")
BOARD_STATUSES = ("queued", "in-flight", "waiting", "done")
OPTIONAL_TEXT_FIELDS = ("owner", "hold", "hold_until", "notes", "github_issue")
CHECKLIST_NAMES = {"todo", "todos", "roadmap", "backlog", "tasks", "plan"}
CHECKLIST_SUFFIXES = {"", ".md", ".markdown", ".txt"}
TASK_FOLDERS = {".beads": "Beads", ".taskmaster": "Task Master", "backlog": "Backlog.md-style folder",
                "tasks": "task folder", "issues": "issue folder", "todo": "task folder", ".tasks": "task folder"}
TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".json", ".jsonl", ".yml", ".yaml", ".toml", ".db", ".csv"}
CODE_SUFFIXES = {".py", ".js", ".ts", ".tsx", ".go", ".rs", ".rb", ".java", ".sh"}
CHECK_RE = re.compile(r"^(\s*)[-*+]\s+\[([ xX])\]\s+(.*)$")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def short_title(text: str, limit: int = 80) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------- pm-plugin 0.x

def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse the 0.x frontmatter: `key: value` lines, `[a, b]` lists, and a trailing ` # comment`."""
    match = re.match(r"\A---\n(.*?)\n---[ \t]*(?:\n|\Z)(.*)\Z", text, re.S)
    if not match:
        return {}, text
    meta: dict = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            continue
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            meta[key.strip()] = [v.strip() for v in inner.split(",") if v.strip()] if inner else []
        else:
            meta[key.strip()] = value.split("#", 1)[0].strip() if " #" in value else value
    return meta, match.group(2)


def split_sections(body: str) -> list[tuple[str, str]]:
    """Split a body at `## ` headings into (lowercase heading, raw block incl. the heading line).

    Text before the first heading comes back under the empty name."""
    marks = list(re.finditer(r"^## (.+?)\s*$", body, re.M))
    if not marks:
        return [("", body)]
    blocks = [("", body[:marks[0].start()])] if body[:marks[0].start()].strip() else []
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(body)
        blocks.append((mark.group(1).strip().lower(), body[mark.start():end]))
    return blocks


def section_body(body: str, heading: str) -> str:
    for name, block in split_sections(body):
        if name == heading.lower():
            return block.split("\n", 1)[1].strip() if "\n" in block else ""
    return ""


def placeholder_only(text: str) -> bool:
    """True for empty text or a 0.x template stub such as `Approach:` / `approved: no`."""
    return all(not line.strip() or re.fullmatch(r"[\w ]+:\s*(?:no|none)?", line.strip(), re.I)
               for line in text.splitlines())


def issue_number(value: str) -> str:
    match = re.fullmatch(r"#?(\d+)|.*/issues/(\d+)/?", value.strip())
    return (match.group(1) or match.group(2)) if match else ""


def reference(value: str) -> str:
    return f"#{value}" if value.isdigit() else value


def read_0x(root: Path, **_: object) -> dict:
    """Read a pm-plugin 0.x board: docs/pm/tickets/T*.md, epics/, roadmap.md, decisions.md, CONTEXT.md."""
    pm = root / "docs" / "pm"
    tickets = []
    for path in sorted((pm / "tickets").glob("T*.md")):
        meta, body = parse_frontmatter(read_text(path))
        title_line = re.search(r"^# (.+)$", body, re.M)
        tickets.append({
            "id": str(meta.get("id") or path.stem.split("-")[0]),
            "title": str(meta.get("title") or (title_line.group(1) if title_line else path.stem)),
            "epic": str(meta.get("epic", "")), "milestone": str(meta.get("milestone", "")),
            "status": str(meta.get("status", "todo")).lower() or "todo",
            "priority": str(meta.get("priority", "")).upper(),
            "depends_on": meta.get("depends_on", []) if isinstance(meta.get("depends_on", []), list)
            else [d.strip() for d in str(meta["depends_on"]).split(",") if d.strip()],
            "owner": str(meta.get("owner", "")), "issue": str(meta.get("issue", "")), "pr": str(meta.get("pr", "")),
            "ready": str(meta.get("ready", "yes")).strip().lower() not in {"no", "false", "off", "0"},
            "path": path.relative_to(root).as_posix(), "body": body,
        })
    epics = {}
    for path in sorted((pm / "epics").glob("E*.md")):
        meta, body = parse_frontmatter(read_text(path))
        epic_id = str(meta.get("id") or path.stem.split("-")[0])
        epics[epic_id] = {"title": str(meta.get("title", "")), "goal": section_body(body, "Goal"),
                          "path": path.relative_to(root).as_posix()}
    by_id = {t["id"]: t for t in tickets}
    warnings: list[str] = []
    items, history = [], []
    imported = {t["id"] for t in tickets if t["status"] not in ("dismissed", "done")}
    dropped_done = 0
    for t in tickets:
        status = t["status"]
        if status in ("dismissed", "done"):
            history.append({"key": t["id"], "title": t["title"], "status": status,
                            "why": "closed without being done" if status == "dismissed" else "done work stays in git history"})
            continue
        owner, hold, extra = t["owner"], "", []
        if status in ("in progress", "review"):
            mapped = "in-flight"
            if not owner:
                mapped = "queued"
                warnings.append(f"{t['id']} is {status} with no owner; imported as queued so someone can claim it.")
            extra.append("In review (0.x status review)." if status == "review" else "")
        else:
            mapped = "queued"
            if status != "todo":
                warnings.append(f"{t['id']} has unknown status '{status}'; imported as queued.")
            if not t["ready"]:
                hold = "Not yet clarified in pm 0.x (ready: no). Confirm what, why and acceptance before starting."
        deps = []
        for dep in t["depends_on"]:
            if dep == t["id"]:
                warnings.append(f"{t['id']} listed itself as a dependency; dropped.")
            elif dep in imported:
                deps.append(dep)
            elif dep not in by_id:
                warnings.append(f"{t['id']} depends on unknown ticket {dep}; dependency dropped.")
            elif by_id[dep]["status"] == "dismissed":
                warnings.append(f"{t['id']} depended on {dep}, which was dismissed; dependency dropped.")
            else:
                dropped_done += 1
        facts = []
        epic = epics.get(t["epic"])
        if t["epic"]:
            facts.append(f"epic {t['epic']}" + (f" {epic['title']}" if epic and epic["title"] else ""))
        if t["milestone"]:
            facts.append(f"milestone {t['milestone']}")
        if t["priority"]:
            facts.append(f"priority {t['priority']}")
        if t["pr"]:
            facts.append(f"PR {reference(t['pr'])}")
        number = issue_number(t["issue"]) if t["issue"] else ""
        if t["issue"] and not number:
            facts.append(f"issue {t['issue']}")
        notes = [f"Migrated from pm-plugin 0.x ticket {t['id']}" + (f" ({', '.join(facts)})." if facts else ".")]
        notes.extend(line for line in extra if line)
        if epic and epic["goal"]:
            notes.append(f"Epic goal: {epic['goal']}")
        intent_parts, note_parts = [], []
        for name, block in split_sections(t["body"]):
            if name in ("plan", "notes", "proposed changes"):
                text = block.split("\n", 1)[1].strip() if "\n" in block else ""
                if text and not (name == "plan" and placeholder_only(text)):
                    note_parts.append(f"{name.capitalize()} (0.x):\n{text}")
            else:
                intent_parts.append(block)
        intent = "".join(intent_parts).strip("\n") or t["title"]
        items.append({"key": t["id"], "title": t["title"], "intent": intent, "status": mapped, "owner": owner,
                      "hold": hold, "hold_until": "", "depends_on": deps, "github_issue": number,
                      "notes": "\n\n".join([*note_parts, "\n".join(notes)])})
    if dropped_done:
        warnings.append(f"{dropped_done} dependency link(s) on finished tickets dropped, since they are already satisfied.")

    knowledge, retire = [], []
    backlog_lines: list[str] = []
    roadmap = pm / "roadmap.md"
    if roadmap.exists():
        text = read_text(roadmap)
        milestones = re.findall(r"^## (M\d+)\s*[:\-]?\s*(.*)$", text, re.M)
        backlog = section_body(text, "Backlog")
        backlog_lines = [m.group(1).strip() for m in re.finditer(r"^\s*[-*]\s+(.+)$", backlog, re.M)
                         if not re.fullmatch(r"\(?\s*(nothing yet|none)\s*\)?\.?", m.group(1).strip(), re.I)]
        knowledge.append({"from": "docs/pm/roadmap.md",
                          "what": f"{len(milestones)} milestone(s): " + "; ".join(f"{k} {v}".strip() for k, v in milestones),
                          "route": "Product direction and goals go to README.md; each item's notes already name its milestone. Ask the owner before writing."})
        retire.append("docs/pm/roadmap.md")
    for number, line in enumerate(backlog_lines, 1):
        items.append({"key": f"backlog-{number}-{slugify(line)[:40]}", "title": short_title(line), "intent": line,
                      "status": "queued", "owner": "", "hold": "", "hold_until": "", "depends_on": [],
                      "github_issue": "",
                      "notes": "Migrated from the pm-plugin 0.x roadmap Backlog (no epic or milestone)."})
    if epics:
        knowledge.append({"from": "docs/pm/epics/",
                          "what": f"{len(epics)} epic(s): " + "; ".join(f"{k} {v['title']}".strip() for k, v in epics.items()),
                          "route": "Epic goals of open tickets were copied into those items' notes. Goals of finished epics go to README.md only if they still describe the product."})
        retire.append("docs/pm/epics")
    decisions = pm / "decisions.md"
    if decisions.exists():
        entries = re.findall(r"^## (.+?)\s*$", read_text(decisions), re.M)
        knowledge.append({"from": "docs/pm/decisions.md", "what": f"{len(entries)} decision(s): " + "; ".join(entries),
                          "route": "Decisions that shape future work become guidance in AGENTS.md (architectural ones in docs/pm/CODEBASE.md); one that only explains a past change stays in git history. Go through them with the owner."})
        retire.append("docs/pm/decisions.md")
    context = root / "CONTEXT.md"
    if context.exists():
        block = re.search(r"^## pm[ \t]*\n(.*?)(?=^#{1,2} |\Z)", read_text(context), re.M | re.S)
        if block:
            settings = dict(line.strip().split(":", 1) for line in block.group(1).splitlines() if ":" in line)
            settings = {k.strip(): v.strip() for k, v in settings.items()}
            routes = ["the `## pm` block has no 1.x equivalent and can be removed from CONTEXT.md; keep the rest of the file"]
            if settings.get("check"):
                routes.append(f"check command `{settings['check']}` belongs in AGENTS.md as the project's test/lint command")
            if settings.get("mirror", "off") not in ("off", ""):
                routes.append(f"mirror was `{settings['mirror']}`; 1.x leaves it off until the owner runs `pm.py mirror github`")
            knowledge.append({"from": "CONTEXT.md (## pm block)", "what": ", ".join(f"{k}={v}" for k, v in settings.items()),
                              "route": "; ".join(routes)})
    if (pm / "tickets").exists():
        retire.insert(0, "docs/pm/tickets")
    known = {"tickets", "epics", "roadmap.md", "decisions.md", "config.json", "items", "CODEBASE.md"}
    stray = sorted(p.name for p in pm.iterdir() if p.name not in known) if pm.exists() else []
    if stray:
        warnings.append("Other files under docs/pm were left alone and are not in the retire list: " + ", ".join(stray) + ".")

    by_status: dict[str, int] = {}
    for t in tickets:
        by_status[t["status"]] = by_status.get(t["status"], 0) + 1
    if backlog_lines:
        by_status["backlog"] = len(backlog_lines)
    return {"source": "pm-0x", "before": {"total": len(tickets) + len(backlog_lines), "by_status": by_status},
            "items": items, "history": history, "knowledge": knowledge, "warnings": warnings, "retire": retire,
            "not_carried_over": ["auto, plan (approval gate), tests and confidence: 1.x has no equivalent (ready: no became a decision hold)",
                                 "priority P0-P3: noted in the item's notes, not ordered"]}


# ---------------------------------------------------------------- markdown checklist

def parse_checklist(text: str) -> tuple[list[dict], int]:
    """Return (entries, prose_lines). An entry is a top-level checkbox plus everything indented under it;
    nested checkboxes stay inside their parent. Each entry has indent, done, heading and lines."""
    entries: list[dict] = []
    current: dict | None = None
    heading, prose = "", 0

    def flush():
        nonlocal current
        if current:
            while current["lines"] and not current["lines"][-1].strip():
                current["lines"].pop()
            entries.append(current)
        current = None

    for line in text.splitlines():
        head = re.match(r"^#{1,6}\s+(.*?)\s*#*\s*$", line)
        check = CHECK_RE.match(line)
        indent = len(line) - len(line.lstrip())
        if head:
            flush()
            heading = head.group(1)
        elif check and (current is None or len(check.group(1)) <= current["indent"]):
            flush()
            current = {"indent": len(check.group(1)), "done": check.group(2) != " ", "heading": heading,
                       "lines": [check.group(3)]}
        elif current and (not line.strip() or indent > current["indent"]):
            current["lines"].append(line)
        else:
            flush()
            prose += bool(line.strip())
    flush()
    return entries, prose


def read_checklist(root: Path, file: str | None = None, **_: object) -> dict:
    """Read `- [ ]` / `- [x]` lines from one Markdown file. Other bullet styles need a hand-made plan."""
    if not file:
        raise ValueError("The checklist source needs --file PATH, for example --file TODO.md.")
    path = (root / file).resolve()
    if not path.is_file() or root.resolve() not in path.parents:
        raise ValueError(f"{file} is not a file inside this repository.")
    rel = path.relative_to(root.resolve()).as_posix()
    entries, prose = parse_checklist(read_text(path))

    items, history, seen = [], [], {}
    for entry in entries:
        first = entry["lines"][0]
        slug = slugify(first)[:40] or "item"
        seen[slug] = seen.get(slug, 0) + 1
        key = f"{rel}:{slug}" + (f"-{seen[slug]}" if seen[slug] > 1 else "")
        title = short_title(first)
        if entry["done"]:
            history.append({"key": key, "title": title, "status": "done", "why": "done work stays in git history"})
            continue
        where = f', under "{entry["heading"]}"' if entry["heading"] else ""
        items.append({"key": key, "title": title, "intent": "\n".join(entry["lines"]),
                      "status": "queued", "owner": "", "hold": "", "hold_until": "",
                      "depends_on": [], "github_issue": "",
                      "notes": f"Migrated from {rel}{where}."})
    knowledge, warnings, retire = [], [], []
    if prose:
        knowledge.append({"from": rel, "what": f"{prose} line(s) of text that are not checklist items",
                          "route": "Lasting rules go to AGENTS.md, the product description to README.md, architecture to docs/pm/CODEBASE.md; anything else stays where it is. Ask the owner."})
        warnings.append(f"{rel} also holds other text, so it is not on the retire list; remove the migrated checkboxes by hand.")
    else:
        retire.append(rel)
    if not entries:
        warnings.append(f"No `- [ ]` or `- [x]` lines found in {rel}; map it by hand (see docs/manual.md).")
    return {"source": f"checklist:{rel}", "before": {"total": len(entries), "by_status": {
            "open": sum(not e["done"] for e in entries), "done": sum(e["done"] for e in entries)}},
            "items": items, "history": history, "knowledge": knowledge, "warnings": warnings, "retire": retire,
            "not_carried_over": ["owners, dates, labels and `#123` references in the text stay inside the intent; the owner can ask for them to be mapped"]}


SOURCES = {"pm-0x": read_0x, "checklist": read_checklist}


# ---------------------------------------------------------------- detection

def scan(root: Path, remote_url: str = "") -> list[dict]:
    """Look for known task systems. Returns findings: system, label, paths, detail, importer, command."""
    found = []
    pm = root / "docs" / "pm"
    tickets = sorted((pm / "tickets").glob("T*.md"))
    if tickets:
        epics = len(list((pm / "epics").glob("E*.md")))
        extras = [name for name in ("roadmap.md", "decisions.md") if (pm / name).exists()]
        found.append({"system": "pm-0x", "label": "pm-plugin 0.x board", "paths": ["docs/pm/tickets"],
                      "detail": f"{len(tickets)} tickets, {epics} epics" + (", " + ", ".join(extras) if extras else ""),
                      "importer": "pm-0x", "command": "pm.py migrate plan --from pm-0x --out PLAN.json"})
    candidates = [p for base in (root, root / "docs") if base.is_dir() for p in sorted(base.iterdir())]
    for path in candidates:
        if path.is_file() and path.stem.lower() in CHECKLIST_NAMES and path.suffix.lower() in CHECKLIST_SUFFIXES:
            rel = path.relative_to(root).as_posix()
            entries, _ = parse_checklist(read_text(path))
            open_count = sum(not e["done"] for e in entries)
            done_count = len(entries) - open_count
            if open_count or done_count:
                found.append({"system": "checklist", "label": f"checklist file {rel}", "paths": [rel],
                              "detail": f"{open_count} open, {done_count} done checkboxes", "importer": "checklist",
                              "command": f"pm.py migrate plan --from checklist --file {rel} --out PLAN.json"})
            else:
                found.append({"system": "notes-file", "label": f"task notes file {rel}", "paths": [rel],
                              "detail": f"{len(read_text(path).splitlines())} lines, no checkboxes",
                              "importer": "", "command": ""})
        elif path.is_file() and path.suffix.lower() == ".csv" and re.search(r"linear|issue|ticket|backlog|task", path.stem, re.I):
            rel = path.relative_to(root).as_posix()
            found.append({"system": "export", "label": f"tracker export {rel}", "paths": [rel],
                          "detail": "CSV file", "importer": "", "command": ""})
    for name, label in TASK_FOLDERS.items():
        folder = root / name
        if not folder.is_dir():
            continue
        files = [p for p in folder.rglob("*") if p.is_file()]
        if not files or any(p.suffix.lower() in CODE_SUFFIXES for p in files):
            continue
        if name[0] != "." and not any(p.suffix.lower() in TEXT_SUFFIXES for p in files):
            continue
        found.append({"system": name.strip("."), "label": f"{label} {name}/", "paths": [name + "/"],
                      "detail": f"{len(files)} files", "importer": "", "command": ""})
    if "github.com" in remote_url:
        found.append({"system": "github-issues", "label": "GitHub Issues (possible)", "paths": [],
                      "detail": "the remote is on GitHub; open issues may be the backlog: `gh issue list --state open`",
                      "importer": "", "command": ""})
    return found


# ---------------------------------------------------------------- plans

def plan_status(item: dict) -> str:
    """The 1.x board status an item will get: a hold on unfinished work means waiting."""
    return "waiting" if item.get("hold") else item.get("status", "queued")


def status_counts(statuses) -> dict[str, int]:
    counts = dict.fromkeys(BOARD_STATUSES, 0)
    for status in statuses:
        counts[status] += 1
    return counts


def format_counts(counts: dict[str, int]) -> str:
    return ", ".join(f"{n} {name.replace('-', ' ')}" for name, n in counts.items())


def validate_plan(plan: object) -> list[str]:
    """Return every problem that would make the plan unsafe to apply; an empty list means it is valid."""
    if not isinstance(plan, dict):
        return ["The plan must be a JSON object."]
    errors = []
    if not isinstance(plan.get("source"), str) or not plan["source"].strip():
        errors.append("source must be a non-empty string naming the old system, for example \"beads\".")
    items = plan.get("items")
    if not isinstance(items, list):
        return errors + ["items must be a list."]
    keys = [item.get("key") for item in items if isinstance(item, dict)]
    for number, item in enumerate(items, 1):
        if not isinstance(item, dict):
            errors.append(f"items[{number}] must be an object.")
            continue
        name = f"item {item.get('key') or number}"
        for field in ("key", "title", "intent"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                errors.append(f"{name}: {field} must be a non-empty string (intent is the requester's original words).")
        if isinstance(item.get("title"), str) and len(item["title"].strip().splitlines()) > 1:
            errors.append(f"{name}: title must be a single line; put the rest in intent.")
        for field in OPTIONAL_TEXT_FIELDS:
            if field in item and not isinstance(item[field], str):
                errors.append(f"{name}: {field} must be a string; leave it out instead of {json.dumps(item[field])}.")
        if keys.count(item.get("key")) > 1:
            errors.append(f"{name}: key is used more than once.")
        status = item.get("status", "queued")
        if status not in PLAN_STATUSES:
            errors.append(f"{name}: status must be one of {', '.join(PLAN_STATUSES)}, not {status!r}.")
        if status == "in-flight" and not (isinstance(item.get("owner"), str) and item["owner"].strip()):
            errors.append(f"{name}: an in-flight item needs an owner.")
        if isinstance(item.get("github_issue"), str) and item["github_issue"] and not item["github_issue"].isdigit():
            errors.append(f"{name}: github_issue must be the issue number, digits only.")
        deps = item.get("depends_on", [])
        if not isinstance(deps, list):
            errors.append(f"{name}: depends_on must be a list of item keys.")
            continue
        for dep in deps:
            if not isinstance(dep, str):
                errors.append(f"{name}: depends_on must list item keys as strings, not {json.dumps(dep)}.")
            elif dep not in keys:
                errors.append(f"{name}: depends on {dep!r}, which is not an item in the plan.")
            elif dep == item.get("key"):
                errors.append(f"{name}: cannot depend on itself.")
    if errors:
        return errors
    graph = {i["key"]: i.get("depends_on", []) for i in items}
    visiting, finished = set(), set()

    def cycle(key: str, trail: list[str]) -> list[str] | None:
        if key in finished:
            return None
        if key in visiting:
            return trail[trail.index(key):] + [key]
        visiting.add(key)
        for dep in graph.get(key, []):
            found = cycle(dep, trail + [key])
            if found:
                return found
        visiting.discard(key)
        finished.add(key)
        return None

    for key in graph:
        found = cycle(key, [])
        if found:
            errors.append("Dependencies form a cycle: " + " -> ".join(found) + ".")
            break
    return errors


def render_plan(plan: dict) -> str:
    """Human-readable summary the owner confirms before anything is written."""
    items, history = plan.get("items", []), plan.get("history", [])
    before = plan.get("before", {})
    lines = [f"Migration plan from {plan.get('source')}"]
    if before:
        detail = ", ".join(f"{n} {status}" for status, n in before.get("by_status", {}).items())
        lines.append(f"Before: {before.get('total', 0)} entries in the old system ({detail})")
    lines.append(f"After:  {len(items)} items on the board ({format_counts(status_counts(map(plan_status, items)))})")
    if history:
        by_reason: dict[str, int] = {}
        for entry in history:
            by_reason[entry.get("status", "closed")] = by_reason.get(entry.get("status", "closed"), 0) + 1
        lines.append("Left in git history, not imported: " + ", ".join(f"{n} {s}" for s, n in by_reason.items()))
    if before and before.get("total", 0) != len(items) + len(history):
        lines.append(f"[check] {before.get('total', 0)} entries before but {len(items) + len(history)} accounted for.")
    lines += ["", "Items (old key -> status, waits on):"]
    for item in items:
        deps = ", ".join(item.get("depends_on", []))
        extras = [f"owner {item['owner']}"] if item.get("owner") else []
        if item.get("hold"):
            extras.append("held")
        if item.get("github_issue"):
            extras.append(f"issue #{item['github_issue']}")
        lines.append(f"  {item['key']} -> {plan_status(item)}" + (f", waits on {deps}" if deps else "")
                     + (f" ({'; '.join(extras)})" if extras else "") + f": {item['title']}")
    for heading, key in (("Warnings", "warnings"), ("Not carried over", "not_carried_over")):
        if plan.get(key):
            lines += ["", f"{heading}:"] + [f"  - {text}" for text in plan[key]]
    if plan.get("knowledge"):
        lines += ["", "Knowledge that is not an item, and where it goes (see docs/placement.md):"]
        lines += [f"  - {k['from']}: {k['what']}\n      -> {k['route']}" for k in plan["knowledge"]]
    if plan.get("retire"):
        lines += ["", "Old files to remove only after the owner confirms: " + ", ".join(plan["retire"])]
    return "\n".join(lines)
