"""ICM structure checks behind `pm.py walk`, `pm.py index`, and `pm.py refs`.

The rules are adapted from icm-architect (MIT, (c) 2026 Jake Van Clief); see icm/LICENSE and icm/method.md.
Everything here only reads the repository, except write_index, which rewrites the generated card index.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

MAP = "docs/pm/map"
ENTRY_LINES = 60
CONTEXT_LINES = 80
TOKEN_BUDGET = 8000
CONTRACT_SECTIONS = ("Inputs", "Process", "Outputs", "Verify", "Human check")
CARD_SECTIONS = {
    "object": ("Why this shape", "Shape", "Connected to", "If you change this", "Surfaces", "See"),
    "process": ("Input → Movement → Output", "Why this shape", "Steps", "If you change this", "Surfaces", "See"),
}
STATUSES = ("stub", "verified", "stale")
UNIVERSES = ("live", "leftover", "ghost")
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", "target", ".pytest_cache"}
TEMPLATES = Path(__file__).resolve().parents[1] / "icm" / "templates"
LINK = re.compile(r"\[[^\]\n]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
CITATION = re.compile(r"`((?:[^`\s:]+/)+[^`\s:]+|[^`\s:/]+\.[A-Za-z]\w*):(\d+)(?:-(\d+))?`")
STAGE_DIR = re.compile(r"^\d{2}[_-]")
SKILL_ROOTS = (".claude/skills", "skills")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")


def repo_files(root: Path) -> list[str]:
    """Tracked and untracked, not ignored, files that exist, as repo-relative POSIX paths."""
    result = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                            capture_output=True)
    if result.returncode == 0:
        names = sorted({name for name in result.stdout.decode("utf-8", "replace").split("\0") if name})
        return [name for name in names if (root / name).exists() or (root / name).is_symlink()]
    found = []
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        found.extend((Path(folder) / name).relative_to(root).as_posix() for name in files)
    return sorted(found)


def frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = re.match(r"\A---\n(.*?)\n---\n?(.*)\Z", text, re.S)
    if not match:
        return {}, text
    meta, last = {}, None
    for line in match.group(1).splitlines():
        key, sep, value = line.partition(":")
        if line[:1] in (" ", "\t") and last:
            meta[last] = f"{meta[last]} {line.strip()}".strip()
        elif sep and re.fullmatch(r"[A-Za-z_-]+", key.strip()):
            last = key.strip()
            meta[last] = re.sub(r"\s+#.*$", "", value).strip()
    return meta, match.group(2)


def headings(text: str) -> dict[str, str]:
    """Each `## ` heading (normalised) mapped to the text under it."""
    sections, name = {}, None
    for line in text.splitlines():
        if line.startswith("## "):
            name = line[3:].strip().replace("->", "→").casefold()
            sections[name] = ""
        elif name is not None:
            sections[name] += line + "\n"
    return sections


def title_and_sentence(body: str, fallback: str) -> tuple[str, str]:
    title, sentence = fallback, ""
    lines = body.splitlines()
    for number, line in enumerate(lines):
        if line.startswith("# "):
            title = line[2:].strip()
            sentence = next((rest.strip() for rest in lines[number + 1:] if rest.strip()), "")
            break
    if sentence.startswith("#"):
        sentence = ""
    return title, sentence if len(sentence) <= 120 else sentence[:119] + "…"


def link_targets(path: Path, root: Path, text: str) -> list[tuple[int, str, Path]]:
    """Relative links in text, resolved against the file's folder (a leading / means the repo root)."""
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        targets = [m.group(1) for m in LINK.finditer(line)]
        if re.match(r"^@\S+$", line.strip()):
            targets.append(line.strip()[1:])
        for raw in targets:
            if re.match(r"^[a-z][a-z0-9+.-]*:", raw, re.I) or raw.startswith("#") or "{" in raw:
                continue
            target = unquote(raw.split("#", 1)[0].split("?", 1)[0])
            if not target:
                continue
            base = root if target.startswith("/") else path.parent
            found.append((number, raw, (base / target.lstrip("/")).resolve()))
    return found


