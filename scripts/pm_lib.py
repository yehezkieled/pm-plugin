"""Shared library for the pm plugin. Standard library only.

Reads and writes the markdown files under docs/pm and the `## pm` block in
CONTEXT.md. No dates, no time estimates: order and priority only.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

PM_SUBDIR = Path("docs") / "pm"
STATUSES = ["todo", "in progress", "review", "done", "dismissed"]
CLOSED = ("done", "dismissed")  # a dismissed ticket is closed without being done
TESTS_STATES = ["open", "frozen"]  # tests: frozen while a bug fix is written
CONFIDENCE = ["high", "medium", "low"]
PRIORITIES = ["P0", "P1", "P2", "P3"]
READY_STATES = ["yes", "no"]  # ready: yes once the ticket was grilled (What, Why, testable Acceptance settled)
TICKET_FIELDS = ["id", "title", "epic", "milestone", "status", "priority",
                 "depends_on", "owner", "auto", "plan", "ready", "issue", "pr", "tests", "confidence"]
DEFAULT_CONFIG = {
    "flow": "branch-local",
    "host": "none",
    "mirror": "off",
    "merge": "ask",
    "gates": "tdd, checks, review, docs",
    "check": "",
    "milestone": "",
    "tools": "",
    "routines": "work=off audit=off",
    "auto_cap": "1",
}

_YES = {"yes", "true", "on", "1"}


# ---------------------------------------------------------------- frontmatter

def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Return (meta, body). Meta values are strings, or lists for [a, b]."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    meta: dict = {}
    for line in text[4:end].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            continue
        meta[key.strip()] = _parse_value(value.strip())
    return meta, text[end + 5:]


def _parse_value(value: str):
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [v.strip() for v in inner.split(",") if v.strip()] if inner else []
    return value.split("#", 1)[0].strip() if " #" in value else value


def dump_frontmatter(meta: dict, body: str) -> str:
    lines = ["---"]
    for key, value in meta.items():
        if isinstance(value, list):
            lines.append(f"{key}: [{', '.join(value)}]")
        elif value in ("", None):
            lines.append(f"{key}:")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines) + "\n" + body


def truthy(value) -> bool:
    return str(value).strip().lower() in _YES


# ---------------------------------------------------------------- locations

def find_root(start: Path | None = None) -> Path:
    """Git top level if inside a repo, else the start folder."""
    start = Path(start or Path.cwd()).resolve()
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=start,
                             capture_output=True, text=True, check=True).stdout.strip()
        return Path(out)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return start


def pm_dir(root: Path) -> Path:
    return Path(root) / PM_SUBDIR


def has_pm(root: Path) -> bool:
    return (pm_dir(root) / "roadmap.md").exists()


# ---------------------------------------------------------------- models

@dataclass
class Ticket:
    id: str
    title: str = ""
    epic: str = ""
    milestone: str = ""
    status: str = "todo"
    priority: str = "P2"
    depends_on: list = field(default_factory=list)
    owner: str = ""
    auto: bool = False
    plan: str = "none"
    ready: bool = True
    issue: str = ""
    pr: str = ""
    tests: str = "open"
    confidence: str = ""
    path: Path | None = None
    body: str = ""
    meta: dict = field(default_factory=dict)

    @property
    def plan_approved(self) -> bool:
        section = section_text(self.body, "Plan")
        return re.search(r"^approved:\s*(yes|true)\s*$", section, re.M | re.I) is not None

    @property
    def plan_ok(self) -> bool:
        """A routine may take this ticket only when no plan gate is pending."""
        return self.plan != "required" or self.plan_approved

    @property
    def has_proposals(self) -> bool:
        return bool(section_text(self.body, "Proposed changes").strip())


@dataclass
class Epic:
    id: str
    title: str = ""
    milestone: str = ""
    status: str = "todo"
    path: Path | None = None
    body: str = ""
    meta: dict = field(default_factory=dict)


@dataclass
class Milestone:
    id: str
    title: str = ""


def section_text(body: str, heading: str) -> str:
    """Text under `## <heading>` up to the next `## `."""
    pattern = re.compile(rf"^## {re.escape(heading)}\s*$", re.M)
    m = pattern.search(body)
    if not m:
        return ""
    rest = body[m.end():]
    nxt = re.search(r"^## ", rest, re.M)
    return rest[: nxt.start()] if nxt else rest


def replace_section(body: str, heading: str, new_text: str) -> str:
    """Replace the text under `## <heading>`; add the section if missing."""
    block = f"## {heading}\n{new_text.rstrip()}\n\n"
    pattern = re.compile(rf"^## {re.escape(heading)}\s*$", re.M)
    m = pattern.search(body)
    if not m:
        return body.rstrip() + "\n\n" + block
    rest = body[m.end():]
    nxt = re.search(r"^## ", rest, re.M)
    tail = rest[nxt.start():] if nxt else ""
    return body[: m.start()] + block + tail


def _ticket_from(path: Path) -> Ticket:
    meta, body = parse_frontmatter(path.read_text())
    deps = meta.get("depends_on", [])
    if isinstance(deps, str):
        deps = [d.strip() for d in deps.split(",") if d.strip()]
    return Ticket(
        id=str(meta.get("id") or path.stem.split("-")[0]),
        title=str(meta.get("title", "")),
        epic=str(meta.get("epic", "")),
        milestone=str(meta.get("milestone", "")),
        status=str(meta.get("status", "todo")).lower() or "todo",
        priority=str(meta.get("priority", "P2")).upper() or "P2",
        depends_on=list(deps),
        owner=str(meta.get("owner", "")),
        auto=truthy(meta.get("auto", "no")),
        plan=str(meta.get("plan", "none")).lower() or "none",
        ready=truthy(meta.get("ready", "yes")),  # tickets written before the flag existed count as grilled
        issue=str(meta.get("issue", "")),
        pr=str(meta.get("pr", "")),
        tests=str(meta.get("tests", "open")).lower() or "open",
        confidence=str(meta.get("confidence", "")).lower(),
        path=path,
        body=body,
        meta=meta,
    )


def load_tickets(root: Path) -> list[Ticket]:
    folder = pm_dir(root) / "tickets"
    if not folder.exists():
        return []
    return sorted((_ticket_from(p) for p in folder.glob("T*.md")), key=lambda t: t.id)


def load_epics(root: Path) -> list[Epic]:
    folder = pm_dir(root) / "epics"
    if not folder.exists():
        return []
    epics = []
    for p in sorted(folder.glob("E*.md")):
        meta, body = parse_frontmatter(p.read_text())
        epics.append(Epic(
            id=str(meta.get("id") or p.stem.split("-")[0]),
            title=str(meta.get("title", "")),
            milestone=str(meta.get("milestone", "")),
            status=str(meta.get("status", "todo")).lower() or "todo",
            path=p, body=body, meta=meta,
        ))
    return sorted(epics, key=lambda e: e.id)


_MILESTONE_RE = re.compile(r"^## (M\d+)\s*[:\-]?\s*(.*)$", re.M)


def load_milestones(root: Path) -> list[Milestone]:
    path = pm_dir(root) / "roadmap.md"
    if not path.exists():
        return []
    return [Milestone(m.group(1), m.group(2).strip()) for m in _MILESTONE_RE.finditer(path.read_text())]


# ---------------------------------------------------------------- config

def pm_block(root: Path) -> tuple[bool, bool, dict]:
    """(CONTEXT.md exists, `## pm` heading exists, keys found in the block)."""
    path = Path(root) / "CONTEXT.md"
    if not path.exists():
        return False, False, {}
    text = path.read_text()
    m = re.search(r"^## pm\s*$", text, re.M)
    if not m:
        return True, False, {}
    block = text[m.end():]
    nxt = re.search(r"^#{1,2} ", block, re.M)
    if nxt:
        block = block[: nxt.start()]
    found: dict = {}
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith("<!--"):
            continue
        for chunk in re.split(r"\s{2,}(?=[a-z_]+:\s)", line):
            key, sep, value = chunk.partition(":")
            if sep and re.fullmatch(r"[a-z_]+", key.strip()):
                found[key.strip()] = value.strip()
    return True, True, found


def read_config(root: Path) -> dict:
    """The `## pm` block of CONTEXT.md, with defaults filled in and values normalised."""
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(pm_block(root)[2])
    cfg["mirror"] = "on" if truthy(cfg.get("mirror", "off")) else "off"
    cfg["merge"] = "auto" if str(cfg.get("merge", "ask")).strip().lower() == "auto" else "ask"
    for key in ("flow", "host"):
        cfg[key] = str(cfg.get(key, "")).strip().lower()
    return cfg


def milestone_goal(root: Path, milestone_id: str) -> str:
    """The `Goal:` line of a milestone, or its first plain line when the label is missing."""
    path = pm_dir(root) / "roadmap.md"
    if not path.exists():
        return ""
    for chunk in path.read_text().split("\n## ")[1:]:
        head, _, rest = chunk.partition("\n")
        if not head.startswith(milestone_id):
            continue
        fallback = ""
        for line in rest.splitlines():
            line = line.strip()
            if line.startswith("Goal:"):
                return line[len("Goal:"):].strip()
            if line and not fallback and not line.startswith(("Epics:", "Retro:", "-", "#")):
                fallback = line
        return fallback
    return ""


def config_list(cfg: dict, key: str) -> list[str]:
    return [v.strip() for v in cfg.get(key, "").split(",") if v.strip()]


def config_pairs(cfg: dict, key: str) -> dict:
    """`work=off audit=on` -> {"work": "off", "audit": "on"}"""
    out = {}
    for token in cfg.get(key, "").split():
        k, sep, v = token.partition("=")
        if sep:
            out[k] = v
    return out


# ---------------------------------------------------------------- picking

def _priority_rank(p: str) -> int:
    return PRIORITIES.index(p) if p in PRIORITIES else len(PRIORITIES)


def flow_order(tickets: list[Ticket]) -> list[Ticket]:
    """Topological order by depends_on, ties broken by id. Raises on a cycle."""
    by_id = {t.id: t for t in tickets}
    remaining = {t.id for t in tickets}
    done_ids: set[str] = set()
    order: list[Ticket] = []
    while remaining:
        ready = sorted(tid for tid in remaining
                       if all(d in done_ids or d not in by_id for d in by_id[tid].depends_on))
        if not ready:
            raise ValueError("dependency cycle among: " + ", ".join(sorted(remaining)))
        tid = ready[0]
        order.append(by_id[tid])
        done_ids.add(tid)
        remaining.remove(tid)
    return order


def deps_done(t: Ticket, by_id: dict) -> bool:
    return all(d not in by_id or by_id[d].status == "done" for d in t.depends_on)


def ready_tickets(tickets: list[Ticket]) -> list[Ticket]:
    """Tickets /pm:work may take: todo, grilled, nobody's, every dependency done."""
    by_id = {t.id: t for t in tickets}
    return [t for t in tickets if t.status == "todo" and t.ready and not t.owner and deps_done(t, by_id)]


