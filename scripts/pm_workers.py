"""Worker sessions behind `pm.py worker`: each board item is done by its own Claude Code session.

The coordinating session (the one the person talks to) starts a worker with `pm.py worker start`, run as a
background command so Claude Code tells it when the worker's turn ends. A worker is a separate headless
`claude -p` process with its own context, the `pm:worker` agent as its instructions, and its own git worktree
under `.claude/worktrees/pm-<item>/` (a lone worker may run in the person's checkout instead). `pm.py worker
answer` continues the same session with `claude -p --resume`, so a worker that parked its item with a question
picks up where it stopped, context intact.

Each worker's session ID, checkout, settings, and log live in the clone's Git common directory (`pm-workers/`),
next to the board lock, so every worktree and a restarted coordinating session find them; the board items stay
the durable record of the work itself. The permission setting for worker sessions is chosen once per clone by
the person and kept there too; the default model and effort for workers and their validators are the project's,
in `docs/pm/config.json`.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

WORKTREE_DIR = ".claude/worktrees"
WORKTREE_PREFIX = "pm-"
# Recommended first; the person picks once per clone. auto falls back to acceptEdits where it is unavailable.
PERMISSION_MODES = ("auto", "acceptEdits", "default", "bypassPermissions")
RECOMMENDED_MODE = "auto"
FALLBACK_MODE = "acceptEdits"
EFFORTS = ("low", "medium", "high", "xhigh", "max")
# The Agent tool takes these model aliases for a subagent; "inherit" uses the worker session's model.
VALIDATOR_MODELS = ("inherit", "fable", "opus", "sonnet", "haiku")
INIT_WAIT_SECONDS = 90


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def git_common_dir(root: Path) -> Path:
    try:
        out = subprocess.check_output(["git", "-C", str(root), "rev-parse", "--git-common-dir"], text=True,
                                      stderr=subprocess.DEVNULL).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise ValueError("Worker sessions need a Git repository: each runs in its own git worktree.")
    path = Path(out)
    return path if path.is_absolute() else (root / path).resolve()


def state_dir(root: Path) -> Path:
    path = git_common_dir(root) / "pm-workers"
    path.mkdir(parents=True, exist_ok=True)
    return path


def sessions_dir(root: Path) -> Path:
    path = state_dir(root) / "sessions"
    path.mkdir(exist_ok=True)
    return path


def state_path(root: Path, item_id: str) -> Path:
    return sessions_dir(root) / f"{item_id}.json"


def log_path(root: Path, item_id: str) -> Path:
    return sessions_dir(root) / f"{item_id}.log"


def write_json(path: Path, data: dict) -> None:
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def load_state(root: Path, item_id: str) -> dict | None:
    path = state_path(root, item_id)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def save_state(root: Path, state: dict) -> None:
    write_json(state_path(root, state["item"]), state)


def all_states(root: Path) -> list[dict]:
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(sessions_dir(root).glob("*.json"))]


# --- the person's choices -------------------------------------------------------------------------------------

def local_settings(root: Path) -> dict:
    path = state_dir(root) / "settings.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_local_settings(root: Path, settings: dict) -> None:
    write_json(state_dir(root) / "settings.json", settings)


MODE_CHOICES = (
    "No permission setting is chosen for worker sessions in this copy of the project. A worker runs unattended, "
    "so it cannot ask before an edit or a command. Ask the person once which setting to use, then run "
    "`pm.py worker mode MODE`:\n"
    "- auto (recommended): a safety check approves routine edits and commands and blocks risky ones; "
    "falls back to acceptEdits where auto mode is unavailable\n"
    "- acceptEdits: file edits are approved; any command outside the person's allow rules is refused\n"
    "- default: only what the person's allow rules already permit; most work is refused\n"
    "- bypassPermissions: no checks at all\n"
    "Anything refused comes back here as a question, and the person can allow it for that worker.")


def permission_mode(root: Path) -> str:
    mode = local_settings(root).get("permission_mode", "")
    if mode not in PERMISSION_MODES:
        raise ValueError(MODE_CHOICES)
    return mode


def cmd_mode(root: Path, args) -> int:
    settings = local_settings(root)
    if not args.mode:
        mode = settings.get("permission_mode")
        print(f"Worker sessions here run with permission setting: {mode}." if mode else MODE_CHOICES)
        if settings.get("fallback_note"):
            print(settings["fallback_note"])
        return 0
    settings.update(permission_mode=args.mode, chosen_at=now())
    settings.pop("fallback_note", None)
    save_local_settings(root, settings)
    print(f"Worker sessions in this copy of the project now run with permission setting: {args.mode}. "
          "It is kept in this clone only, not committed.")
    return 0


def recorded_defaults(config: dict) -> dict:
    return {role: dict(config.get(role) or {}) for role in ("workers", "validators")}


def missing_defaults(config: dict) -> list[str]:
    found = recorded_defaults(config)
    return [f"{role} {key}" for role in ("workers", "validators") for key in ("model", "effort") if not found[role].get(key)]


def defaults_text(config: dict) -> str:
    found = recorded_defaults(config)
    lines = []
    for role, label in (("workers", "Worker sessions"), ("validators", "Validator subagents")):
        model, effort = found[role].get("model"), found[role].get("effort")
        lines.append(f"{label}: model {model or 'not set'}, effort {effort or 'not set'}.")
    return "\n".join(lines)


# --- processes ------------------------------------------------------------------------------------------------

def alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    stat = Path(f"/proc/{pid}/stat")
    if stat.exists():  # a finished child nobody has waited on yet is a zombie, not running
        try:
            return stat.read_text().rsplit(")", 1)[1].split()[0] != "Z"
        except (OSError, IndexError):
            return True
    return True


def ensure_worktree(root: Path, item_id: str) -> Path:
    """The item's own worktree under .claude/worktrees/, detached at the current commit; reused when it exists."""
    path = root / WORKTREE_DIR / f"{WORKTREE_PREFIX}{item_id}"
    if path.exists():
        if not (path / ".git").exists():
            raise ValueError(f"{path} exists but is not a git worktree; move it aside first.")
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(["git", "-C", str(root), "worktree", "add", "--quiet", "--detach", str(path), "HEAD"],
                            text=True, capture_output=True)
    if result.returncode:
        raise ValueError(result.stderr.strip() or f"git worktree add {path} failed")
    return path