def template_lines() -> set[str]:
    """Lines of the card templates that still hold a placeholder; one in a card means the copy was not filled in."""
    lines = set()
    for name in ("object.md", "process.md"):
        template = TEMPLATES / name
        if template.exists():
            lines.update(line.strip() for line in read(template).splitlines() if "{" in line and line.strip())
    return lines


def card_paths(root: Path) -> list[Path]:
    paths = []
    for shelf in ("objects", "processes"):
        folder = root / MAP / shelf
        if folder.is_dir():
            paths.extend(p for p in sorted(folder.rglob("*.md")) if not p.name.startswith("_") and p.name != "CONTEXT.md")
    return paths


def read_cards(root: Path) -> list[dict]:
    cards = []
    for path in card_paths(root):
        text = read(path)
        meta, body = frontmatter(text)
        rel = path.relative_to(root / MAP).as_posix()
        title, sentence = title_and_sentence(body, path.stem)
        parts = PurePosixPath(rel).parts
        cluster = parts[1] if parts[0] == "objects" and len(parts) > 2 else ""
        cards.append({"path": path, "rel": rel, "meta": meta, "body": body, "text": text,
                      "title": title, "sentence": sentence, "shelf": parts[0], "cluster": cluster})
    return cards


def render_index(root: Path) -> str:
    cards = read_cards(root)
    counts = {status: sum(card["meta"].get("status") == status for card in cards) for status in STATUSES}
    lines = ["# Card index", "",
             "Generated by `pm.py index` from each card's frontmatter. Do not edit by hand; "
             "run `pm.py index` after adding a card or changing its status.", "",
             f"{len(cards)} card{'s' if len(cards) != 1 else ''}: " + ", ".join(f"{counts[s]} {s}" for s in STATUSES) + ".", ""]

    def line(card: dict) -> str:
        meta = card["meta"]
        labels = " · ".join(value for value in (meta.get("status") or "no status", meta.get("universe", "")) if value)
        tail = f" — {card['sentence']}" if card["sentence"] else ""
        return f"- [{card['title']}]({card['rel']}) — {labels}{tail}"

    objects = [card for card in cards if card["shelf"] == "objects"]
    if objects:
        lines.extend(("## Objects", ""))
        for cluster in sorted({card["cluster"] for card in objects}):
            lines.extend((f"### {cluster or 'other'}", ""))
            lines.extend(line(card) for card in objects if card["cluster"] == cluster)
            lines.append("")
    processes = [card for card in cards if card["shelf"] == "processes"]
    if processes:
        lines.extend(("## Processes", ""))
        lines.extend(line(card) for card in processes)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_index(root: Path) -> str:
    if not (root / MAP).is_dir():
        raise ValueError(f"No System map in {MAP}/ yet. Build one with /pm:map.")
    text = render_index(root)
    (root / MAP / "_index.md").write_text(text, encoding="utf-8")
    summary = next(line for line in text.splitlines() if re.match(r"^\d+ cards?: ", line))
    return f"Wrote {MAP}/_index.md: {summary}"


def tokens(text: str) -> int:
    return (len(text) + 3) // 4


def is_pointer(text: str) -> bool:
    return text.strip() == "@AGENTS.md"


def check_entry_pair(root: Path, folder: str, add) -> None:
    """At most one hand-maintained entry file per folder: CLAUDE.md is `@AGENTS.md` or identical to it."""
    claude, agents = root / folder / "CLAUDE.md", root / folder / "AGENTS.md"
    if claude.is_file() and agents.is_file():
        claude_text, agents_text = read(claude), read(agents)
        if not is_pointer(claude_text) and claude_text != agents_text:
            label = f"{folder}/" if folder != "." else ""
            add("FAIL", f"{label}CLAUDE.md and {label}AGENTS.md are two hand-maintained entry files. "
                        f"Keep the content in {label}AGENTS.md and make {label}CLAUDE.md the one line `@AGENTS.md`.")