def to_grill(tickets: list[Ticket]) -> list[Ticket]:
    """Tickets waiting for /pm:grill: todo, not grilled, nobody's, not blocked (a blocked ticket is grilled once it is free)."""
    by_id = {t.id: t for t in tickets}
    return [t for t in tickets if t.status == "todo" and not t.ready and not t.owner and deps_done(t, by_id)]


def grilled_early(t: Ticket, by_id: dict) -> bool:
    """Grilled while a dependency is still open: the answers may go stale when that dependency lands."""
    return t.status == "todo" and t.ready and not deps_done(t, by_id)


def pick_next(tickets: list[Ticket], root: Path, routine: bool = False) -> Ticket | None:
    candidates = ready_tickets(tickets)
    if routine:
        candidates = [t for t in candidates if t.auto and t.plan_ok]
    if not candidates:
        return None
    milestone_ids = [m.id for m in load_milestones(root)]
    positions: dict[str, int] = {}
    for epic_id in {t.epic for t in tickets}:
        try:
            for i, t in enumerate(flow_order([t for t in tickets if t.epic == epic_id])):
                positions[t.id] = i
        except ValueError:
            pass

    def key(t: Ticket):
        m_index = milestone_ids.index(t.milestone) if t.milestone in milestone_ids else len(milestone_ids)
        return (_priority_rank(t.priority), m_index, positions.get(t.id, 0), t.id)

    return sorted(candidates, key=key)[0]