def claude_binary() -> str:
    found = shutil.which(os.environ.get("PM_CLAUDE", "claude"))
    if not found:
        raise ValueError("The `claude` command is not on PATH, so no worker session can start. Install the Claude Code "
                         "CLI, or set PM_CLAUDE to its path.")
    return found


def worker_command(state: dict, prompt: str, plugin_root: Path, resume: bool) -> list[str]:
    command = [claude_binary(), "-p", prompt, "--output-format", "stream-json", "--verbose"]
    if resume:
        command += ["--resume", state["session"]]
    else:
        command += ["--session-id", state["session"], "--agent", "pm:worker", "--name", f"pm worker {state['item']}"]
    # A --plugin-dir copy replaces an installed plugin of the same name, so the worker runs this exact copy.
    command += ["--plugin-dir", str(plugin_root)]
    if state["permission_mode"] != "default":
        command += ["--permission-mode", state["permission_mode"]]
    if state.get("allowed_tools"):
        command += ["--allowedTools", *state["allowed_tools"]]
    command += ["--model", state["model"], "--effort", state["effort"]]
    command += shlex.split(os.environ.get("PM_WORKER_EXTRA_ARGS", ""))  # for evals: e.g. --setting-sources project
    return command


def append_log(root: Path, item_id: str, event: dict) -> None:
    with log_path(root, item_id).open("ab") as log:
        log.write(json.dumps({"type": "pm", "at": now(), **event}).encode() + b"\n")


