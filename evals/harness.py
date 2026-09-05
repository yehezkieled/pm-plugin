"""Evals: runs pm plugin scenarios against one model in fresh headless sessions and grades the outcome.

usage: python3 evals/harness.py [--out DIR] <model> [scenario ...]
Writes evals/results/<out>/<model>/<scenario>/{out.jsonl,summary.json}   (default out = headless)
A scenario = a throwaway repo, a plain-English prompt, the model with the plugin loaded, and a set of checks.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent  # evals/ lives inside the plugin
RESULTS = HERE / "results"  # ignored by git
sys.path.insert(0, str(PLUGIN / "tests"))
from fixtures import make_repo  # noqa: E402

BANNED = re.compile(r"\b(deadlines?|due dates?|target dates?|eta|estimat(e|es|ed|ion)|velocity|story points?|on track|behind schedule|sprints?|days? left|burndown)\b", re.I)

ENV_STRIP = ["CLAUDECODE", "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_MESSAGING_SOCKET",
             "CLAUDE_CODE_MESSAGING_TOKEN", "CLAUDE_CODE_BRIDGE_SESSION_ID", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_PID"]

NOPY_BIN = RESULTS / "bin" / "nopy"   # a PATH without python3, built on first use
FORK_BIN = RESULTS / "bin" / "fork"   # a gh shim that says "this repo is a fork", built on first use


def ensure_bins():
    if not NOPY_BIN.exists():
        NOPY_BIN.mkdir(parents=True)
        for d in os.environ.get("PATH", "").split(os.pathsep):
            for exe in (Path(d).glob("*") if Path(d).is_dir() else []):
                if exe.name.startswith("python") or (NOPY_BIN / exe.name).exists():
                    continue
                (NOPY_BIN / exe.name).symlink_to(exe)
    if not FORK_BIN.exists():
        FORK_BIN.mkdir(parents=True)
        gh = FORK_BIN / "gh"
        gh.write_text('#!/bin/bash\n# eval shim: pretends this repo is a fork; refuses everything else\ncase "$1 $2" in\n  "auth status") exit 0 ;;\n  "repo view") echo true; exit 0 ;;\nesac\necho "gh shim: refusing \'$*\'" >&2; exit 1\n')
        gh.chmod(0o755)

CALC = '''"""Tiny calculator module."""


def add(a, b):
    return a + b


def divide(a, b):
    return a / b


def parse_amount(text):
    try:
        return float(text.replace(",", ""))
    except Exception:
        return 0


def average(values):
    total = 0
    for v in values:
        total = total + v
    return total / len(values)
'''

CALC_TEST = '''import unittest

from calc import add


class AddTest(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(2, 3), 5)


if __name__ == "__main__":
    unittest.main()
'''

CALC_CONTEXT = """# calc

A tiny calculator library. Code in calc.py, tests in tests/.
Run checks with: python3 -m unittest discover -s tests