# ---------------------------------------------------------------- flow drawing

def render_flow(tickets: list[Ticket]) -> str:
    """Dependency flow of one epic as plain text lines."""
    by_id = {t.id: t for t in tickets}
    try:
        ordered = flow_order(tickets)
    except ValueError as exc:
        return f"(cannot draw: {exc})"
    succ: dict[str, list[str]] = {t.id: [] for t in tickets}
    pred: dict[str, list[str]] = {t.id: [] for t in tickets}
    for t in ordered:
        for d in t.depends_on:
            if d in by_id:
                succ[d].append(t.id)
                pred[t.id].append(d)
    for lst in succ.values():
        lst.sort()
    used: set[tuple[str, str]] = set()
    chains: list[str] = []
    for t in ordered:
        for s in succ[t.id]:
            if (t.id, s) in used:
                continue
            chain = [t.id, s]
            used.add((t.id, s))
            while len(succ[chain[-1]]) == 1 and len(pred[succ[chain[-1]][0]]) == 1:
                nxt = succ[chain[-1]][0]
                used.add((chain[-1], nxt))
                chain.append(nxt)
            chains.append(" -> ".join(chain))
    standalone = [t.id for t in ordered if not succ[t.id] and not pred[t.id]]
    lines = list(chains)
    if standalone:
        lines.append("Standalone: " + ", ".join(standalone))
    ready = [t.id for t in ready_tickets(ordered)]
    grill = [t.id for t in to_grill(ordered)]
    in_progress = [f"{t.id} ({t.owner})" if t.owner else t.id for t in ordered if t.status == "in progress"]
    review = [t.id for t in ordered if t.status == "review"]
    blocked = []
    for t in ordered:
        if t.status == "todo" and not deps_done(t, by_id):
            waits = [d for d in t.depends_on if d in by_id and by_id[d].status != "done"]
            blocked.append(f"{t.id} (waits on {', '.join(waits)})")
    done = [t.id for t in ordered if t.status == "done"]
    lines.append("Ready now: " + (", ".join(ready) or "none"))
    if grill:
        lines.append("To grill: " + ", ".join(grill))
    if in_progress:
        lines.append("In progress: " + ", ".join(in_progress))
    if review:
        lines.append("In review: " + ", ".join(review))
    if blocked:
        lines.append("Blocked: " + ", ".join(blocked))
    if done:
        lines.append("Done: " + ", ".join(done))
    return "\n".join(lines)


