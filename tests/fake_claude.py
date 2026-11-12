#!/usr/bin/env python3
"""A stand-in for the `claude` CLI in worker-session tests.

It knows only the interactive surface the plugin uses: `--bg` background sessions, `agents --json`, `stop`, `rm`,
`--resume ID --bg`, and a session a person opens (no `--bg`). It has no print mode: a call with `-p` fails, so a
test that passes proves the plugin never asked for one.

A session is a process that stays open. Each turn it records what it saw, then runs the plugin's own Stop hook
the way Claude Code does; a message the hook hands back (exit 2) becomes its next turn. A session a person opened
runs the SessionStart hook first and takes the ticket it hands over.

FAKE_CLAUDE_HOME: where it keeps its sessions (one JSON each), calls.jsonl (each CLI call) and turns.jsonl (each turn).
FAKE_CLAUDE_SLEEP: seconds a turn takes.
FAKE_CLAUDE_MODE: the permission mode a session reports instead of the one it was given.
FAKE_CLAUDE_BG_FAIL: `--bg` fails with this message, as where background sessions are blocked.
FAKE_CLAUDE_WORK: "finish" makes the first turn do the item's work: join, claim, branch, commit, validated, finish.
    "litter" does the same and leaves an uncommitted file behind.
FAKE_CLAUDE_PERMISSION: the first turn asks the person to allow this (e.g. "Bash npm test") and waits until the
    file approve-<session id> appears in FAKE_CLAUDE_HOME.
FAKE_CLAUDE_BACKGROUND: seconds a background task (its validator) keeps the first turn open after an early message.
"""
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

HOME = Path(os.environ["FAKE_CLAUDE_HOME"])
SESSIONS = HOME / "sessions"
REPO = Path(__file__).resolve().parents[1]
args = sys.argv[1:]


def value(flag, argv=None):
    argv = args if argv is None else argv
    return argv[argv.index(flag) + 1] if flag in argv else None


def git(cwd, *command):
    return subprocess.run(["git", "-C", str(cwd), *command], text=True, capture_output=True).stdout.strip()


def append(name, record):
    HOME.mkdir(parents=True, exist_ok=True)
    with (HOME / name).open("a", encoding="utf-8") as file:
        file.write(json.dumps(record) + "\n")


def alive(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    stat = Path(f"/proc/{pid}/stat")
    return not (stat.exists() and stat.read_text().rsplit(")", 1)[1].split()[0] == "Z")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(spec):
    SESSIONS.mkdir(parents=True, exist_ok=True)
    path = SESSIONS / f"{spec['sessionId']}.json"
    temp = path.with_name(path.name + f".{os.getpid()}.tmp")
    temp.write_text(json.dumps(spec), encoding="utf-8")
    temp.replace(path)


def sessions():
    return [load(path) for path in sorted(SESSIONS.glob("*.json"))] if SESSIONS.exists() else []


def find(job):
    return next((spec for spec in sessions() if spec.get("id") == job or spec["sessionId"] == job), None)


def kill(spec):
    if alive(spec.get("pid")):
        try:
            os.killpg(spec["pid"], signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
        for _ in range(50):
            if not alive(spec["pid"]):
                break
            time.sleep(0.1)
        else:
            os.killpg(spec["pid"], signal.SIGKILL)


# --- a session's own process -----------------------------------------------------------------------------------

def hook(spec, event, payload):
    """Run the plugin's worker hook as Claude Code runs it: (exit code, what it wrote to stderr)."""
    env = dict(os.environ, **spec["env"], CLAUDE_PLUGIN_ROOT=spec["plugin"], CLAUDE_PROJECT_DIR=spec["cwd"],
               CLAUDE_CODE_SESSION_ID=spec["sessionId"])
    payload = {"session_id": spec["sessionId"], "cwd": spec["cwd"], "permission_mode": spec["mode"],
               "transcript_path": spec["transcript"], **payload}
    result = subprocess.run(["bash", str(Path(spec["plugin"]) / "hooks" / "worker.sh"), event], cwd=spec["cwd"], env=env,
                            input=json.dumps(payload), text=True, capture_output=True)
    return result.returncode, result.stderr


def wrote(spec, *tool_uses, sidechain=False):
    with open(spec["transcript"], "a", encoding="utf-8") as transcript:
        transcript.write(json.dumps({"type": "assistant", "isSidechain": sidechain,
                                     "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                                     "message": {"content": [{"type": "tool_use", "name": name, "input": data}
                                                             for name, data in tool_uses]}}) + "\n")


