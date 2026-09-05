"""Live branch-pr flow test against a throwaway private GitHub repo.

usage: python3 livepr.py setup                       # create repo, push code + docs, mirror issues
       python3 livepr.py run <model> <ask|auto> <Txxx> # fresh clone, set merge mode, run claude, evaluate
Writes livepr/<model>-<mode>-<Txxx>/{out.jsonl,summary.json}
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness as h  # noqa: E402

SLUG = os.environ.get("PM_EVAL_REPO", "")  # "owner/name": a throwaway private repo you own; it gets rewritten
OWNER, _, REPO = SLUG.partition("/")
BASE = h.RESULTS / "livepr"

CONTEXT = """# calc

A tiny calculator library. Code in calc.py, tests in tests/.
Run checks with: python3 -m unittest discover -s tests

## pm
flow: branch-pr
host: github
mirror: on
merge: {merge}
gates: tdd, checks, review, docs
check: python3 -m unittest discover -s tests
milestone: M1
tools: python3=yes gh=yes
routines: work=off audit=off
auto_cap: 1
"""

TICKETS = [
    ("T002", "Subtract function", "P1", "Add subtract(a, b) to calc.py returning a minus b.",
     "- [ ] subtract(5, 3) returns 2\n- [ ] subtract(0, 4) returns -4\n- [ ] a unit test in tests/test_calc.py covers both"),
    ("T003", "Multiply function", "P1", "Add multiply(a, b) to calc.py returning the product.",
     "- [ ] multiply(4, 3) returns 12\n- [ ] multiply(4, 0) returns 0\n- [ ] a unit test in tests/test_calc.py covers both"),
    ("T004", "Power function", "P2", "Add power(a, b) to calc.py returning a raised to b.",
     "- [ ] power(2, 3) returns 8\n- [ ] power(5, 0) returns 1\n- [ ] a unit test in tests/test_calc.py covers both"),
    ("T005", "Modulo function", "P2", "Add modulo(a, b) to calc.py returning the remainder of a divided by b.",
     "- [ ] modulo(7, 3) returns 1\n- [ ] modulo(6, 3) returns 0\n- [ ] a unit test in tests/test_calc.py covers both"),
]


def sh(*cmd, cwd=None, check=True, env=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env)
    if check and r.returncode != 0:
        raise SystemExit(f"failed: {' '.join(cmd)}\n{r.stdout}\n{r.stderr}")
    return r


def gh_json(*args):
    r = sh("gh", *args, "--repo", SLUG)
    return json.loads(r.stdout) if r.stdout.strip() else None


def setup():
    seed = BASE / "seed"
    if seed.exists():
        shutil.rmtree(seed)
    seed.mkdir(parents=True)
    (seed / "calc.py").write_text(h.CALC)
    (seed / "tests").mkdir()
    (seed / "tests/test_calc.py").write_text(h.CALC_TEST)
    (seed / "README.md").write_text("# calc\n\nA tiny calculator library. Throwaway repo for a plugin test.\n")
    (seed / "CONTEXT.md").write_text(CONTEXT.format(merge="ask"))
    pmd = seed / "docs/pm"
    (pmd / "epics").mkdir(parents=True)
    (pmd / "tickets").mkdir(parents=True)
    (pmd / "roadmap.md").write_text("# Roadmap\n\nMilestones are ordered versions. Work moves top to bottom.\n\n## M1: Four operations\nGoal: the basic operations all work and are tested.\nEpics: E01\n\n## Backlog\n- Percent helper\n")
    (pmd / "decisions.md").write_text("# Decisions\n\n## 2026-09-01: Standard library only\nContext: tiny library.\nDecision: no third-party packages.\nConsequences: unittest, not pytest.\n")
    (pmd / "epics/E01-basics.md").write_text("---\nid: E01\ntitle: Calculator basics\nmilestone: M1\nstatus: in progress\nissue:\n---\n## Goal\nThe basic operations exist and are tested.\n\n## Tickets\n\n## Flow\n")
    (pmd / "tickets/T001-add.md").write_text(h.ticket_text("T001", "Add function", "done", "P1", "", "add(a, b) returns the sum.", "- [x] add(2, 3) returns 5 and a test covers it"))
    for tid, title, prio, what, acc in TICKETS:
        (pmd / f"tickets/{tid}-{title.split()[0].lower()}.md").write_text(h.ticket_text(tid, title, "todo", prio, "", what, acc))
    h.pm(seed, "flow", "--all")
    assert h.pm(seed, "validate").returncode == 0
    h.git(seed, "init", "-q", "-b", "main")
    h.git(seed, "add", ".")
    h.git(seed, "commit", "-q", "-m", "initial")
    sh("gh", "repo", "create", SLUG, "--private", "--description", "throwaway: pm plugin branch-pr test", "--source", str(seed), "--remote", "origin", "--push")
    r = subprocess.run([sys.executable, str(h.PLUGIN / "scripts/pm.py"), "sync"], cwd=seed, capture_output=True, text=True)
    print(r.stdout, r.stderr)
    h.git(seed, "add", "docs/pm")
    h.git(seed, "commit", "-q", "-m", "pm: issue numbers from sync")
    sh("git", "push", "-q", cwd=seed)
    print("setup done:", f"https://github.com/{SLUG}")


FUNCS = {"T002": "subtract", "T003": "multiply", "T004": "power", "T005": "modulo", "T006": "negate", "T007": "absolute", "T008": "square", "T009": "cube"}
EXTRA = {
    "T006": ("Negate function", "P2", "Add negate(a) to calc.py returning -a.", "- [ ] negate(3) returns -3\n- [ ] negate(0) returns 0\n- [ ] a unit test in tests/test_calc.py covers both"),
    "T007": ("Absolute function", "P2", "Add absolute(a) to calc.py returning a without its sign.", "- [ ] absolute(-4) returns 4\n- [ ] absolute(4) returns 4\n- [ ] a unit test in tests/test_calc.py covers both"),
    "T008": ("Square function", "P2", "Add square(a) to calc.py returning a times a.", "- [ ] square(3) returns 9\n- [ ] square(-2) returns 4\n- [ ] a unit test in tests/test_calc.py covers both"),
    "T009": ("Cube function", "P2", "Add cube(a) to calc.py returning a times a times a.", "- [ ] cube(2) returns 8\n- [ ] cube(-2) returns -8\n- [ ] a unit test in tests/test_calc.py covers both"),
}


def add_ticket(tid):
    """Push one more independent ticket (and its mirrored issue) so another model can take a fresh one."""
    work = BASE / "add-ticket"
    if work.exists():
        shutil.rmtree(work)
    sh("gh", "repo", "clone", SLUG, str(work), "--", "-q")
    title, prio, what, acc = EXTRA[tid]
    (work / f"docs/pm/tickets/{tid}-{title.split()[0].lower()}.md").write_text(h.ticket_text(tid, title, "todo", prio, "", what, acc))
    h.pm(work, "flow", "--all")
    r = subprocess.run([sys.executable, str(h.PLUGIN / "scripts/pm.py"), "sync"], cwd=work, capture_output=True, text=True)
    print(r.stdout.strip(), r.stderr.strip())
    assert h.pm(work, "validate").returncode == 0
    h.git(work, "add", "docs/pm")
    h.git(work, "commit", "-q", "-m", f"pm: add {tid}")
    sh("git", "push", "-q", cwd=work)
    print("added", tid)


def run(model, mode, tid, reeval=False):
    run_dir = BASE / f"{model}-{mode}-{tid}"
    repo = run_dir / "repo"
    out = run_dir / "out.jsonl"
    if not reeval:
        if run_dir.exists():
            shutil.rmtree(run_dir)
        run_dir.mkdir(parents=True)
        sh("gh", "repo", "clone", SLUG, str(repo), "--", "-q")
        ctx = (repo / "CONTEXT.md").read_text()
        want = CONTEXT.format(merge=mode)
        if ctx != want:
            (repo / "CONTEXT.md").write_text(want)
            h.git(repo, "add", "CONTEXT.md")
            h.git(repo, "commit", "-q", "-m", f"pm: merge {mode}")
            sh("git", "push", "-q", cwd=repo)
        env = {"PM_OWNER": f"live-{model}"}
        prompt = "Pick up the next ticket in our project tracking and do it end to end."
        h.wait_for_capacity(model)
        try:
            code, secs = h.run_claude(repo, prompt, model, 100, out, env)
        except subprocess.TimeoutExpired:
            code, secs = -1, 1800.0
    else:
        old = json.loads((run_dir / "summary.json").read_text())
        code, secs = old["exit"], old["seconds"]
    tools, skills, result, text, tool_inputs = h.parse(out)
    full = result.get("result", "") if result else text
    checks, info = {}, {}
    checks["skill_invoked"] = "pm:work" in skills
    sh("git", "fetch", "-q", "--all", cwd=repo)
    main_log = sh("git", "log", "origin/main", "--oneline", cwd=repo).stdout
    checks["claim_pushed_to_main"] = f"claim {tid}" in main_log
    prs = gh_json("pr", "list", "--state", "all", "--json", "number,title,body,state,headRefName,mergedAt", "--limit", "50")
    mine = [p for p in prs if p["title"].startswith(f"{tid}")]
    info["prs"] = [(p["number"], p["title"], p["state"]) for p in mine]
    checks["one_pr_created"] = len(mine) == 1
    pr = mine[0] if mine else None
    ticket_main = sh("git", "show", f"origin/main:docs/pm/tickets/", cwd=repo, check=False).stdout
    tfile = next((n for n in ticket_main.splitlines() if n.startswith(tid)), None)
    on_main = sh("git", "show", f"origin/main:docs/pm/tickets/{tfile}", cwd=repo, check=False).stdout if tfile else ""
    on_branch = sh("git", "show", f"origin/{pr['headRefName']}:docs/pm/tickets/{tfile}", cwd=repo, check=False).stdout if (pr and tfile) else ""
    issue = next((l.split(":", 1)[1].strip() for l in on_main.splitlines() if l.startswith("issue:")), "")
    info["issue"] = issue
    checks["pr_body_closes_issue"] = bool(pr) and bool(issue) and f"#{issue}" in (pr["body"] or "")
    latest = on_main if "status: done" in on_main else on_branch
    checks["ticket_pr_field_set"] = bool(pr) and f"pr: {pr['number']}" in latest
    checks["plan_written"] = "Approach:" in latest and len(latest.split("Approach:")[1].split("\n")[0].strip()) > 0
    fn = FUNCS[tid]
    others = [v for k, v in FUNCS.items() if k != tid]

    def widened(after_calc, base_calc):
        return any(f"def {k}" in after_calc and f"def {k}" not in base_calc for k in others)

    if mode == "ask":
        checks["pr_left_open"] = bool(pr) and pr["state"] == "OPEN"
        checks["ticket_in_review"] = "status: review" in on_branch
        checks["main_untouched_by_code"] = f"def {fn}" not in sh("git", "show", "origin/main:calc.py", cwd=repo).stdout
        checks["asked_or_deferred_merge"] = "merge" in full.lower()
        branch_calc = sh("git", "show", f"origin/{pr['headRefName']}:calc.py", cwd=repo, check=False).stdout if pr else ""
        checks["branch_has_function"] = f"def {fn}" in branch_calc
        base = sh("git", "merge-base", "origin/main", f"origin/{pr['headRefName']}", cwd=repo, check=False).stdout.strip() if pr else ""
        base_calc = sh("git", "show", f"{base}:calc.py", cwd=repo, check=False).stdout if base else ""
        checks["did_not_widen"] = bool(pr) and not widened(branch_calc, base_calc)
    else:
        checks["pr_merged"] = bool(pr) and pr["state"] == "MERGED"
        checks["ticket_done_on_main"] = "status: done" in on_main
        main_calc = sh("git", "show", "origin/main:calc.py", cwd=repo).stdout
        checks["main_has_function"] = f"def {fn}" in main_calc
        squash = next((l.split()[0] for l in main_log.splitlines() if l.split(" ", 1)[1].startswith(tid)), "")
        base_calc = sh("git", "show", f"{squash}^:calc.py", cwd=repo, check=False).stdout if squash else ""
        after_calc = sh("git", "show", f"{squash}:calc.py", cwd=repo, check=False).stdout if squash else ""
        checks["did_not_widen"] = bool(squash) and not widened(after_calc, base_calc)
        st = gh_json("issue", "view", issue, "--json", "state") if issue else None
        checks["issue_closed"] = bool(st) and st["state"] == "CLOSED"
        epic = sh("git", "show", "origin/main:docs/pm/epics/E01-basics.md", cwd=repo).stdout
        checks["flow_redrawn_with_done"] = tid in epic.split("## Flow")[1] if "## Flow" in epic else False
        wt = run_dir / "main-check"
        sh("git", "worktree", "add", "-q", str(wt), "origin/main", cwd=repo)
        checks["main_tests_pass"] = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=wt, capture_output=True).returncode == 0
        sh("git", "worktree", "remove", "--force", str(wt), cwd=repo)
    checks["no_time_words_in_docs"] = not any(h.BANNED.search(p.read_text()) for p in (repo / "docs/pm").rglob("*.md"))
    summary = {"model": model, "mode": mode, "ticket": tid, "exit": code, "seconds": round(secs), "turns": (result or {}).get("num_turns"),
               "skills": skills, "checks": checks, "info": info, "passed": sum(checks.values()), "total": len(checks),
               "result_head": full[:800]}
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=1))
    print(f"[{model} {mode} {tid}] {summary['passed']}/{summary['total']} failed={[k for k, v in checks.items() if not v]} {summary['seconds']}s", flush=True)


if __name__ == "__main__":
    if not SLUG or not REPO:
        sys.exit("set PM_EVAL_REPO=owner/name first: a throwaway private GitHub repo you own (setup rewrites it)")
    if sys.argv[1] == "setup":
        setup()
    elif sys.argv[1] == "add-ticket":
        add_ticket(sys.argv[2])
    elif sys.argv[1] == "reeval":
        run(sys.argv[2], sys.argv[3], sys.argv[4], reeval=True)
    else:
        run(sys.argv[2], sys.argv[3], sys.argv[4])