def walk(root: Path, items: list[dict]) -> list[tuple[str, str]]:
    """The mechanical half of the ICM walk test. Returns (level, message) pairs; level is FAIL, WARN, or ok."""
    results: list[tuple[str, str]] = []
    add = lambda level, message: results.append((level, message))
    files = repo_files(root)
    has_map = (root / MAP).is_dir()

    entry = next((root / name for name in ("AGENTS.md", "CLAUDE.md") if (root / name).is_file()), None)
    entry_text = read(entry) if entry else ""
    if entry and entry.name == "CLAUDE.md" and is_pointer(entry_text):
        entry, entry_text = None, ""
    if not entry:
        add("FAIL", "No entry file: add AGENTS.md as the catalog (where things live, where to go for a task) "
                    "and CLAUDE.md with the one line `@AGENTS.md`.")
    else:
        count = len(entry_text.splitlines())
        if count > ENTRY_LINES:
            add("FAIL", f"{entry.name} has {count} lines; the entry file is a catalog and stays under {ENTRY_LINES}. "
                        "Move content to the shelf that owns it (docs/placement.md) and leave a link.")
        else:
            add("ok", f"{entry.name} is a small catalog ({count} lines).")
    folders = sorted({str(PurePosixPath(name).parent) for name in files if PurePosixPath(name).name in ("CLAUDE.md", "AGENTS.md")})
    for folder in folders:
        check_entry_pair(root, folder, add)

    routing = [name for name in files if PurePosixPath(name).name in ("AGENTS.md", "CLAUDE.md", "CONTEXT.md")
               or (name.startswith(MAP + "/") and name.endswith(".md") and "/_templates/" not in name)]
    broken = []
    for name in routing:
        path = root / name
        for number, raw, target in link_targets(path, root, read(path)):
            if not target.exists():
                broken.append(f"{name}:{number} -> {raw}")
    if broken:
        add("FAIL", "Links that do not resolve (a moved file that something still points at is a break): "
                    + "; ".join(broken[:12]) + (f"; and {len(broken) - 12} more" if len(broken) > 12 else ""))
    elif routing:
        add("ok", f"Every link in the {len(routing)} routing file{'s' if len(routing) != 1 else ''} and cards resolves.")

    contracts = [name for name in files if PurePosixPath(name).name == "CONTEXT.md"]
    for name in contracts:
        text = read(root / name)
        count = len(text.splitlines())
        if count > CONTEXT_LINES:
            add("FAIL", f"{name} has {count} lines; a CONTEXT.md routes and stays under {CONTEXT_LINES}. "
                        "Move the content into a reference file it points at.")
        folder = PurePosixPath(name).parent
        if STAGE_DIR.match(folder.name) or name == f"{MAP}/CONTEXT.md":
            missing = [s for s in CONTRACT_SECTIONS if s.casefold() not in headings(text)]
            if missing:
                add("FAIL", f"{name} is a working folder's contract but lacks: " + ", ".join(f"## {s}" for s in missing) + ".")
        elif not LINK.search(text) and not re.search(r"`[^`\n]*[/.][^`\n]*`", text) and "inputs" not in headings(text):
            add("WARN", f"{name} points at nothing. A CONTEXT.md is a folder's contract or router, never a glossary "
                        f"or overview; move vocabulary to the Names table in {MAP}/AGENTS.md (docs/placement.md).")

    workflows = workflow_skills(root, files)
    for skill in workflows:
        walk_workflow(root, skill, add)
    if has_map:
        walk_map(root, entry_text, add)
    if (root / "docs/pm/CODEBASE.md").is_file():
        add("WARN", f"docs/pm/CODEBASE.md is a second home for architecture next to {MAP}/. Once its facts are on cards, "
                    "retire it (check pm.py refs first)." if has_map else
                    f"docs/pm/CODEBASE.md is not a System map yet; /pm:map turns it into {MAP}/ and retires it.")

    for item in items:
        missing = [path for path in item.get("touches", []) if not (root / path).exists()]
        if missing:
            add("FAIL", f"Item {item['id']} touches paths that do not exist: {', '.join(missing)}. "
                        f"Fix them with pm.py set {item['id']} --touches.")

    if not entry:
        return results
    budget = [("entry", entry_text)]
    if workflows:
        budget.append(("workflow SKILL.md", max((read(root / skill / "SKILL.md") for skill in workflows), key=len)))
    elif has_map and (root / MAP / "AGENTS.md").is_file():
        budget.append(("map catalog", read(root / MAP / "AGENTS.md")))
    elif (root / "CONTEXT.md").is_file():
        budget.append(("root contract", read(root / "CONTEXT.md")))
    shelves = [read(card["path"]) for card in read_cards(root)] + [read(root / n) for n in contracts if n != "CONTEXT.md"]
    if shelves:
        budget.append(("largest card or contract", max(shelves, key=len)))
    total = sum(tokens(text) for _, text in budget)
    detail = " + ".join(name for name, _ in budget)
    if total > TOKEN_BUDGET:
        add("FAIL", f"{detail} is about {total:,} tokens; one walk should stay under {TOKEN_BUDGET:,}. "
                    "Split the largest file or tighten what the entry file carries.")
    else:
        add("ok", f"{detail}: about {total:,} tokens (under {TOKEN_BUDGET:,}).")
    return results