def subagent_model(spec, agent):
    """The model Claude Code runs a plugin subagent on (code.claude.com/docs/en/sub-agents, "Choose a model"): the
    agent's own `model:` (`inherit` is the session's model), else CLAUDE_CODE_SUBAGENT_MODEL, else the session's."""
    session_model = value("--model", spec["argv"]) or "claude-default"
    text = (Path(spec["plugin"]) / "agents" / f"{agent}.md").read_text(encoding="utf-8")
    front = text.split("---", 2)[1] if text.startswith("---") else ""
    declared = next((line.split(":", 1)[1].strip() for line in front.splitlines() if line.startswith("model:")), "")
    if declared:
        return session_model if declared == "inherit" else declared
    return spec["env"].get("CLAUDE_CODE_SUBAGENT_MODEL") or session_model


def ran_validator(spec):
    """A pm:validator subagent's own transcript and meta file, where Claude Code records the model it ran on."""
    folder = Path(spec["transcript"]).with_suffix("") / "subagents"
    folder.mkdir(parents=True, exist_ok=True)
    name, model = f"agent-{uuid.uuid4().hex[:16]}", subagent_model(spec, "validator")
    (folder / f"{name}.meta.json").write_text(json.dumps({"agentType": "pm:validator", "pickedEffortModel": model}))
    (folder / f"{name}.jsonl").write_text(json.dumps({"type": "assistant", "isSidechain": True,
                                                      "message": {"model": model, "content": []}}) + "\n")


def do_the_work(spec, item, prompt, litter):
    """What a worker does for its item, through the real board CLI in its own copy."""
    env = dict(os.environ, **spec["env"], CLAUDE_CODE_SESSION_ID=spec["sessionId"])
    cwd = spec["cwd"]

    def pm(*command, text=""):
        return subprocess.run([sys.executable, str(Path(spec["plugin"]) / "scripts" / "pm.py"), *command], cwd=cwd, env=env,
                              input=text, text=True, capture_output=True, check=True).stdout
    joined = pm("worker", "join", item)
    person = next((line.split(": ", 1)[1] for line in joined.splitlines() if line.startswith("Claim under: ")), "Ari")
    pm("claim", item, text=person)
    main = git(cwd, "worktree", "list", "--porcelain").splitlines()[0].split(" ", 1)[1]
    board = git(main, "branch", "--show-current")  # the claim is on the board's branch: the work starts from there
    if "already made for this copy" in joined:
        subprocess.run(["git", "-C", cwd, "merge", "-q", board], check=True)
    else:
        subprocess.run(["git", "-C", cwd, "switch", "-qc", f"pm/{item}", board], check=True)
    (Path(cwd) / f"{item}.txt").write_text("the work\n")
    subprocess.run(["git", "-C", cwd, "add", f"{item}.txt"], check=True)
    subprocess.run(["git", "-C", cwd, "commit", "-qm", f"{item}: the work"], check=True)
    pm("validated", item, "--verdict", "pass", text="Checked.")
    pm("finish", item, text="Done.")
    if litter:
        (Path(cwd) / "scratch.txt").write_text("not committed\n")
    elif "your own worktree, made for this item" in joined:  # back to its start, so the work branch is free
        subprocess.run(["git", "-C", cwd, "switch", "-q", "--detach", board], check=True)