## pm
flow: branch-local
host: none
mirror: off
merge: auto
gates: tdd, checks, review, docs
check: python3 -m unittest discover -s tests
milestone: M1
tools: python3=yes gh=no
routines: work=off audit=off
auto_cap: 2
"""


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          env=dict(os.environ, GIT_AUTHOR_NAME="tester", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="tester", GIT_COMMITTER_EMAIL="t@t"))


def pm(root, *args):
    return subprocess.run([sys.executable, str(PLUGIN / "scripts/pm.py"), "--root", str(root), *args], capture_output=True, text=True)


def validate_ok(root, allow=()):
    r = pm(root, "validate")
    if r.returncode == 0:
        return True
    left = [l for l in (r.stdout + r.stderr).splitlines() if l.strip() and l.strip() not in allow and not l.startswith("pm validate")]
    return not left


LOGIN_ALLOW = ("T007: owner set but status is todo",)


def ticket_text(tid, title, status, prio, deps, what, acc, auto="yes", plan="none", proposed=""):
    return f"---\nid: {tid}\ntitle: {title}\nepic: E01\nmilestone: M1\nstatus: {status}\npriority: {prio}\ndepends_on: [{deps}]\nowner:\nauto: {auto}\nplan: {plan}\nissue:\npr:\n---\n## What\n{what}\n\n## Why\nPart of the four basic operations.\n\n## Acceptance\n{acc}\n\n## Subtasks\n- [ ] write the failing test\n- [ ] make it pass\n\n## Plan\nApproach:\nTouches:\nTests first:\nDecisions to record:\napproved: no\n\n## Notes\n\n## Proposed changes\n{proposed}"


def calc_repo(root: Path, with_pm: bool, variant: str = "chain"):
    """variant: chain (T003 depends on T002) | independent | plan_required | routine | proposed"""
    root.mkdir(parents=True)
    (root / "calc.py").write_text(CALC)
    (root / "tests").mkdir()
    (root / "tests/test_calc.py").write_text(CALC_TEST)
    (root / "README.md").write_text("# calc\n\nA tiny calculator library.\n")
    if with_pm:
        (root / "CONTEXT.md").write_text(CALC_CONTEXT)
        pmd = root / "docs/pm"
        (pmd / "epics").mkdir(parents=True)
        (pmd / "tickets").mkdir(parents=True)
        (pmd / "roadmap.md").write_text("# Roadmap\n\nMilestones are ordered versions. Work moves top to bottom.\n\n## M1: Four operations\nGoal: add, subtract, multiply, divide all work and are tested.\nEpics: E01\n\n## Backlog\n- Percent helper\n")
        (pmd / "decisions.md").write_text("# Decisions\n\n## 2026-09-01: Standard library only\nContext: tiny library.\nDecision: no third-party packages.\nConsequences: unittest, not pytest.\n")
        (pmd / "epics/E01-basics.md").write_text("---\nid: E01\ntitle: Calculator basics\nmilestone: M1\nstatus: in progress\nissue:\n---\n## Goal\nThe four basic operations exist and are tested.\n\n## Tickets\n\n## Flow\n")
        proposed = "- parse_amount returns 0 on bad input, which hides errors; it should raise ValueError instead (seen while doing T001)\n" if variant == "proposed" else ""
        (pmd / "tickets/T001-add.md").write_text(ticket_text("T001", "Add function", "done", "P1", "", "add(a, b) returns the sum.", "- [x] add(2, 3) returns 5 and a test covers it", proposed=proposed))
        t2_plan = "required" if variant == "plan_required" else "none"
        (pmd / "tickets/T002-subtract.md").write_text(ticket_text("T002", "Subtract function", "todo", "P1", "T001", "Add subtract(a, b) to calc.py returning a minus b.", "- [ ] subtract(5, 3) returns 2\n- [ ] subtract(0, 4) returns -4\n- [ ] a unit test in tests/test_calc.py covers both and python3 -m unittest discover -s tests passes", plan=t2_plan))
        t3_deps = "" if variant in ("independent", "routine") else "T002"
        t3_auto = "no" if variant == "routine" else "yes"
        (pmd / "tickets/T003-multiply.md").write_text(ticket_text("T003", "Multiply function", "todo", "P2", t3_deps, "Add multiply(a, b) to calc.py.", "- [ ] multiply(4, 3) returns 12 and a test covers it", auto=t3_auto))
        if variant == "bug":
            (pmd / "tickets/T004-average-empty.md").write_text(ticket_text(
                "T004", "Bug: average crashes on an empty list", "todo", "P0", "",
                "average([]) raises ZeroDivisionError. Expected: average([]) returns 0. Reproduce: python3 -c 'import calc; calc.average([])'",
                "- [ ] average([]) returns 0\n- [ ] a test reproduces the bug and now passes", auto="no"))
        pm(root, "flow", "--all")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "initial")


def login_repo(root: Path, all_m1_done: bool = False):
    make_repo(root)
    (root / "README.md").write_text("# lists\n\nA small web app where a person logs in and keeps lists.\n")
    if all_m1_done:
        for p in (root / "docs/pm/tickets").glob("T00[1-5]*.md"):
            s = p.read_text()
            s = re.sub(r"^status: .*$", "status: done", s, count=1, flags=re.M)
            s = re.sub(r"^owner: .*$", "owner:", s, count=1, flags=re.M)
            s = s.replace("- [ ] Something testable happens.", "- [x] Something testable happens.")
            s = s.replace("## Notes\n", "## Notes\nThe check command was slow; a focused test run helped. Review caught an unhandled error path.\n")
            p.write_text(s)
    pm(root, "flow", "--all")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "initial")


def fresh_repo(root: Path, fork: bool = False):
    root.mkdir(parents=True)
    (root / "README.md").write_text("# notes-cli\n\nA command line tool to keep short notes in a text file.\nRun tests with python3 -m unittest\n")
    (root / "notes.py").write_text('import sys\n\n\ndef add_note(path, text):\n    with open(path, "a") as f:\n        f.write(text + "\\n")\n\n\ndef list_notes(path):\n    with open(path) as f:\n        return [l.rstrip("\\n") for l in f]\n\n\nif __name__ == "__main__":\n    add_note("notes.txt", " ".join(sys.argv[1:]))\n')
    (root / "tests").mkdir()
    (root / "tests/test_notes.py").write_text("import os\nimport tempfile\nimport unittest\n\nfrom notes import add_note, list_notes\n\n\nclass NotesTest(unittest.TestCase):\n    def test_add_then_list(self):\n        with tempfile.TemporaryDirectory() as d:\n            p = os.path.join(d, 'n.txt')\n            add_note(p, 'hello')\n            self.assertEqual(list_notes(p), ['hello'])\n")
    (root / "TODO.md").write_text("- search notes\n- delete a note\n- tags\n")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "initial")
    if fork:
        git(root, "remote", "add", "origin", "https://github.com/someone-else/notes-cli.git")


def fork_with_pm(root: Path):
    """A fork that already has pm docs kept out of git through .git/info/exclude."""
    fresh_repo(root, fork=True)
    (root / "CONTEXT.md").write_text("# notes-cli\n\nCode in notes.py, tests in tests/.\n\n## pm\nflow: branch-pr\nhost: github\nmirror: off\nmerge: ask\ngates: tdd, checks, review, docs\ncheck: python3 -m unittest discover -s tests\nmilestone: M1\ntools: python3=yes gh=yes\nroutines: work=off audit=off\nauto_cap: 1\n")
    pmd = root / "docs/pm"
    (pmd / "epics").mkdir(parents=True)
    (pmd / "tickets").mkdir(parents=True)
    (pmd / "roadmap.md").write_text("# Roadmap\n\nMilestones are ordered versions. Work moves top to bottom.\n\n## M1: Search\nGoal: notes can be searched from the command line.\nEpics: E01\n\n## Backlog\n- tags\n")
    (pmd / "decisions.md").write_text("# Decisions\n\n## 2026-09-01: pm layout\nContext: fork.\nDecision: docs/pm stays local.\nConsequences: excluded from git.\n")
    (pmd / "epics/E01-search.md").write_text("---\nid: E01\ntitle: Search\nmilestone: M1\nstatus: in progress\nissue:\n---\n## Goal\nSearch works.\n\n## Tickets\n\n## Flow\n")
    (pmd / "tickets/T001-search.md").write_text(ticket_text("T001", "Search notes", "todo", "P1", "", "Add search(path, word) to notes.py.", "- [ ] search finds a note containing the word and a test covers it", auto="no").replace("epic: E01", "epic: E01"))
    pm(root, "flow", "--all")
    (root / ".git/info/exclude").write_text("docs/pm/\nCONTEXT.md\n")


def nopy_env():
    ensure_bins()
    return {"PATH": str(NOPY_BIN)}


def fork_env():
    ensure_bins()
    return {"PATH": f"{FORK_BIN}:{os.environ['PATH']}"}


SCENARIOS = {
    # ---- round 1/2 core scenarios ----
    "init_implicit": dict(
        setup=fresh_repo, max_turns=80,
        prompt="I want to start managing the work in this project properly, with milestones, epics and tickets. "
               "Set that up for me now. Do not ask me any questions: take the recommended answer for everything, "
               "and do not commit anything.",
        expect_skill="pm:init"),
    "plan_bug_implicit": dict(
        setup=login_repo, max_turns=40,
        prompt="There is a bug: login fails when the password contains a space. Please record it in our project tracking "
               "so we can pick it up later. Do not ask me questions, use sensible defaults.",
        expect_skill="pm:plan"),
    "status_implicit": dict(
        setup=login_repo, max_turns=20,
        prompt="Where are we on this project? What is next and what is blocked?",
        expect_skill="pm:status"),
    "work_implicit": dict(
        setup=lambda r: calc_repo(r, True), max_turns=90,
        prompt="Pick up the next ticket in our project tracking and do it end to end. Do not ask me any questions; "
               "the settings already say to merge automatically.",
        expect_skill="pm:work"),
    "help_explicit": dict(
        setup=lambda r: calc_repo(r, True), max_turns=10,
        prompt="/pm:help",
        expect_skill=None),
    "audit_implicit": dict(
        setup=lambda r: calc_repo(r, True), max_turns=60,
        prompt="Go through the codebase looking for bugs, missing tests and sloppy error handling, and file what you find "
               "in our project tracking. File at most 2. Do not ask me questions and do not change any code.",
        expect_skill="pm:audit"),
    "control_no_pm": dict(
        setup=lambda r: calc_repo(r, True), max_turns=10,
        prompt="What does the average function in calc.py do? One short paragraph.",
        expect_skill=None, expect_no_pm=True),
    # ---- round 3: the gaps ----
    "retro_implicit": dict(
        setup=lambda r: login_repo(r, all_m1_done=True), max_turns=50,
        prompt="We just shipped the first milestone. Close it out and do a short retrospective on how the work went. "
               "Do not ask me questions: take your own suggested answers. Do not commit.",
        expect_skill="pm:retro"),
    "routine_explicit": dict(
        setup=lambda r: calc_repo(r, True, "routine"), max_turns=90,
        prompt="/pm:work --routine",
        expect_skill=None),
    "work_plan_required": dict(
        setup=lambda r: calc_repo(r, True, "plan_required"), max_turns=60,
        prompt="Pick up the next ticket in our project tracking and do it. Do not ask me any questions.",
        expect_skill="pm:work"),
    "work_named_blocked": dict(
        setup=lambda r: calc_repo(r, True), max_turns=30,
        prompt="Do ticket T003 from our project tracking now. No questions.",
        expect_skill="pm:work"),
    "plan_epic_implicit": dict(
        setup=login_repo, max_turns=60,
        prompt="We need a new chunk of work in the first milestone: password reset by email. Add it to our project tracking "
               "and break it into two or three tickets with clear acceptance. Do not ask me questions.",
        expect_skill="pm:plan"),
    "plan_idea_implicit": dict(
        setup=login_repo, max_turns=20,
        prompt="Someday it would be nice to have keyboard shortcuts in the app. Note it down in our project tracking for later.",
        expect_skill="pm:plan"),
    "plan_apply_implicit": dict(
        setup=lambda r: calc_repo(r, True, "proposed"), max_turns=50,
        prompt="The agent that did T001 left proposed changes on the ticket. Go through them and accept them all. "
               "Do not ask me questions.",
        expect_skill="pm:plan"),
    "audit_routine": dict(
        setup=lambda r: calc_repo(r, True), max_turns=60,
        prompt="/pm:audit --routine --cap 2",
        expect_skill=None),
    "init_existing_pm": dict(
        setup=lambda r: calc_repo(r, True), max_turns=20,
        prompt="Set up milestones, epics and tickets tracking for this repo please. No questions.",
        expect_skill=None),
    "help_skill_arg": dict(
        setup=lambda r: calc_repo(r, True), max_turns=10,
        prompt="/pm:help work",
        expect_skill=None),
    "init_fork": dict(
        setup=lambda r: fresh_repo(r, fork=True), max_turns=80, env=fork_env,
        prompt="I want to start managing the work in this project properly, with milestones, epics and tickets. "
               "Set that up for me now. Do not ask me any questions: take the recommended answer for everything, "
               "and do not commit anything.",
        expect_skill="pm:init"),
    "status_fork": dict(
        setup=fork_with_pm, max_turns=20, env=lambda: dict(fork_env(), PM_BACKUP_DIR="{run_dir}/backup"),
        prompt="Show me the project board.",
        expect_skill="pm:status"),
    "nopy_status": dict(
        setup=login_repo, max_turns=25, env=nopy_env,
        prompt="Where are we on this project? What is next and what is blocked?",
        expect_skill="pm:status"),
    "nopy_plan_bug": dict(
        setup=login_repo, max_turns=40, env=nopy_env,
        prompt="There is a bug: login fails when the password contains a space. Please record it in our project tracking "
               "so we can pick it up later. Do not ask me questions, use sensible defaults.",
        expect_skill="pm:plan"),
    "direct_code_request": dict(
        setup=lambda r: calc_repo(r, True), max_turns=40,
        prompt="Add a subtract(a, b) function to calc.py with a unit test.",
        expect_skill=None),
    "work_bug_implicit": dict(
        setup=lambda r: calc_repo(r, True, "bug"), max_turns=60,
        prompt="There is a bug ticket about average crashing on an empty list. Fix it. Do not ask me questions, use sensible defaults.",
        expect_skill="pm:work"),
}


LIMIT_RE = re.compile(r"usage limit|rate limit|limit reached|too many requests|429|overloaded|resets at", re.I)


def probe_capacity(model="haiku") -> tuple[bool, str]:
    env = {k: v for k, v in os.environ.items() if k not in ENV_STRIP}
    cmd = ["claude", "-p", "Reply with the single word ok.", "--model", model, "--max-turns", "1", "--output-format", "json"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=180, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return False, "probe timeout"
    text = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0 and LIMIT_RE.search(text):
        return False, text[-300:]
    try:
        d = json.loads(r.stdout)
        if d.get("is_error") and LIMIT_RE.search(str(d.get("result", ""))):
            return False, str(d.get("result", ""))[-300:]
    except (json.JSONDecodeError, TypeError):
        pass
    return True, text[-120:]


def wait_for_capacity(model="haiku", every=600):
    while True:
        ok, why = probe_capacity(model)
        if ok:
            return
        print(f"usage window full, waiting {every}s: {why!r}", flush=True)
        time.sleep(every)


def hit_limit(out: Path) -> bool:
    """True when the run was cut short (or never started) because the usage window was full."""
    tools, _, result, text, _ = parse(out)
    final = str((result or {}).get("result", "") or "")
    if result and result.get("is_error") and LIMIT_RE.search(final):
        return True
    if tools:
        return False
    blob = final or text or out.read_text(errors="replace")[-2000:]
    return bool(LIMIT_RE.search(str(blob))) and ((result or {}).get("is_error", True) is True or not result)


def run_claude(repo: Path, prompt: str, model: str, max_turns: int, out: Path, extra_env=None) -> tuple[int, float]:
    env = {k: v for k, v in os.environ.items() if k not in ENV_STRIP}
    env.update(extra_env or {})
    cmd = ["claude", "-p", prompt, "--model", model, "--max-turns", str(max_turns),
           "--permission-mode", "bypassPermissions", "--plugin-dir", str(PLUGIN),
           "--output-format", "stream-json", "--verbose"]
    start = time.time()
    with open(out, "w") as fh, open(os.devnull) as devnull:
        proc = subprocess.run(cmd, cwd=repo, stdin=devnull, stdout=fh, stderr=subprocess.STDOUT, env=env, timeout=1800)
    return proc.returncode, time.time() - start


def parse(out: Path):
    tools, skills, result, texts, tool_inputs = [], [], None, [], []
    for line in out.read_text(errors="replace").splitlines():
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("type") == "assistant":
            for b in d.get("message", {}).get("content", []):
                if b.get("type") == "tool_use":
                    tools.append(b["name"])
                    tool_inputs.append((b["name"], b.get("input", {})))
                    if b["name"] == "Skill":
                        skills.append(str(b.get("input", {}).get("skill", "")))
                elif b.get("type") == "text":
                    texts.append(b.get("text", ""))
        elif d.get("type") == "result":
            result = d
    return tools, skills, result, "\n".join(texts), tool_inputs


def agents_ran(tool_inputs):
    """Both review agents were started through the Agent tool."""
    types = [str(inp.get("subagent_type", "")) for name, inp in tool_inputs if name == "Agent"]
    return any("verifier" in x for x in types) and any("reviewer" in x for x in types)


def branch_file(repo, branch_glob, path):
    """Content of <path> on the first local branch matching branch_glob, else ''."""
    branches = [b.strip("* ").strip() for b in git(repo, "branch", "--list", branch_glob).stdout.splitlines()]
    if not branches:
        return ""
    return git(repo, "show", f"{branches[0]}:{path}").stdout


def tests_pass_on_branch(repo, branch_glob):
    branches = [b.strip("* ").strip() for b in git(repo, "branch", "--list", branch_glob).stdout.splitlines()]
    if not branches:
        return False
    wt = repo.parent / "wt-check"
    if wt.exists():
        shutil.rmtree(wt)
    git(repo, "worktree", "add", "--detach", str(wt), branches[0])
    ok = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=wt, capture_output=True).returncode == 0
    git(repo, "worktree", "remove", "--force", str(wt))
    return ok


def evaluate(name: str, spec: dict, repo: Path, run_dir: Path, tools, skills, result, text, tool_inputs):
    checks, info = {}, {}
    pm_skills = [s for s in skills if s.startswith("pm:")]
    info["pm_skills"] = pm_skills
    if spec.get("expect_skill"):
        checks["skill_invoked"] = spec["expect_skill"] in pm_skills
    if spec.get("expect_no_pm"):
        checks["no_pm_skill"] = not pm_skills
    docs = repo / "docs/pm"
    full = result.get("result", "") if result else text
    status = git(repo, "status", "--porcelain").stdout
    commits = git(repo, "rev-list", "--count", "HEAD").stdout.strip()
    bashes = " \n".join(str(i.get("command", "")) for n, i in tool_inputs if n == "Bash")

    def t(tid_glob):
        ps = sorted((docs / "tickets").glob(tid_glob)) if (docs / "tickets").exists() else []
        return ps[0].read_text() if ps else ""

    if name == "init_implicit":
        checks["roadmap_created"] = (docs / "roadmap.md").exists()
        checks["epic_created"] = any((docs / "epics").glob("E*.md")) if (docs / "epics").exists() else False
        checks["pm_block_in_context"] = (repo / "CONTEXT.md").exists() and "## pm" in (repo / "CONTEXT.md").read_text()
        checks["validate_ok"] = validate_ok(repo) if (docs / "roadmap.md").exists() else False
        checks["not_committed"] = commits == "1"
    elif name == "init_fork":
        checks["roadmap_created"] = (docs / "roadmap.md").exists()
        checks["pm_block_in_context"] = (repo / "CONTEXT.md").exists() and "## pm" in (repo / "CONTEXT.md").read_text()
        checks["validate_ok"] = validate_ok(repo) if (docs / "roadmap.md").exists() else False
        excl = (repo / ".git/info/exclude").read_text() if (repo / ".git/info/exclude").exists() else ""
        checks["docs_pm_excluded"] = "docs/pm" in excl
        checks["context_excluded"] = "CONTEXT.md" in excl
        checks["mirror_off"] = "mirror: off" in ((repo / "CONTEXT.md").read_text() if (repo / "CONTEXT.md").exists() else "")
        checks["docs_not_visible_to_git"] = "docs/pm" not in status
        checks["not_committed"] = commits == "1"
    elif name == "init_existing_pm":
        checks["did_not_overwrite"] = status.strip() == "" and commits == "1"
        checks["routed_to_pm"] = bool(pm_skills)
        checks["says_already_set_up"] = any(w in full.lower() for w in ("already", "exists", "set up"))
    elif name == "plan_bug_implicit" or name == "nopy_plan_bug":
        new = sorted(p.name for p in (docs / "tickets").glob("T008*.md"))
        checks["ticket_T008_created"] = bool(new)
        body = (docs / "tickets" / new[0]).read_text() if new else ""
        checks["is_bug_ticket"] = "bug" in body.lower()
        checks["has_reproduce_and_acceptance"] = bool(body) and "## Acceptance" in body and ("reproduc" in body.lower() or "expected" in body.lower())
        checks["flow_redrawn"] = any("T008" in e.read_text() for e in (docs / "epics").glob("E*.md"))
        checks["validate_ok"] = validate_ok(repo, LOGIN_ALLOW)
        checks["not_committed"] = commits == "1"
        if name == "nopy_plan_bug":
            info["bash_with_python"] = [c for c in bashes.split(" \n") if "python" in c][:5]
    elif name == "status_implicit" or name == "nopy_status":
        checks["mentions_in_progress_ticket"] = "T005" in full
        checks["mentions_ready"] = "ready" in full.lower()
        checks["mentions_T007_problem"] = "T007" in full
        checks["no_files_changed"] = status.strip() == ""
    elif name == "status_fork":
        checks["board_printed"] = "T001" in full and "M1" in full
        checks["no_files_changed"] = status.strip() == ""
        backup = run_dir / "backup"
        copies = list(backup.rglob("roadmap.md")) if backup.exists() else []
        checks["backup_copy_made"] = bool(copies)
        checks["backup_has_context"] = bool(list(backup.rglob("CONTEXT.md"))) if backup.exists() else False
        checks["says_where_backup_is"] = "backup" in full.lower()
    elif name == "work_implicit":
        log = git(repo, "log", "--all", "--oneline").stdout
        checks["claim_committed"] = "claim T002" in log
        t2 = t("T002*.md")
        checks["ticket_done_or_review"] = ("status: done" in t2) or ("status: review" in t2)
        checks["plan_written"] = "Approach:" in t2 and len(t2.split("Approach:")[1].split("\n")[0].strip()) > 0
        checks["subtract_works"] = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, '.'); import calc; assert calc.subtract(5,3)==2 and calc.subtract(0,4)==-4"], cwd=repo, capture_output=True).returncode == 0
        checks["tests_pass"] = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=repo, capture_output=True).returncode == 0
        checks["test_added"] = "subtract" in (repo / "tests/test_calc.py").read_text()
        checks["merged_to_main"] = "subtract" in git(repo, "show", "main:calc.py").stdout
        checks["did_not_widen"] = "def multiply" not in (repo / "calc.py").read_text()
        checks["review_agents_ran"] = agents_ran(tool_inputs)
    elif name == "work_bug_implicit":
        log = git(repo, "log", "--all", "--oneline").stdout
        checks["claim_committed"] = "claim T004" in log
        t4 = branch_file(repo, "t004*", "docs/pm/tickets/T004-average-empty.md") or t("T004*.md")
        checks["ticket_done_or_review"] = ("status: done" in t4) or ("status: review" in t4)
        checks["freeze_committed"] = "+tests: frozen" in git(repo, "log", "--all", "-p", "--", "docs/pm/tickets").stdout
        test_src = branch_file(repo, "t004*", "tests/test_calc.py") or (repo / "tests/test_calc.py").read_text()
        checks["test_reproduces_bug"] = "average([])" in test_src.replace(" ", "")
        calc_src = branch_file(repo, "t004*", "calc.py") or (repo / "calc.py").read_text()
        checks["bug_fixed"] = subprocess.run([sys.executable, "-c", calc_src + "\nassert average([]) == 0"], capture_output=True).returncode == 0
        checks["tests_pass"] = tests_pass_on_branch(repo, "t004*")
        frozen_at = git(repo, "log", "--all", "--format=%H", "--reverse", "-S", "tests: frozen", "--", "docs/pm/tickets").stdout.split()
        heads = git(repo, "branch", "--list", "--format=%(refname:short)", "t004*").stdout.split() or ["HEAD"]
        changed = git(repo, "diff", "--name-only", frozen_at[0], heads[0], "--", "tests").stdout.strip() if frozen_at else ""
        checks["no_silent_test_edit"] = bool(frozen_at) and (not changed or "Test change:" in t4)
        checks["did_not_widen"] = "def subtract" not in calc_src and "def multiply" not in calc_src
        checks["review_agents_ran"] = agents_ran(tool_inputs)
    elif name == "routine_explicit":
        log = git(repo, "log", "--all", "--oneline").stdout
        t2, t3 = branch_file(repo, "t002*", "docs/pm/tickets/T002-subtract.md") or t("T002*.md"), t("T003*.md")
        checks["claim_committed"] = "claim T002" in log
        checks["t002_in_review"] = "status: review" in t2
        checks["plan_written"] = "Approach:" in t2 and len(t2.split("Approach:")[1].split("\n")[0].strip()) > 0
        checks["branch_has_subtract"] = "def subtract" in branch_file(repo, "t002*", "calc.py")
        checks["branch_tests_pass"] = tests_pass_on_branch(repo, "t002*")
        checks["not_merged"] = "subtract" not in git(repo, "show", "main:calc.py").stdout
        checks["t003_untouched"] = "status: todo" in t3 and "owner:\n" in t3
        checks["did_not_widen"] = "def multiply" not in branch_file(repo, "t002*", "calc.py")
    elif name == "work_plan_required":
        log = git(repo, "log", "--all", "--oneline").stdout
        t2 = t("T002*.md")
        checks["claim_committed"] = "claim T002" in log
        checks["plan_written"] = "Approach:" in t2 and len(t2.split("Approach:")[1].split("\n")[0].strip()) > 0
        checks["not_approved"] = "approved: yes" not in t2
        checks["no_code_written"] = "subtract" not in (repo / "calc.py").read_text() and "subtract" not in branch_file(repo, "t002*", "calc.py")
        checks["still_in_progress"] = "status: in progress" in t2
        checks["says_waiting_for_approval"] = "approv" in full.lower()
    elif name == "work_named_blocked":
        t3 = t("T003*.md")
        checks.pop("skill_invoked", None)
        checks["skill_or_direct_refusal"] = ("pm:work" in pm_skills) or ("T002" in full and "status: todo" in t3)
        checks["t003_not_claimed"] = "status: todo" in t3 and "owner:\n" in t3
        checks["no_branch_created"] = not git(repo, "branch", "--list", "t003*").stdout.strip()
        checks["no_code_written"] = "multiply" not in (repo / "calc.py").read_text()
        checks["names_open_dependency"] = "T002" in full
        checks["nothing_committed"] = commits == "1"
    elif name == "plan_epic_implicit":
        epics = sorted((docs / "epics").glob("E03*.md"))
        checks["epic_E03_created"] = bool(epics)
        road = (docs / "roadmap.md").read_text()
        m1 = road.split("## M1")[1].split("## M2")[0] if "## M1" in road else ""
        checks["roadmap_M1_lists_E03"] = "E03" in m1
        new = [p for p in (docs / "tickets").glob("T*.md") if p.name[:4] not in ("T001", "T002", "T003", "T004", "T005", "T006", "T007")]
        checks["two_or_three_tickets"] = 2 <= len(new) <= 3
        checks["tickets_in_E03"] = all("epic: E03" in p.read_text() for p in new) if new else False
        checks["flow_drawn"] = bool(epics) and any(p.name[:4] in epics[0].read_text() for p in new)
        checks["validate_ok"] = validate_ok(repo, LOGIN_ALLOW)
        checks["not_committed"] = commits == "1"
    elif name == "plan_idea_implicit":
        road = (docs / "roadmap.md").read_text()
        backlog = road.split("## Backlog")[1] if "## Backlog" in road else ""
        checks["backlog_line_added"] = "keyboard" in backlog.lower()
        checks["no_ticket_created"] = len(list((docs / "tickets").glob("T*.md"))) == 7
        checks["only_roadmap_changed"] = [l[3:] for l in status.splitlines()] == ["docs/pm/roadmap.md"]
    elif name == "plan_apply_implicit":
        t1 = t("T001*.md")
        new = [p for p in (docs / "tickets").glob("T*.md") if p.name[:4] not in ("T001", "T002", "T003")]
        checks["new_ticket_created"] = len(new) >= 1
        checks["new_ticket_about_parse_amount"] = any("parse_amount" in p.read_text() for p in new)
        prop = t1.split("## Proposed changes")[1] if "## Proposed changes" in t1 else "x"
        checks["proposals_cleared"] = "parse_amount" not in prop
        checks["flow_redrawn"] = any(p.name[:4] in (docs / "epics/E01-basics.md").read_text() for p in new) if new else False
        checks["validate_ok"] = validate_ok(repo)
        checks["no_code_changed"] = "calc.py" not in status
    elif name == "help_explicit":
        checks["lists_all_skills"] = all(s in full for s in ["/pm:init", "/pm:plan", "/pm:work", "/pm:status", "/pm:retro", "/pm:audit"])
        checks["shows_project_settings"] = "branch-local" in full or "flow:" in full
    elif name == "help_skill_arg":
        checks["work_section_shown"] = "claim" in full.lower() and "gates" in full.lower()
        checks["shows_project_settings"] = "branch-local" in full or "flow:" in full
        checks["not_whole_sheet"] = "/pm:retro" not in full.split("This project")[0] if "This project" in full else "/pm:retro" not in full
    elif name in ("audit_implicit", "audit_routine"):
        new = [p for p in (docs / "tickets").glob("T*.md") if p.name[:4] not in ("T001", "T002", "T003")]
        checks["tickets_filed"] = 1 <= len(new) <= 2
        checks["evidence_has_file_ref"] = all("calc.py" in p.read_text() for p in new) if new else False
        code_changed = [l for l in status.splitlines() if not l[3:].startswith("docs/pm/") and "__pycache__" not in l]
        checks["no_code_changed"] = not code_changed
        checks["not_auto"] = all("auto: no" in p.read_text() for p in new) if new else False
        checks["validate_ok"] = validate_ok(repo)
        if name == "audit_routine":
            checks["not_committed"] = commits == "1"
    elif name == "retro_implicit":
        road = (docs / "roadmap.md").read_text()
        m1 = road.split("## M1")[1].split("## M2")[0] if "## M1" in road else ""
        checks["retro_block_under_M1"] = "Retro:" in m1 or "retro" in m1.lower()
        ctx = (repo / "CONTEXT.md").read_text()
        checks["milestone_now_M2"] = bool(re.search(r"^milestone:\s*M2\s*$", ctx, re.M))
        checks["pm_block_still_parses"] = pm(repo, "config").returncode == 0 and "flow=branch-pr" in pm(repo, "config").stdout.replace(": ", "=")
        checks["validate_ok"] = validate_ok(repo, LOGIN_ALLOW)
        checks["not_committed"] = commits == "1"
        checks["no_code_changed"] = all(l[3:].startswith("docs/pm/") or l[3:] == "CONTEXT.md" for l in status.splitlines())
    elif name == "control_no_pm":
        checks["answers_question"] = "average" in full.lower() or "mean" in full.lower()
        checks["no_files_changed"] = status.strip() == ""
    elif name == "direct_code_request":
        checks["subtract_works"] = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, '.'); import calc; assert calc.subtract(5,3)==2"], cwd=repo, capture_output=True).returncode == 0
        checks["tests_pass"] = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=repo, capture_output=True).returncode == 0
        info["used_pm_skill"] = bool(pm_skills)
        info["ticket_T002_touched"] = "docs/pm/tickets/T002" in status or "claim T002" in git(repo, "log", "--all", "--oneline").stdout
        info["stop_hook_notice_seen"] = "no ticket was updated" in (run_dir / "out.jsonl").read_text(errors="replace")
    checks["no_time_words_in_docs"] = not any(BANNED.search(p.read_text()) for p in docs.rglob("*.md")) if docs.exists() else True
    return checks, info


def main():
    args = sys.argv[1:]
    out_root = RESULTS / "headless"
    reeval = False
    while args and args[0].startswith("--"):
        if args[0] == "--out":
            out_root = Path(args[1]) if args[1].startswith("/") else RESULTS / args[1]
            args = args[2:]
        elif args[0] == "--reeval":
            reeval = True
            args = args[1:]
    model = args[0]
    names = args[1:] or list(SCENARIOS)
    base = out_root / model
    for name in names:
        spec = SCENARIOS[name]
        run_dir = base / name
        repo = run_dir / "repo"
        out = run_dir / "out.jsonl"
        if reeval:
            old = json.loads((run_dir / "summary.json").read_text())
            code, secs = old["exit"], old["seconds"]
        else:
            if run_dir.exists():
                shutil.rmtree(run_dir)
            run_dir.mkdir(parents=True)
            spec["setup"](repo)
        extra_env = spec["env"]() if spec.get("env") else {}
        extra_env = {k: v.replace("{run_dir}", str(run_dir)) for k, v in extra_env.items()}
        for attempt in range(0 if reeval else 6):
            wait_for_capacity(model)
            try:
                code, secs = run_claude(repo, spec["prompt"], model, spec["max_turns"], out, extra_env)
            except subprocess.TimeoutExpired:
                code, secs = -1, 1800.0
            if not hit_limit(out):
                break
            print(f"[{model}] {name}: usage window full during the run, retrying after a pause", flush=True)
            shutil.rmtree(repo)
            spec["setup"](repo)
            time.sleep(600)
        tools, skills, result, text, tool_inputs = parse(out)
        checks, info = evaluate(name, spec, repo, run_dir, tools, skills, result, text, tool_inputs)
        summary = {
            "model": model, "scenario": name, "exit": code, "seconds": round(secs),
            "turns": (result or {}).get("num_turns"),
            "skills": skills, "tools": sorted(set(tools)), "checks": checks, "info": info,
            "passed": sum(checks.values()), "total": len(checks),
            "result_head": ((result or {}).get("result") or text)[:800],
        }
        (run_dir / "summary.json").write_text(json.dumps(summary, indent=1))
        print(f"[{model}] {name}: {summary['passed']}/{summary['total']} skills={skills} {summary['seconds']}s", flush=True)


if __name__ == "__main__":
    main()