def workflow_skills(root: Path, files: list[str]) -> list[str]:
    """Skill folders that hold an ICM workflow: a SKILL.md with numbered stage folders under stages/."""
    found = set()
    for name in files:
        parts = PurePosixPath(name).parts
        for base in SKILL_ROOTS:
            depth = len(PurePosixPath(base).parts)
            if tuple(parts[:depth]) == PurePosixPath(base).parts and len(parts) > depth + 2 and parts[depth + 1] == "stages":
                skill = "/".join(parts[:depth + 1])
                if (root / skill / "SKILL.md").is_file():
                    found.add(skill)
    return sorted(found)


def walk_workflow(root: Path, skill: str, add) -> None:
    """A workflow is built to be packaged as a Claude skill: self-contained, with its runs kept outside it."""
    folder = root / skill
    text = read(folder / "SKILL.md")
    meta, _ = frontmatter(text)
    name = PurePosixPath(skill).name
    problems = []
    if meta.get("name", "").strip("\"'") != name:
        problems.append(f"SKILL.md needs `name: {name}` in its frontmatter")
    if "Use when" not in meta.get("description", ""):
        problems.append("SKILL.md needs a description with a 'Use when' clause; it is what tells Claude to run the workflow")
    count = len(text.splitlines())
    if count > ENTRY_LINES:
        problems.append(f"SKILL.md has {count} lines; it routes to the stages and stays under {ENTRY_LINES}, "
                        "so stage detail belongs in that stage's CONTEXT.md")
    stages = sorted(p for p in (folder / "stages").iterdir() if p.is_dir())
    for stage in stages:
        if not STAGE_DIR.match(stage.name):
            problems.append(f"stages/{stage.name}/ is not numbered: name stages NN_name so the folder order is the run order")
        elif not (stage / "CONTEXT.md").is_file():
            problems.append(f"stages/{stage.name}/ has no CONTEXT.md contract")
    for path in sorted(p for p in folder.rglob("*.md") if p.is_file()):
        for number, raw, target in link_targets(path, root, read(path)):
            if not target.exists():
                problems.append(f"{path.relative_to(folder).as_posix()}:{number} links to {raw}, which does not exist")
            elif target != folder.resolve() and folder.resolve() not in target.parents:
                problems.append(f"{path.relative_to(folder).as_posix()}:{number} links outside the skill ({raw}), "
                                "which breaks once it is packaged")
    outputs = sorted({p.parent.relative_to(folder).as_posix() for p in folder.rglob("*")
                      if p.is_file() and "output" in p.relative_to(folder).parts})
    if outputs:
        problems.append(f"run output inside the skill ({', '.join(outputs[:4])}) would ship with it; write each run to runs/<run>/")
    if problems:
        add("FAIL", f"Workflow {skill}/: " + "; ".join(problems[:10]) + ".")
    else:
        add("ok", f"Workflow {skill}/ has {len(stages)} numbered stage{'s' if len(stages) != 1 else ''} and is packageable as a skill.")