def spawn(root: Path, state: dict, prompt: str, plugin_root: Path, resume: bool) -> subprocess.Popen:
    env = dict(os.environ, PM_WORKER=state["item"], PM_COORDINATOR_ROOT=str(root))
    # The coordinating session's identity must not pass to the worker as if it were the same session.
    for key in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN",
                "CLAUDE_CODE_SESSION_ATTENDED", "CLAUDE_PID"):
        env.pop(key, None)
    append_log(root, state["item"], {"event": "resume" if resume else "start", "prompt": prompt,
                                     "permission_mode": state["permission_mode"]})
    with log_path(root, state["item"]).open("ab") as log:
        process = subprocess.Popen(worker_command(state, prompt, plugin_root, resume), cwd=state["checkout"], env=env,
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    state.update(pid=process.pid, running=True, turns=state.get("turns", 0) + 1, last_start=now(), exit_code=None)
    save_state(root, state)
    return process


def started_mode(root: Path, item_id: str, process: subprocess.Popen) -> str | None:
    """The permission mode the worker's session reports at startup, or None if it ended or never said."""
    deadline = time.time() + INIT_WAIT_SECONDS
    while time.time() < deadline:
        for event in reversed(turn_events(log_events(root, item_id))):
            if event.get("type") == "system" and event.get("subtype") == "init":
                return event.get("permissionMode")
        if process.poll() is not None:
            return None
        time.sleep(0.5)
    return None


def launch(root: Path, state: dict, prompt: str, plugin_root: Path, resume: bool) -> subprocess.Popen:
    process = spawn(root, state, prompt, plugin_root, resume)
    if state["permission_mode"] != "auto":
        return process
    mode = started_mode(root, state["item"], process)
    if mode in (None, "auto"):
        return process
    # Auto mode is not available to this account or model: fall back to acceptEdits, as the person chose.
    stop_process(process.pid)
    note = (f"Auto mode was unavailable to worker sessions (the session started in {mode} mode), so this copy "
            f"falls back to {FALLBACK_MODE}, as chosen. Change it with `pm.py worker mode MODE`.")
    settings = local_settings(root)
    settings.update(permission_mode=FALLBACK_MODE, fallback_note=note)
    save_local_settings(root, settings)
    append_log(root, state["item"], {"event": "fallback", "from": "auto", "started_as": mode, "to": FALLBACK_MODE})
    print(note, flush=True)
    state["permission_mode"] = FALLBACK_MODE
    if not resume:
        state["session"] = str(uuid.uuid4())  # the stopped run may have saved under the first ID
    return spawn(root, state, prompt, plugin_root, resume)


def stop_process(pid: int) -> None:
    """Stop the worker and what it started (its own process group, where the platform has them)."""
    kill = getattr(os, "killpg", os.kill)
    try:
        kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    for _ in range(20):
        if not alive(pid):
            return
        time.sleep(0.5)
    try:
        kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))
    except ProcessLookupError:
        pass


# --- reading a worker's log -----------------------------------------------------------------------------------

def log_events(root: Path, item_id: str) -> list[dict]:
    path = log_path(root, item_id)
    events = []
    if not path.exists():
        return events
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def turn_events(events: list[dict]) -> list[dict]:
    """Events of the latest start or resume only."""
    starts = [index for index, event in enumerate(events) if event.get("type") == "pm" and event.get("event") in ("start", "resume")]
    return events[starts[-1] + 1:] if starts else events


def last_result(events: list[dict]) -> dict | None:
    results = [event for event in turn_events(events) if event.get("type") == "result"]
    return results[-1] if results else None


def short(text: str, limit: int = 100) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def activity(events: list[dict]) -> str:
    """The worker's latest step, from its own messages (not its validator's)."""
    for event in reversed(turn_events(events)):
        if event.get("type") != "assistant" or event.get("parent_tool_use_id"):
            continue
        for block in reversed(event.get("message", {}).get("content", [])):
            if block.get("type") == "tool_use":
                data = block.get("input", {})
                detail = data.get("description") or data.get("command") or data.get("file_path") or data.get("subagent_type") or ""
                return short(f"{block.get('name')}: {detail}")
            if block.get("type") == "text" and block.get("text", "").strip():
                return short(block["text"])
    return "starting"


def wait_for(root: Path, item_id: str, process: subprocess.Popen | None) -> int:
    if process is not None:
        code = process.wait()
    else:
        while alive((load_state(root, item_id) or {}).get("pid")):
            time.sleep(2)
        result = last_result(log_events(root, item_id))
        code = 0 if result and not result.get("is_error") else 1
    state = load_state(root, item_id)
    state.update(running=False, exit_code=code, last_exit=now())
    save_state(root, state)
    return code


def session_facts(events: list[dict], item_id: str) -> list[str]:
    """What the worker's own session did this turn, read from its log rather than from its report."""
    # The CLI is often called through a shell variable, so match the subcommand next to this item's ID.
    board_command = re.compile(r"\b(claim|hold|resume|validated|finish|correct)\s+[\"']?" + re.escape(item_id) + r"\b([^\n;&|]*)")
    commands, validators = [], 0
    for event in turn_events(events):
        if event.get("type") != "assistant" or event.get("parent_tool_use_id"):
            continue
        for block in event.get("message", {}).get("content", []):
            if block.get("type") != "tool_use":
                continue
            data = block.get("input", {})
            if block.get("name") == "Agent" and data.get("subagent_type") == "pm:validator":
                validators += 1
            elif block.get("name") == "Agent":
                commands.append(f"subagent {data.get('subagent_type') or 'general'}")
            elif block.get("name") == "Bash":
                for name, rest in board_command.findall(data.get("command", "")):
                    verdict = re.search(r"--verdict\s+(pass|findings)", rest)
                    commands.append(f"{name} --verdict {verdict.group(1)}" if verdict else name)
    return [f"Its board commands this turn: {', '.join(commands) or 'none'}; validator subagents started: {validators}."]


