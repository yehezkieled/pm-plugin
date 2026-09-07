"""Drives a real interactive Claude Code session in tmux, answering its dialogs like a person would.

usage: python3 interactive.py [--out DIR] <model> <scenario>
scenarios: work_plan_mode | init_interview | plan_bug_interview | work_merge_ask | retro_interview | grill_interview | brainstorm_session
Writes <out>/<model>/<scenario>/{screen.log,transcript.jsonl,summary.json}
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness as h  # noqa: E402

ENV_U = " ".join(f"-u {k}" for k in h.ENV_STRIP)


def tmux(*args):
    return subprocess.run(["tmux", *args], capture_output=True, text=True)


class Session:
    def __init__(self, name, repo, model, log):
        self.name, self.repo, self.model, self.log = name, repo, model, log
        self.last = ""
        self.typed = ""
        self.events = []

    def start(self):
        tmux("kill-session", "-t", f"={self.name}:")
        cmd = f"env {ENV_U} claude --model {self.model} --plugin-dir {h.PLUGIN} --dangerously-skip-permissions; sleep 3"
        r = tmux("new-session", "-d", "-s", self.name, "-x", "200", "-y", "50", "-c", str(self.repo), cmd)
        if r.returncode:
            raise SystemExit(r.stderr)

    def screen(self, lines=80):
        r = tmux("capture-pane", "-p", "-t", f"={self.name}:", "-S", f"-{lines}")
        text = r.stdout
        if text != self.last:
            with open(self.log, "a") as fh:
                fh.write(f"\n===== {time.strftime('%H:%M:%S')} =====\n{text}")
            self.last = text
        return text

    def keys(self, *keys):
        tmux("send-keys", "-t", f"={self.name}:", *keys)

    def type_text(self, text):
        self.typed = text
        tmux("send-keys", "-t", f"={self.name}:", "-l", text)
        time.sleep(0.8)
        self.keys("Enter")

    def event(self, kind, detail=""):
        self.events.append({"t": time.strftime("%H:%M:%S"), "kind": kind, "detail": detail})
        with open(self.log, "a") as fh:
            fh.write(f"\n>>>>> {kind}: {detail}\n")

    def stop(self):
        self.type_text("/exit")
        time.sleep(3)
        tmux("kill-session", "-t", f"={self.name}:")


def visible_lines(text):
    return [l.rstrip() for l in text.splitlines() if l.strip()]


def prompt_row_free(lines, typed):
    """The input row is empty or holds only Claude Code's own suggestion, not text we typed and never submitted."""
    for l in lines:
        m = re.match(r"^❯(?:\s+(.*))?$", l.strip())
        if m:
            text = (m.group(1) or "").strip()
            return text == "" or text != typed.strip()
    return False


def question_block(text):
    """The AskUserQuestion dialog: (question text, [option labels]) or None."""
    if "Enter to select" not in text or "❯ 1." not in text:
        return None
    lines = visible_lines(text)
    opts, q = [], []
    seen_first = False
    for l in lines:
        m = re.match(r"^\s*(?:❯\s*)?(\d+)\.\s+(.*)$", l)
        if m:
            seen_first = True
            opts.append(m.group(2).strip())
        elif not seen_first:
            q.append(l.strip())
    q = [x for x in q if not x.startswith(("☐", "☑", "☒", "─", "━", "▔", "╌", "⎿", "●", "←", "Submit"))]
    return " ".join(q[-2:]), opts


def choose_option(question, opts, policy):
    """Index (0-based) of the option to pick."""
    ql = question.lower()
    for key, want in policy:
        if key in ql:
            for i, o in enumerate(opts):
                if any(w in o.lower() for w in want):
                    return i
    return 0


def transcript_path(repo, since):
    d = Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(repo))
    if not d.exists():
        return None
    files = [p for p in d.glob("*.jsonl") if p.stat().st_mtime >= since - 5]
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