def walk_map(root: Path, entry_text: str, add) -> None:
    catalog = root / MAP / "AGENTS.md"
    if not re.search(r"(?<![\w/])/?docs/pm/map\b", entry_text):
        add("FAIL", f"The entry file does not route to the System map: add a row pointing at {MAP}/AGENTS.md.")
    if not catalog.is_file():
        add("FAIL", f"{MAP}/AGENTS.md is missing: the map needs its own small catalog (names, clusters, where to go).")
        catalog_text = ""
    else:
        catalog_text = read(catalog)
        count = len(catalog_text.splitlines())
        if count > ENTRY_LINES:
            add("FAIL", f"{MAP}/AGENTS.md has {count} lines; the map catalog stays under {ENTRY_LINES}. Move detail onto cards.")
        if "_index.md" not in catalog_text:
            add("FAIL", f"{MAP}/AGENTS.md does not link _index.md, so a cold agent cannot reach the cards.")
        if (root / MAP / "effects").is_dir() and "effects/CONTEXT.md" not in catalog_text:
            add("FAIL", f"{MAP}/AGENTS.md does not link effects/CONTEXT.md, the change-impact index.")
    if not (root / MAP / "CONTEXT.md").is_file():
        add("FAIL", f"{MAP}/CONTEXT.md is missing: the map's contract (inputs, process, outputs, verify, human check).")
    for shelf in ("objects", "processes", "effects"):
        folder = root / MAP / shelf
        if folder.is_dir() and not any(p.is_file() for p in folder.rglob("*")):
            add("FAIL", f"{MAP}/{shelf}/ is empty. Remove it until it has real content.")
    if (root / MAP / "effects").is_dir() and not (root / MAP / "effects" / "CONTEXT.md").is_file():
        add("FAIL", f"{MAP}/effects/ needs a CONTEXT.md: if you change X, open these cards.")

    cards = read_cards(root)
    if not cards:
        add("FAIL", f"{MAP}/ has no cards. Write a stub card for every noun (copy _templates/object.md), then pm.py index.")
        return
    if len(cards) > 1 and not (root / MAP / "effects" / "CONTEXT.md").is_file():
        add("FAIL", f"{MAP}/ has {len(cards)} cards but no effects/CONTEXT.md, the change-impact index "
                    "(if you change X, open these cards). Write it and link it from the map's AGENTS.md.")
    placeholders = template_lines()
    problems = []
    for card in cards:
        meta, rel = card["meta"], card["rel"]
        kind = meta.get("type", "")
        expected = "object" if card["shelf"] == "objects" else "process"
        status = meta.get("status", "")
        if kind != expected:
            problems.append(f"{rel}: type is {kind or 'missing'}, expected {expected}")
        if status not in STATUSES:
            problems.append(f"{rel}: status is {status or 'missing'}, expected one of {', '.join(STATUSES)}")
        if expected == "object" and meta.get("universe", "") not in UNIVERSES:
            problems.append(f"{rel}: universe is {meta.get('universe') or 'missing'}, expected one of {', '.join(UNIVERSES)}")
        unfilled = [line for line in card["text"].splitlines() if line.strip() in placeholders]
        if unfilled:
            problems.append(f"{rel}: template line not filled in: {unfilled[0].strip()}")
        citations = [(m.group(1), int(m.group(2)), int(m.group(3) or m.group(2))) for m in CITATION.finditer(card["body"])]
        bad = []
        for path, start, end in citations:
            target = root / path
            if not target.is_file():
                bad.append(f"{path} does not exist")
            elif end > len(read(target).splitlines()) or start < 1:
                bad.append(f"{path}:{start} is past the end of the file")
        if status == "verified":
            sections = headings(card["body"])
            missing = [s for s in CARD_SECTIONS[expected] if s.casefold() not in sections]
            if missing:
                problems.append(f"{rel}: verified card lacks " + ", ".join(f"## {s}" for s in missing))
            impact = sections.get("if you change this", "")
            if "Hits" not in impact or "Does not hit" not in impact:
                problems.append(f"{rel}: 'If you change this' needs both Hits and Does not hit")
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", meta.get("verified", "")) or not meta.get("commit"):
                problems.append(f"{rel}: verified needs `verified: YYYY-MM-DD` and `commit:` in frontmatter")
            if not citations:
                problems.append(f"{rel}: verified card cites no source (`path:line`)")
            problems.extend(f"{rel}: {message}" for message in bad)
        elif bad:
            add("WARN", f"{rel} ({status}) cites missing source: " + "; ".join(bad))
    if problems:
        add("FAIL", "Cards: " + "; ".join(problems[:12]) + (f"; and {len(problems) - 12} more" if len(problems) > 12 else ""))
    else:
        add("ok", "1 card has its frontmatter, sections, and citations." if len(cards) == 1
            else f"{len(cards)} cards have their frontmatter, sections, and citations.")
    index = root / MAP / "_index.md"
    if not index.is_file() or read(index) != render_index(root):
        add("FAIL", f"{MAP}/_index.md is missing or out of date. Run pm.py index; never edit it by hand.")