def branch_facts(root: Path, item_id: str) -> str:
    """The item as its work branch has it, the state finish and validation leave there."""
    shown = subprocess.run(["git", "-C", str(root), "show", f"pm/{item_id}:docs/pm/items/{item_id}.md"],
                           text=True, capture_output=True)
    if shown.returncode:
        return f"No branch pm/{item_id} with the item on it."
    status = re.search(r'^status: "([^"]*)"', shown.stdout, re.M)
    validation = re.search(r"^Validation: (pass|findings) at ([0-9a-f]{7})[0-9a-f]*", shown.stdout, re.M)
    return (f"On branch pm/{item_id}: status {status.group(1) if status else 'unknown'}; "
            + (f"validation {validation.group(1)} at {validation.group(2)}." if validation else "no validation recorded."))


def report(root: Path, item_id: str) -> str:
    state = load_state(root, item_id)
    events = log_events(root, item_id)
    result = last_result(events)
    lines = [f"Worker session for {item_id} ended its turn (exit {state.get('exit_code')}): session {state['session']}, "
             f"checkout {state['checkout']}, permission setting {state['permission_mode']}."]
    if result is None:
        tail = log_path(root, item_id).read_text(encoding="utf-8", errors="replace").strip().splitlines()[-5:]
        lines.append("It ended without a final report. Last output:")
        lines.extend(short(line, 300) for line in tail)
        return "\n".join(lines)
    denials = result.get("permission_denials") or []
    if denials:
        refused = []
        for denial in denials:
            data = denial.get("tool_input") or {}
            refused.append(short(f"{denial.get('tool_name')} {data.get('command') or data.get('file_path') or ''}".strip(), 160))
        lines.append("Permission was refused for: " + "; ".join(dict.fromkeys(refused)))
    lines.extend(session_facts(events, item_id))
    lines.append(branch_facts(root, item_id))
    lines.append("Report:")
    lines.append(str(result.get("result", "")).strip() or "(empty)")
    return "\n".join(lines)


# --- commands -------------------------------------------------------------------------------------------------

def worker_prompt(state: dict, claim_resume: bool, note: str) -> str:
    claim = "resume the existing claim (claim --resume)" if claim_resume else "new claim"
    where = ("You run in the person's checkout." if not state["own_worktree"]
             else f"You run in your own worktree {state['checkout']}, detached at the coordinating checkout's commit.")
    validator = f"Validator: model {state['validator_model']}, effort {state['validator_effort']}"
    return "\n".join(filter(None, [f"Item: {state['item']}", f"Claim under: {state['person']}", f"Claim: {claim}", where,
                                   validator, note.strip()]))


def cmd_start(root: Path, args, plugin_root: Path, config: dict, person: str, note: str) -> int:
    existing = load_state(root, args.id)
    if existing and existing.get("running") and alive(existing.get("pid")):
        raise ValueError(f"A worker session for {args.id} is already running (pid {existing['pid']}). Wait for it with "
                         f"`pm.py worker wait {args.id}`, or stop it with `pm.py worker stop {args.id}`.")
    if existing and not args.fresh:
        raise ValueError(f"{args.id} already has a worker session ({existing['session']}). Continue it with "
                         f"`pm.py worker answer {args.id}` so it keeps its context, or pass --fresh to start a new one.")
    found = recorded_defaults(config)
    chosen = {"model": args.model or found["workers"].get("model"), "effort": args.effort or found["workers"].get("effort"),
              "validator_model": args.validator_model or found["validators"].get("model"),
              "validator_effort": args.validator_effort or found["validators"].get("effort")}
    unset = [name.replace("_", " ") for name, value in chosen.items() if not value]
    if unset:
        raise ValueError("No default model and effort are recorded for worker sessions and their validators ("
                         + ", ".join(unset) + " missing). Ask the person once, then record them with `pm.py defaults "
                         "--worker-model M --worker-effort E --validator-model M --validator-effort E`; do not pick them "
                         "yourself. A model or effort the person names for this item goes on this start instead.")
    if chosen["validator_model"] not in VALIDATOR_MODELS:
        raise ValueError(f"Validator model must be one of {', '.join(VALIDATOR_MODELS)} (the models a subagent can run on).")
    mode = permission_mode(root)
    checkout = root if args.here else ensure_worktree(root, args.id)
    state = {"item": args.id, "session": str(uuid.uuid4()), "checkout": str(checkout), "person": person,
             "own_worktree": not args.here, "permission_mode": mode, "allowed_tools": [],
             "created": now(), "turns": 0, **chosen}
    if existing:
        append_log(root, args.id, {"event": "fresh", "replaces": existing["session"]})
    process = launch(root, state, worker_prompt(state, args.resume, note), plugin_root, resume=False)
    print(f"Started worker session {state['session']} for {args.id} in {checkout} (pid {process.pid}; model "
          f"{state['model']}, effort {state['effort']}; validator {state['validator_model']}, {state['validator_effort']}).",
          flush=True)
    if args.no_wait:
        return 0
    code = wait_for(root, args.id, process)
    print(report(root, args.id))
    return code