def read_transcript(path):
    tools, texts = [], []
    if not path or not path.exists():
        return tools, texts
    for line in path.read_text(errors="replace").splitlines():
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("type") != "assistant":
            continue
        for b in d.get("message", {}).get("content", []):
            if b.get("type") == "tool_use":
                tools.append((b["name"], b.get("input", {})))
            elif b.get("type") == "text":
                texts.append(b.get("text", ""))
    return tools, texts


SCENARIOS = {
    "work_plan_mode": dict(
        setup=lambda r: h.calc_repo(r, True, "plan_required"),
        prompt="Pick up the next ticket in our project tracking and do it.",
        text_policy=[],            # never answer plain-text questions: the run ends when the ticket is done
        done=lambda r: "status: done" in (r / "docs/pm/tickets/T002-subtract.md").read_text()),
    "work_merge_ask": dict(
        setup=lambda r: (h.calc_repo(r, True), (r / "CONTEXT.md").write_text((r / "CONTEXT.md").read_text().replace("merge: auto", "merge: ask")), h.git(r, "commit", "-qam", "merge ask")),
        prompt="Pick up the next ticket in our project tracking and do it.",
        text_policy=[("merge", "Yes, merge it now.")],
        done=lambda r: "status: done" in (r / "docs/pm/tickets/T002-subtract.md").read_text()),
    "init_interview": dict(
        setup=h.fresh_repo,
        prompt="Set up project management for this repo.",
        text_policy=[("commit", "No, do not commit."), ("?", "Yes, go ahead.")],
        done=lambda r: False),
    "plan_bug_interview": dict(
        setup=h.login_repo,
        prompt="There is a bug: login fails when the password contains a space. Record it in our project tracking.",
        text_policy=[("commit", "No."), ("?", "Yes, that is right.")],
        done=lambda r: any((r / "docs/pm/tickets").glob("T008*.md"))),
    "retro_interview": dict(
        setup=lambda r: h.login_repo(r, all_m1_done=True),
        prompt="We shipped the first milestone. Close it out and do the retro.",
        text_policy=[("commit", "No, do not commit."), ("?", "Yes, agreed.")],
        done=lambda r: False),
    "grill_interview": dict(
        setup=h.grill_repo,
        prompt="Ticket T008 is only a rough note. Grill me on it so it is ready to work on.",
        text_policy=[("commit", "No."), ("?", "Yes, that is right.")],
        done=lambda r: "ready: yes" in (r / "docs/pm/tickets/T008-remember-me.md").read_text()),
    "brainstorm_session": dict(
        setup=h.login_repo,
        prompt="Let us brainstorm what the login part of this app still needs before a person could use it.",
        text_policy=[("commit", "No."), ("?", "Yes, that is right, go on.")],
        done=lambda r: False),
}

# AskUserQuestion answer policy: (substring of the question, words that mark the option to pick)
ASK_POLICY = [("commit", ("no", "not", "later", "skip")), ("archive", ("archive", "move")), ("merge", ("yes", "merge")),
              ("model", ("opus",)),  # answer Opus, not the default, so a pass proves the answer reached the Agent tool
              ("go ahead", ("go",)),
              ("apply", ("apply", "all", "yes")), ("write", ("apply", "all", "yes")),  # the brainstorm proposal: apply every row
              ("grill", ("later",)), ("ready: no", ("later",)), ("now, or later", ("later",))]  # keep a brainstorm run bounded: new tickets are grilled in their own run