def ticket_line(t: Ticket) -> str:
    extra = []
    if t.owner:
        extra.append(t.owner)
    if t.pr:
        extra.append(f"PR #{t.pr}")
    tail = f" ({', '.join(extra)})" if extra else ""
    return f"- {t.id} {t.status} {t.priority} {t.title}{tail}"


def update_epic(root: Path, epic_id: str) -> str:
    """Redraw the Tickets and Flow sections of one epic file. Returns the flow text."""
    epics = {e.id: e for e in load_epics(root)}
    if epic_id not in epics:
        raise KeyError(f"unknown epic {epic_id}")
    epic = epics[epic_id]
    tickets = [t for t in load_tickets(root) if t.epic == epic_id]
    ordered = flow_order(tickets) if tickets else []
    tickets_text = "\n".join(ticket_line(t) for t in ordered) or "(no tickets yet)"
    flow_text = "<!-- drawn by pm flow, do not edit by hand -->\n" + (render_flow(tickets) if tickets else "(no tickets yet)")
    body = replace_section(epic.body, "Tickets", tickets_text)
    body = replace_section(body, "Flow", flow_text)
    epic.path.write_text(dump_frontmatter(epic.meta, body))
    return flow_text


def update_all_epics(root: Path) -> list[str]:
    return [e.id for e in load_epics(root) if update_epic(root, e.id) is not None]