def cmd_answer(root: Path, args, plugin_root: Path, message: str) -> int:
    state = load_state(root, args.id)
    if not state:
        raise ValueError(f"{args.id} has no worker session yet; start one with `pm.py worker start {args.id}`.")
    if state.get("running") and alive(state.get("pid")):
        raise ValueError(f"The worker session for {args.id} is still working; wait for it with `pm.py worker wait {args.id}`.")
    if not Path(state["checkout"]).exists():
        raise ValueError(f"The worker's checkout {state['checkout']} is gone, so its session cannot continue there. "
                         f"Start a fresh one with `pm.py worker start {args.id} --resume --fresh`.")
    for tool in args.allow or []:
        if tool not in state.setdefault("allowed_tools", []):
            state["allowed_tools"].append(tool)
    process = launch(root, state, message, plugin_root, resume=True)
    print(f"Continued worker session {state['session']} for {args.id} (pid {process.pid}).", flush=True)
    if args.no_wait:
        return 0
    code = wait_for(root, args.id, process)
    print(report(root, args.id))
    return code


def cmd_wait(root: Path, args) -> int:
    state = load_state(root, args.id)
    if not state:
        raise ValueError(f"{args.id} has no worker session.")
    code = wait_for(root, args.id, None) if state.get("running") else (state.get("exit_code") or 0)
    print(report(root, args.id))
    return code


def cmd_stop(root: Path, args) -> int:
    state = load_state(root, args.id)
    if not state or not alive(state.get("pid")):
        print(f"No running worker session for {args.id}.")
        return 0
    stop_process(state["pid"])
    state.update(running=False, exit_code=-signal.SIGTERM, last_exit=now())
    save_state(root, state)
    print(f"Stopped the worker session for {args.id}; its conversation is kept, so `pm.py worker answer {args.id}` continues it.")
    return 0


def cmd_list(root: Path, items: dict[str, dict]) -> int:
    states = all_states(root)
    if not states:
        print("No worker sessions.")
        return 0
    for state in states:
        item = items.get(state["item"], {})
        events = log_events(root, state["item"])
        if state.get("running") and alive(state.get("pid")):
            doing = "working: " + activity(events)
        elif state.get("running"):
            doing = f"its process ended unwatched; `pm.py worker wait {state['item']}` prints its report"
        else:
            doing = "turn ended: " + short((last_result(events) or {}).get("result", "no final report"), 160)
        line = f"- {state['item']} {item.get('title', '')}: board {item.get('status', 'not on this board')}"
        if item.get("hold"):
            line += f", waiting on: {short(item['hold'], 160)}"
        line += f"; session {state['session'][:8]}, turn {state.get('turns', 0)}; {doing}"
        print(line)
    return 0


def cmd_remove(root: Path, args) -> int:
    state = load_state(root, args.id)
    if state and alive(state.get("pid")):
        raise ValueError(f"The worker session for {args.id} is still running; stop it first.")
    path = root / WORKTREE_DIR / f"{WORKTREE_PREFIX}{args.id}"
    if path.exists():
        result = subprocess.run(["git", "-C", str(root), "worktree", "remove", str(path)], text=True, capture_output=True)
        if result.returncode:
            raise ValueError((result.stderr.strip() or "git worktree remove failed") + " Commit or discard its changes first.")
    for file in (state_path(root, args.id), log_path(root, args.id)):
        file.unlink(missing_ok=True)
    print(f"Removed {args.id}'s worker worktree and session record; its branch and commits are kept.")
    return 0