def reeval(model, scenario, out_root):
    spec = SCENARIOS[scenario]
    run_dir = out_root / model / scenario
    repo = run_dir / "repo"
    old = json.loads((run_dir / "summary.json").read_text())
    tp = run_dir / "transcript.jsonl"
    if not tp.exists():
        src = transcript_path(repo, 0)
        if src:
            shutil.copy(src, tp)
    tools, texts = read_transcript(tp)
    checks = evaluate(scenario, repo, tools, texts, old["events"])
    old.update({"tools": [n for n, _ in tools], "checks": checks, "passed": sum(checks.values()), "total": len(checks),
                "last_text": (texts[-1] if texts else "")[:800]})
    (run_dir / "summary.json").write_text(json.dumps(old, indent=1))
    print(f"[{model}] {scenario}: {old['passed']}/{old['total']} failed={[k for k, v in checks.items() if not v]} (reeval)", flush=True)


def drive(model, scenario, out_root):
    spec = SCENARIOS[scenario]
    run_dir = out_root / model / scenario
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    repo = run_dir / "repo"
    spec["setup"](repo)
    log = run_dir / "screen.log"
    h.wait_for_capacity(model)
    s = Session(f"pm-{model}-{scenario}"[:48], repo, model, log)
    start = time.time()
    s.start()
    prompt_sent = False
    prompt_at = 0.0
    answered_text = 0
    stable_since = None
    last_screen = None
    finished = False
    reason = "timeout"
    while time.time() - start < 1500:
        time.sleep(3)
        scr = s.screen()
        lines = visible_lines(scr)
        tail = "\n".join(lines[-40:])
        if "Yes, I trust this folder" in tail:
            s.keys("Down", "Enter"); s.event("trust_dialog"); time.sleep(3); continue
        if "Yes, I accept" in tail and "Bypass" in tail:
            s.keys("Down", "Enter"); s.event("bypass_dialog"); time.sleep(3); continue
        if not prompt_sent:
            if any(l.startswith("❯") for l in lines) and "Claude Code v" in scr:
                s.type_text(spec["prompt"]); s.event("prompt", spec["prompt"]); prompt_sent = True; prompt_at = time.time()
            continue
        if time.time() - prompt_at < 8 and spec["prompt"][:30] in tail and "esc to interrupt" not in tail:
            # the input box still holds the text: submit again
            s.keys("Enter"); time.sleep(3); continue
        if "Ready to submit your answers?" in tail and "Submit answers" in tail:
            s.keys("Enter"); s.event("submit_answers"); time.sleep(3); continue
        if "hit your session limit" in tail or "Limit reached" in tail:
            reason = "limit"; finished = True; break
        if "Would you like to proceed?" in tail and ("Ready to code" in tail or "manually approve" in tail):
            s.keys("Enter"); s.event("plan_approved"); time.sleep(4); continue
        qb = question_block(tail)
        if qb:
            question, opts = qb
            multi = any(o.startswith(("[ ]", "[✔]", "[x]")) for o in opts)
            if multi:
                # checkbox list: tick the first box when it is empty, then move the cursor to the Submit row and press Enter
                if opts[0].startswith("[ ]"):
                    s.keys("Enter"); time.sleep(0.5)
                for _ in range(10):
                    cur = [l for l in visible_lines(s.screen()) if l.lstrip().startswith("❯")]
                    if cur and "Submit" in cur[-1]:
                        break
                    s.keys("Down"); time.sleep(0.3)
                s.keys("Enter")
                s.event("ask_answered_multi", f"{question} -> {opts[0]}")
                time.sleep(4)
                continue
            idx = choose_option(question, opts, ASK_POLICY)
            for _ in range(idx):
                s.keys("Down"); time.sleep(0.2)
            s.keys("Enter")
            s.event("ask_answered", f"{question} -> {opts[idx] if idx < len(opts) else idx}")
            time.sleep(4)
            continue
        if "Do you want to proceed?" in tail and "1. Yes" in tail:
            s.keys("Enter"); s.event("permission_yes"); time.sleep(2); continue
        busy = "esc to interrupt" in tail or "Thinking" in tail
        idle = (not busy) and prompt_row_free(lines[-12:], s.typed)
        if idle:
            if scr == last_screen and stable_since is None:
                stable_since = time.time()
            elif scr != last_screen:
                stable_since = None
            last_screen = scr
            if stable_since and time.time() - stable_since > 10:
                if spec["done"](repo):
                    reason = "done"; finished = True; break
                _, texts = read_transcript(transcript_path(repo, start))
                last_text = (texts[-1] if texts else "")[-400:]
                asked = "?" in last_text
                if asked and answered_text < 4:
                    reply = next((r for k, r in spec["text_policy"] if k in last_text.lower()), None)
                    if reply:
                        s.type_text(reply); s.event("text_reply", f"{last_text[-120:]!r} -> {reply}")
                        answered_text += 1; stable_since = None; time.sleep(3); continue
                reason = "idle"; finished = True; break
        else:
            stable_since = None
            last_screen = scr
    s.screen()
    if reason == "limit":
        s.event("limit", "usage window full: restarting this scenario after the window resets")
        s.stop()
        time.sleep(60)
        return drive(model, scenario, out_root)
    tp = transcript_path(repo, start)
    if tp:
        shutil.copy(tp, run_dir / "transcript.jsonl")
    s.stop()
    tools, texts = read_transcript(run_dir / "transcript.jsonl" if tp else None)
    checks = evaluate(scenario, repo, tools, texts, s.events)
    summary = {"model": model, "scenario": scenario, "reason": reason, "seconds": round(time.time() - start),
               "events": s.events, "tools": [n for n, _ in tools], "checks": checks,
               "passed": sum(checks.values()), "total": len(checks), "last_text": (texts[-1] if texts else "")[:800]}
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=1))
    print(f"[{model}] {scenario}: {summary['passed']}/{summary['total']} failed={[k for k, v in checks.items() if not v]} reason={reason} {summary['seconds']}s", flush=True)