def run_session(spec):
    """One session's process: its turns, each ending with the plugin's Stop hook."""
    spec["pid"] = os.getpid()
    prompt = spec.pop("prompt", None)
    Path(spec["transcript"]).parent.mkdir(parents=True, exist_ok=True)
    Path(spec["transcript"]).touch()
    save(spec)
    if prompt is None:  # a session the person opened: the plugin may hand it a ticket
        code, handed = hook(spec, "session-start", {"hook_event_name": "SessionStart", "source": "startup"})
        prompt = handed if code == 2 else None
    turn = 0
    while prompt is not None:
        turn += 1
        spec.update(status="busy", state="working")
        spec.pop("waitingFor", None)
        save(spec)
        first = prompt.splitlines()[0] if prompt.strip() else ""
        item = spec["env"].get("PM_WORKER") or (
            first.split("board item ", 1)[1].split()[0].rstrip(":") if "board item " in first else "")
        append("turns.jsonl", {"id": spec.get("id"), "session": spec["sessionId"], "turn": turn, "prompt": prompt,
                               "cwd": spec["cwd"], "pm_worker": spec["env"].get("PM_WORKER"), "pid": os.getpid(),
                               "branch": git(spec["cwd"], "branch", "--show-current"),
                               "head": git(spec["cwd"], "rev-parse", "HEAD"), "at": time.time()})
        if item:  # what a worker's own session does: claim through a shell variable, then start its validator
            wrote(spec, ("Bash", {"command": f'printf Ari | "$PM" claim {item}'}), ("Agent", {"subagent_type": "pm:validator"}))
            wrote(spec, ("Bash", {"command": f"pm.py validated {item} --verdict pass"}), sidechain=True)
            ran_validator(spec)
        time.sleep(float(os.environ.get("FAKE_CLAUDE_SLEEP", "0")))
        asks = os.environ.get("FAKE_CLAUDE_PERMISSION")
        if asks and turn == 1:
            tool, _, command = asks.partition(" ")
            hook(spec, "permission", {"hook_event_name": "PermissionRequest", "tool_name": tool, "tool_input": {"command": command}})
            spec.update(status="waiting", state="blocked", waitingFor="permission prompt")
            save(spec)
            while not (HOME / f"approve-{spec['sessionId']}").exists():
                time.sleep(0.2)
            spec.update(status="busy", state="working")
            spec.pop("waitingFor")
            save(spec)
        work = os.environ.get("FAKE_CLAUDE_WORK")
        if work and turn == 1 and item:
            do_the_work(spec, item, prompt, litter=work == "litter")
        background = float(os.environ.get("FAKE_CLAUDE_BACKGROUND", "0"))
        if background and turn == 1:  # the turn ends early while a background task still runs, then the session goes on
            hook(spec, "stop", {"hook_event_name": "Stop", "stop_hook_active": False,
                                "last_assistant_message": "Validation is still running, so I haven't finished the item yet.",
                                "background_tasks": [{"task_id": "validator-1", "task_type": "local_agent"}]})
            time.sleep(background)
        spec.update(status="idle", state="done")
        save(spec)
        code, handed = hook(spec, "stop", {"hook_event_name": "Stop", "stop_hook_active": False, "background_tasks": [],
                                           "last_assistant_message": f"Result: done\nSeen: {prompt.splitlines()[0]}"})
        prompt = handed if code == 2 else None
    spec.update(status="idle", state="done")
    save(spec)
    while True:  # an open session with nothing to do stays open
        time.sleep(3600)


def new_spec(kind, session=None, job=None):
    session = session or str(uuid.uuid4())
    settings = value("--settings")
    env = json.loads(Path(settings).read_text(encoding="utf-8")).get("env", {}) if settings else {}
    spec = {"sessionId": session, "kind": kind, "cwd": os.getcwd(), "name": value("--name") or "", "startedAt": int(time.time() * 1000),
            "mode": os.environ.get("FAKE_CLAUDE_MODE") or value("--permission-mode") or "default",
            "plugin": value("--plugin-dir") or os.environ.get("FAKE_CLAUDE_PLUGIN") or str(REPO), "env": env, "argv": args,
            "transcript": str(HOME / "transcripts" / f"{session}.jsonl"), "status": "busy", "state": "working"}
    if kind == "background":
        spec["id"] = job or session[:8]
    return spec