# ---------------------------------------------------------------- board

def _count_done(tickets: list[Ticket]) -> str:
    done = sum(1 for t in tickets if t.status == "done")
    dismissed = sum(1 for t in tickets if t.status == "dismissed")
    text = f"{done}/{len(tickets) - dismissed} done"
    return text + (f", {dismissed} dismissed" if dismissed else "")


def render_board(root: Path) -> str:
    cfg = read_config(root)
    tickets = load_tickets(root)
    epics = load_epics(root)
    milestones = load_milestones(root)
    by_id = {t.id: t for t in tickets}
    current = cfg.get("milestone", "")
    lines = [f"pm board  ({root.name})"]
    known = {m.id for m in milestones}
    for m in milestones + [Milestone("", "no milestone")]:
        m_tickets = [t for t in tickets if (t.milestone == m.id if m.id else t.milestone not in known)]
        m_epics = [e for e in epics if (e.milestone == m.id if m.id else e.milestone not in known)]
        if not m.id and not m_tickets and not m_epics:
            continue
        tag = " (current)" if m.id and m.id == current else ""
        lines.append("")
        lines.append(f"{m.id + ': ' if m.id else ''}{m.title}{tag} {_count_done(m_tickets)}")
        for e in m_epics:
            e_tickets = [t for t in tickets if t.epic == e.id]
            lines.append(f"  {e.id} {e.title}  {_count_done(e_tickets)}")
            try:
                ordered = flow_order(e_tickets)
            except ValueError:
                ordered = e_tickets
            for t in ordered:
                notes = []
                if t.owner:
                    notes.append(f"owner: {t.owner}")
                if t.pr:
                    notes.append(f"PR #{t.pr}")
                if t.status == "todo" and not deps_done(t, by_id):
                    waits = [d for d in t.depends_on if d in by_id and by_id[d].status != "done"]
                    notes.append("blocked by " + ", ".join(waits))
                if t.status == "todo" and not t.ready:
                    notes.append("not grilled")
                if grilled_early(t, by_id):
                    notes.append("grilled early: re-check with /pm:grill when free")
                if t.has_proposals:
                    notes.append("proposed changes waiting")
                if t.confidence:
                    notes.append(f"confidence: {t.confidence}")
                tail = ("  " + "  ".join(notes)) if notes else ""
                lines.append(f"    {t.id} {t.status} {t.priority} {t.title}{tail}")
        orphans = [t for t in m_tickets if t.epic not in {e.id for e in m_epics}]
        for t in orphans:
            lines.append(f"    {t.id} {t.status} {t.priority} {t.title}  (epic {t.epic or 'missing'})")
    ready = [t.id for t in ready_tickets(tickets)]
    lines.append("")
    lines.append("Ready now: " + (", ".join(ready) or "none"))
    grill = [t.id for t in to_grill(tickets)]
    if grill:
        lines.append("To grill: " + ", ".join(grill) + "  (/pm:grill Txxx)")
    proposals = [t.id for t in tickets if t.has_proposals]
    if proposals:
        lines.append("Proposed changes waiting: " + ", ".join(proposals))
    backlog = _backlog_count(root)
    lines.append(f"Backlog: {backlog} item{'s' if backlog != 1 else ''}")
    return "\n".join(lines)


def _backlog_count(root: Path) -> int:
    path = pm_dir(root) / "roadmap.md"
    if not path.exists():
        return 0
    text = section_text(parse_frontmatter(path.read_text())[1], "Backlog")
    return sum(1 for line in text.splitlines() if line.strip().startswith("- "))