def is_go_ahead(q):
    """The plan-shown question: 'go ahead?' in the text, or options that offer both go and stop."""
    labels = [str(o.get("label", "")).lower() for o in q.get("options", [])]
    return "go ahead" in q.get("question", "").lower() or (any(l.startswith("go") for l in labels) and any(l.startswith("stop") for l in labels))


def chosen_review_model(events):
    """The model the runner picked when asked which model runs the review agents, else None."""
    for e in events:
        if e.get("kind") == "ask_answered" and "model" in e.get("detail", "").lower() and " -> " in e["detail"]:
            label = e["detail"].rsplit(" -> ", 1)[1].lower()
            for name in ("opus", "sonnet", "haiku"):
                if name in label:
                    return name
    return None


def review_agents_used(tools, model):
    """Both review agents were started with `model` passed to the Agent tool."""
    calls = [inp for name, inp in tools if name == "Agent" and any(k in str(inp.get("subagent_type", "")) for k in ("verifier", "reviewer"))]
    return model is not None and h.agents_ran(tools) and all(str(inp.get("model", "")).lower() == model for inp in calls)


def evaluate(scenario, repo, tools, texts, events):
    c = {}
    names = [n for n, _ in tools]
    docs = repo / "docs/pm"
    asks = [i for n, i in tools if n == "AskUserQuestion"]
    questions = [q.get("question", "") for a in asks for q in a.get("questions", [])]
    commits = h.git(repo, "rev-list", "--count", "HEAD").stdout.strip()

    def code_edit_index():
        for i, (n, inp) in enumerate(tools):
            if n in ("Edit", "Write", "MultiEdit") and "calc.py" in str(inp.get("file_path", "")):
                return i
            cmd = re.sub(r"[0-9]*>&[0-9]+|[0-9]*&?>+\s*/dev/null", "", str(inp.get("command", "")))
            if n == "Bash" and "calc.py" in cmd and (">" in cmd or "sed -i" in cmd or "tee " in cmd):
                return i
        return None

    if scenario in ("work_plan_mode", "work_merge_ask"):
        t2 = (docs / "tickets/T002-subtract.md").read_text()
        log = h.git(repo, "log", "--all", "--oneline").stdout
        c["skill_invoked"] = any(n == "Skill" and i.get("skill") == "pm:work" for n, i in tools)
        c["claim_committed"] = "claim T002" in log
        c["plan_in_ticket"] = "Approach:" in t2 and len(t2.split("Approach:")[1].split("\n")[0].strip()) > 0
        c["ticket_done"] = "status: done" in t2
        c["merged_to_main"] = "subtract" in h.git(repo, "show", "main:calc.py").stdout
        c["tests_pass"] = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=repo, capture_output=True).returncode == 0
        c["did_not_widen"] = "def multiply" not in (repo / "calc.py").read_text()
        c["asked_review_model"] = any("model" in q.lower() and ("review" in q.lower() or "agent" in q.lower()) for q in questions)
        c["review_agents_ran"] = h.agents_ran(tools)
        c["review_agents_used_chosen_model"] = review_agents_used(tools, chosen_review_model(events))
        if scenario == "work_plan_mode":
            c["entered_plan_mode"] = "EnterPlanMode" in names
            c["exited_plan_mode"] = "ExitPlanMode" in names
            c["plan_has_four_labels"] = all(k in t2 for k in ("Approach:", "Touches:", "Tests first:", "Decisions to record:"))
            c["approved_yes_in_ticket"] = "approved: yes" in t2
            ce = code_edit_index()
            c["no_code_before_approval"] = ce is not None and "ExitPlanMode" in names and ce > names.index("ExitPlanMode")
        else:
            c["asked_before_merge"] = any("merge" in q.lower() for q in questions) or any(e["kind"] == "text_reply" and "merge" in e["detail"].lower() for e in events)
            c["asked_go_ahead"] = any(is_go_ahead(q) for a in asks for q in a.get("questions", []))
    elif scenario == "init_interview":
        c["skill_invoked"] = any(n == "Skill" and i.get("skill") == "pm:init" for n, i in tools)
        c["asked_questions"] = len(asks) >= 3
        c["one_question_at_a_time"] = bool(asks) and all(len(a.get("questions", [])) == 1 for a in asks)
        c["no_deadline_question"] = not any(h.BANNED.search(q) for q in questions)
        c["roadmap_created"] = (docs / "roadmap.md").exists()
        c["epic_created"] = any((docs / "epics").glob("E*.md")) if (docs / "epics").exists() else False
        c["pm_block_in_context"] = (repo / "CONTEXT.md").exists() and "## pm" in (repo / "CONTEXT.md").read_text()
        c["validate_ok"] = h.validate_ok(repo) if (docs / "roadmap.md").exists() else False
        c["not_committed"] = commits == "1"
    elif scenario == "plan_bug_interview":
        new = sorted((docs / "tickets").glob("T008*.md"))
        body = new[0].read_text() if new else ""
        c["skill_invoked"] = any(n == "Skill" and i.get("skill") == "pm:plan" for n, i in tools)
        c["at_most_two_questions"] = len(asks) <= 2
        c["ticket_created"] = bool(new)
        c["is_bug_with_reproduce"] = "bug" in body.lower() and ("reproduc" in body.lower() or "expected" in body.lower())
        c["flow_redrawn"] = any("T008" in e.read_text() for e in (docs / "epics").glob("E*.md"))
        c["validate_ok"] = h.validate_ok(repo, h.LOGIN_ALLOW)
    elif scenario == "grill_interview":
        t8 = (docs / "tickets/T008-remember-me.md").read_text()
        c["skill_invoked"] = any(n == "Skill" and i.get("skill") == "pm:grill" for n, i in tools)
        c["asked_questions"] = 1 <= len(asks) <= 5
        c["one_question_at_a_time"] = bool(asks) and all(len(a.get("questions", [])) == 1 for a in asks)
        c["each_question_has_options"] = bool(asks) and all(len(q.get("options", [])) >= 2 for a in asks for q in a.get("questions", []))
        c["marked_ready"] = "ready: yes" in t8
        acc = t8.split("## Acceptance")[1].split("## ")[0] if "## Acceptance" in t8 else ""
        c["acceptance_sharpened"] = "does something" not in acc and acc.count("- [ ]") >= 1
        c["T009_untouched"] = "ready: no" in (docs / "tickets/T009-remember-me-expiry.md").read_text()
        c["validate_ok"] = h.validate_ok(repo, h.LOGIN_ALLOW)
        c["not_committed"] = commits == "1"
    elif scenario == "brainstorm_session":
        items = h.new_pm_items(repo)
        new_tickets = [(docs / "tickets" / n).read_text() for n in items["tickets"]]
        status = h.git(repo, "status", "--porcelain").stdout
        c["skill_invoked"] = any(n == "Skill" and i.get("skill") == "pm:brainstorm" for n, i in tools)
        c["asked_questions"] = 3 <= len(asks) <= 12
        c["one_question_at_a_time"] = bool(asks) and all(len(a.get("questions", [])) == 1 for a in asks)
        c["each_question_has_options"] = bool(asks) and all(len(q.get("options", [])) >= 2 for a in asks for q in a.get("questions", []))
        c["asked_before_writing"] = any(any(w in q.lower() for w in ("apply", "write", "update")) for q in questions) or \
            any(e["kind"] == "text_reply" and "apply" in e["detail"].lower() for e in events)
        c["proposal_has_why"] = any("why" in t.lower() and "|" in t for t in texts)
        c["wrote_something"] = bool(items["tickets"] or items["epics"] or items["backlog_changed"] or items["decisions_changed"])
        grilled_on_request = any(e["kind"] == "ask_answered" and "grill" in e["detail"].lower() and e["detail"].lower().rsplit(" -> ", 1)[-1].startswith("grill") for e in events)
        c["new_tickets_thin"] = all("ready: no" in t for t in new_tickets) or (grilled_on_request and sum("ready: yes" in t for t in new_tickets) <= 1)
        c["only_docs_changed"] = all(l[3:].startswith("docs/pm/") or l[3:] == "CONTEXT.md" for l in status.splitlines())
        c["validate_ok"] = h.validate_ok(repo, h.LOGIN_ALLOW)
        c["not_committed"] = commits == "1"
    elif scenario == "retro_interview":
        road = (docs / "roadmap.md").read_text()
        m1 = road.split("## M1")[1].split("## M2")[0] if "## M1" in road else ""
        ctx = (repo / "CONTEXT.md").read_text()
        c["skill_invoked"] = any(n == "Skill" and i.get("skill") == "pm:retro" for n, i in tools)
        c["asked_retro_questions"] = len(asks) >= 3
        c["one_question_at_a_time"] = bool(asks) and all(len(a.get("questions", [])) == 1 for a in asks)
        c["retro_block_under_M1"] = "Retro:" in m1 or "retro" in m1.lower()
        c["milestone_now_M2"] = bool(re.search(r"^milestone:\s*M2\s*$", ctx, re.M))
        c["pm_block_still_parses"] = h.pm(repo, "config").returncode == 0
        c["validate_ok"] = h.validate_ok(repo, h.LOGIN_ALLOW)
        c["not_committed"] = commits == "1"
    c["no_time_words_in_docs"] = not any(h.BANNED.search(p.read_text()) for p in docs.rglob("*.md")) if docs.exists() else True
    return c


if __name__ == "__main__":
    args = sys.argv[1:]
    out_root = h.RESULTS / "interactive"
    do_reeval = False
    while args and args[0].startswith("--"):
        if args[0] == "--out":
            out_root = Path(args[1]) if args[1].startswith("/") else h.RESULTS / args[1]
            args = args[2:]
        elif args[0] == "--reeval":
            do_reeval = True
            args = args[1:]
    (reeval if do_reeval else drive)(args[0], args[1], out_root)