def start_background(spec, prompt):
    spec["prompt"] = prompt
    save(spec)
    with (HOME / "sessions.log").open("ab") as log:
        subprocess.Popen([sys.executable, __file__, "--session-run", spec["sessionId"]], cwd=spec["cwd"], stdin=subprocess.DEVNULL,
                         stdout=log, stderr=log, start_new_session=True)
    print(f"backgrounded · {spec['id']}" + (f" · {spec['name']}" if spec["name"] else ""))
    print(f"\n  claude attach {spec['id']}    open in this terminal\n  claude logs {spec['id']}      show recent output")


def main():
    if "--session-run" in args:
        spec = load(SESSIONS / f"{value('--session-run')}.json")
        return run_session(spec)
    kind = args[0] if args and args[0] in ("agents", "stop", "rm") else "resume" if "--resume" in args else \
        "bg" if "--bg" in args else "open"
    append("calls.jsonl", {"kind": kind, "argv": args, "cwd": os.getcwd(), "pm_worker": os.environ.get("PM_WORKER"),
                           "session_env": os.environ.get("CLAUDE_CODE_SESSION_ID"), "at": time.time()})
    if "-p" in args or "--print" in args or "--output-format" in args:
        print("error: print mode is not available on this sign-in", file=sys.stderr)
        return 2
    if kind == "agents":
        listed = []
        for spec in sessions():
            running = alive(spec.get("pid"))
            if not running and spec["kind"] != "background":
                continue
            entry = {key: spec[key] for key in ("id", "cwd", "kind", "startedAt", "sessionId", "name") if key in spec}
            if running:
                entry.update({key: spec[key] for key in ("pid", "status", "waitingFor") if key in spec})
            if spec["kind"] == "background":
                entry["state"] = spec.get("state", "done") if running else "done"
            listed.append(entry)
        print(json.dumps(listed, indent=1))
        return 0
    if kind in ("stop", "rm"):
        spec = find(args[1])
        if not spec:
            print(f"no session {args[1]}", file=sys.stderr)
            return 1
        kill(spec)
        if kind == "rm":
            (SESSIONS / f"{spec['sessionId']}.json").unlink()
            print(f"removed {args[1]}")
        else:
            spec.pop("pid", None)
            save(spec)
            print(f"stopped {args[1]}")
        return 0
    if kind in ("bg", "resume"):
        if os.environ.get("FAKE_CLAUDE_BG_FAIL"):
            print(os.environ["FAKE_CLAUDE_BG_FAIL"], file=sys.stderr)
            return 1
        prompt = value("--bg")
        if kind == "bg":
            start_background(new_spec("background"), prompt)
            return 0
        earlier = find(value("--resume"))
        if earlier and alive(earlier.get("pid")):
            copy = new_spec("background")
            print(f"note: session {earlier.get('id') or earlier['sessionId'][:8]} is already running in the background, so this "
                  f"started a copy as {copy['id']}. `claude attach {earlier.get('id')}` opens the original.")
            start_background(copy, prompt)
            return 0
        if earlier and earlier["kind"] == "background":
            print(f"note: woke session {earlier['id']} with its saved options (--name, --agent, --plugin-dir, --model).")
        woken = new_spec("background", session=value("--resume"), job=(earlier or {}).get("id"))
        woken["name"] = woken["name"] or (earlier or {}).get("name", "")
        start_background(woken, prompt)
        return 0
    return run_session(new_spec("interactive"))  # the person opened a session here


if __name__ == "__main__":
    raise SystemExit(main())