def render_walk(results: list[tuple[str, str]]) -> str:
    fails = sum(level == "FAIL" for level, _ in results)
    warns = sum(level == "WARN" for level, _ in results)
    passed = sum(level == "ok" for level, _ in results)
    head = "Walk test: " + ("passed" if not fails else f"{fails} to fix") + f" ({passed} ok, {warns} warning{'s' if warns != 1 else ''})."
    order = {"FAIL": 0, "WARN": 1, "ok": 2}
    lines = [head] + [f"{level:<4}  {message}" for level, message in sorted(results, key=lambda r: order[r[0]])]
    lines.append("These are the mechanical checks. Then walk it cold with the questions in the pm plugin's icm/method.md.")
    return "\n".join(lines)


def all_paths(files: list[str]) -> set[str]:
    paths = set(files)
    for name in files:
        parts = PurePosixPath(name).parts
        paths.update("/".join(parts[:i]) for i in range(1, len(parts)))
    return paths


def refs(root: Path, pairs: list[tuple[str, str]]) -> tuple[str, int]:
    """What points at each path before a move, and whether its destination is free (case-folded)."""
    files = repo_files(root)
    existing = all_paths(files)
    texts = {}
    for name in files:
        path = root / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1_000_000:
            continue
        try:
            texts[name] = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        except (UnicodeDecodeError, OSError):
            continue
    out, collisions = [], 0
    for old, new in pairs:
        old_path = (root / old).resolve()
        if not old_path.exists():
            raise ValueError(f"{old} does not exist.")
        inside = lambda target: target == old_path or old_path in target.parents
        found, names = [], []
        by_path = re.compile(rf"(?<![\w.-]){re.escape(old)}(?![\w-])")
        by_name = re.compile(rf"(?<![\w.-]){re.escape(PurePosixPath(old).name)}(?![\w-])")
        for name, text in texts.items():
            if inside((root / name).resolve()):
                continue
            links = {number for number, _, target in link_targets(root / name, root, text) if inside(target)}
            for number, line in enumerate(text.splitlines(), 1):
                if number in links:
                    found.append(f"{name}:{number} (link)")
                elif by_path.search(line):
                    found.append(f"{name}:{number} (path)")
                elif by_name.search(line):
                    names.append(f"{name}:{number}")
        for name in files:
            path = root / name
            if path.is_symlink() and inside((path.parent / os.readlink(path)).resolve()):
                found.append(f"{name} (symlink)")
        out.append(f"{old}" + (f" -> {new}" if new else ""))
        out.append("  points at it: " + (", ".join(found) if found else "nothing in this repository"))
        if names:
            out.append("  names it without a path (check by hand): " + ", ".join(names[:20])
                       + (f", and {len(names) - 20} more" if len(names) > 20 else ""))
        if new:
            clash = sorted(p for p in existing if p.casefold() == new.casefold() and p != old)
            if clash:
                collisions += 1
                out.append(f"  destination is taken: {', '.join(clash)} (compared case-folded, as macOS and Windows do)")
            else:
                out.append("  destination is free (compared case-folded)")
    out.append("Outside this repository (other repos, CI, cron, agent configs) nothing is visible from here: ask the owner.")
    return "\n".join(out), collisions