def board_line(root: Path) -> str:
    root = Path(root)
    if not has_pm(root):
        return ""
    cfg = read_config(root)
    tickets = load_tickets(root)
    current = cfg.get("milestone", "") or (load_milestones(root)[0].id if load_milestones(root) else "")
    m_tickets = [t for t in tickets if t.milestone == current]
    parts = [f"pm: {current} {_count_done(m_tickets)}" if current else f"pm: {_count_done(tickets)}"]
    in_progress = [f"{t.id} ({t.owner})" if t.owner else t.id for t in tickets if t.status == "in progress"]
    if in_progress:
        parts.append("in progress: " + ", ".join(in_progress))
    review = [t.id for t in tickets if t.status == "review"]
    if review:
        parts.append("review: " + ", ".join(review))
    ready = [t.id for t in ready_tickets(tickets)]
    parts.append("ready: " + (", ".join(ready) or "none"))
    grill = [t.id for t in to_grill(tickets)]
    if grill:
        parts.append("to grill: " + ", ".join(grill))
    return " | ".join(parts)


# ---------------------------------------------------------------- editing

def open_deps(t: Ticket, by_id: dict) -> list[str]:
    return [d for d in t.depends_on if d in by_id and by_id[d].status != "done"]


def set_fields(root: Path, ticket_id: str, early: bool = False, **fields) -> Ticket:
    """Change frontmatter fields. `ready=yes` on a blocked ticket needs early=True (a grill on the user's word)."""
    tickets = {t.id: t for t in load_tickets(root)}
    if ticket_id not in tickets:
        raise KeyError(f"unknown ticket {ticket_id}")
    t = tickets[ticket_id]
    meta = dict(t.meta)
    if truthy(fields.get("ready", "no")) and not t.ready and not early and open_deps(t, tickets):
        waits = ", ".join(open_deps(t, tickets))
        raise ValueError(f"{t.id} waits on {waits}: grill it once that is done, or `pm.py ready {t.id} --early` when the user, told it is blocked, said to go on")
    for key, value in fields.items():
        if key == "status" and value not in STATUSES:
            raise ValueError(f"status must be one of {', '.join(STATUSES)}")
        if key == "priority" and value not in PRIORITIES:
            raise ValueError(f"priority must be one of {', '.join(PRIORITIES)}")
        if key == "depends_on" and isinstance(value, str):
            value = [v.strip() for v in value.strip("[]").split(",") if v.strip()]
        if key == "tests" and value not in TESTS_STATES:
            raise ValueError(f"tests must be one of {', '.join(TESTS_STATES)}")
        if key == "confidence" and value not in CONFIDENCE + [""]:
            raise ValueError(f"confidence must be one of {', '.join(CONFIDENCE)}")
        if key == "ready" and str(value).lower() not in READY_STATES:
            raise ValueError("ready must be yes or no")
        meta[key] = value
    if meta.get("status") in CLOSED and "tests" in meta:
        meta["tests"] = "open"  # the freeze ends with the ticket
    if meta.get("status") == "dismissed":
        meta["owner"] = ""
    t.path.write_text(dump_frontmatter(meta, t.body))
    return _ticket_from(t.path)


def add_note(root: Path, ticket_id: str, line: str) -> Ticket:
    """Append one line under the ticket's `## Notes`."""
    tickets = {t.id: t for t in load_tickets(root)}
    if ticket_id not in tickets:
        raise KeyError(f"unknown ticket {ticket_id}")
    t = tickets[ticket_id]
    notes = section_text(t.body, "Notes").strip()
    body = replace_section(t.body, "Notes", (notes + "\n" if notes else "") + line.strip())
    t.path.write_text(dump_frontmatter(dict(t.meta), body))
    return _ticket_from(t.path)


def next_id(root: Path, kind: str) -> str:
    if kind == "ticket":
        ids = [int(t.id[1:]) for t in load_tickets(root) if t.id[1:].isdigit()]
        return f"T{(max(ids) + 1 if ids else 1):03d}"
    if kind == "epic":
        ids = [int(e.id[1:]) for e in load_epics(root) if e.id[1:].isdigit()]
        return f"E{(max(ids) + 1 if ids else 1):02d}"
    if kind == "milestone":
        ids = [int(m.id[1:]) for m in load_milestones(root) if m.id[1:].isdigit()]
        return f"M{(max(ids) + 1 if ids else 1)}"
    raise ValueError("kind must be ticket, epic or milestone")


def slug(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s[:48].rstrip("-") or "untitled"


def ticket_path(root: Path, ticket_id: str, title: str) -> Path:
    return pm_dir(root) / "tickets" / f"{ticket_id}-{slug(title)}.md"


def epic_path(root: Path, epic_id: str, title: str) -> Path:
    return pm_dir(root) / "epics" / f"{epic_id}-{slug(title)}.md"


# ---------------------------------------------------------------- validation

_PLACEHOLDER = re.compile(r"^\(?\s*(fill in|one testable line per item|first step|none yet|nothing yet|no tickets yet|will be redrawn)\s*\)?\.?$", re.I)


def section_filled(body: str, heading: str) -> bool:
    """True when the section has real text, not just template placeholders."""
    for line in section_text(body, heading).splitlines():
        line = re.sub(r"^\s*-\s*\[[ xX]\]\s*", "", line).strip()
        line = re.sub(r"^\s*-\s*", "", line).strip()
        if line and not _PLACEHOLDER.match(line):
            return True
    return False


def validate(root: Path) -> list[str]:
    problems: list[str] = []
    has_ctx, has_heading, keys = pm_block(root)
    if not has_ctx:
        problems.append("CONTEXT.md: missing, so the pm block is missing (run /pm:init)")
    elif not has_heading:
        problems.append("CONTEXT.md: no `## pm` block (run /pm:init)")
    elif "flow" not in keys:
        problems.append("CONTEXT.md: pm block has no `flow:` line; the block must be plain `key: value` lines, one per line")
    tickets = load_tickets(root)
    epics = {e.id for e in load_epics(root)}
    milestones = {m.id for m in load_milestones(root)}
    by_id: dict[str, Ticket] = {}
    for t in tickets:
        if t.id in by_id:
            problems.append(f"{t.id}: duplicate id ({t.path.name} and {by_id[t.id].path.name})")
        by_id[t.id] = t
    for t in tickets:
        if t.status not in STATUSES:
            problems.append(f"{t.id}: unknown status '{t.status}'")
        if t.priority not in PRIORITIES:
            problems.append(f"{t.id}: unknown priority '{t.priority}'")
        if t.epic and t.epic not in epics:
            problems.append(f"{t.id}: unknown epic {t.epic}")
        if not t.epic:
            problems.append(f"{t.id}: no epic")
        if t.milestone and t.milestone not in milestones:
            problems.append(f"{t.id}: unknown milestone {t.milestone}")
        if t.tests not in TESTS_STATES:
            problems.append(f"{t.id}: tests must be open or frozen, not '{t.tests}'")
        if t.confidence and t.confidence not in CONFIDENCE:
            problems.append(f"{t.id}: confidence must be high, medium, or low, not '{t.confidence}'")
        if "ready" in t.meta and str(t.meta["ready"]).lower() not in READY_STATES:
            problems.append(f"{t.id}: ready must be yes or no, not '{t.meta['ready']}'")
        for d in t.depends_on:
            if d not in by_id:
                problems.append(f"{t.id}: depends on unknown ticket {d}")
            elif d == t.id:
                problems.append(f"{t.id}: depends on itself")
            elif by_id[d].status == "dismissed" and t.status not in CLOSED:
                problems.append(f"{t.id}: depends on dismissed {d}; drop the dependency or dismiss {t.id} too")
        for heading in ("What", "Acceptance"):
            if not section_filled(t.body, heading):
                problems.append(f"{t.id}: {heading} section is empty")
        for heading in ("Why", "Subtasks"):
            if re.search(r"\(\s*fill in\s*\)", section_text(t.body, heading), re.I):
                problems.append(f"{t.id}: placeholder left in {heading}; write the line or remove it")
        if t.owner and t.status == "todo":
            problems.append(f"{t.id}: owner set but status is todo")
        if t.status == "in progress" and not t.owner:
            problems.append(f"{t.id}: in progress but no owner")
    for epic_id in sorted({t.epic for t in tickets}):
        try:
            flow_order([t for t in tickets if t.epic == epic_id])
        except ValueError as exc:
            problems.append(f"{epic_id}: {exc}")
    for e in load_epics(root):
        if e.milestone and e.milestone not in milestones:
            problems.append(f"{e.id}: unknown milestone {e.milestone}")
    return problems
