"""Worker sessions behind `pm.py worker`: each board item is done by its own full Claude Code session.

A worker is an ordinary interactive Claude Code session with its own context: the person can open it, watch it,
and talk to it, and it runs on the sign-in of the app or command line they already use. Nothing here starts a
non-interactive run (print mode, the SDK, or any other headless run). A worker starts in one of three ways, and
all three keep the same record:

- background: `pm.py worker start` runs `claude --bg` in the item's own git worktree
  (`.claude/worktrees/pm-<item>/`, or the person's checkout for a lone worker). `claude attach <id>` opens it.
- app: in the Claude app the coordinating session starts the worker with the app's own session-starting tool
  (`start_session`), giving it the first message `pm.py worker brief` prints. The app makes the copy and the
  branch; the worker's `pm.py worker join` records them.
- handover: where neither works, the person opens a session in the item's worktree and the plugin's
  SessionStart hook hands it the ticket.

The plugin's hooks run inside a worker session: at the end of each turn the Stop hook saves its report in the
record and then listens on the item's mailbox. `pm.py worker answer` continues the same conversation: a background
session is woken with the message as its next prompt (`claude --resume <session> --bg`, also after its process
stopped or its copy was removed); a session that is mid-turn, or one the person opened, takes it from the mailbox.

Each worker's record (session, copy, branch, settings, last report) lives in the clone's Git common directory
(`pm-workers/`), next to the board lock, so every worktree and a restarted coordinating session find it; the board
items stay the durable record of the work itself. The permission setting for worker sessions is chosen once per
clone by the person and kept there too; the default model and effort for workers and their validators are the
project's, in `docs/pm/config.json`.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - exercised on Windows
    fcntl = None
    import msvcrt

WORKTREE_DIR = ".claude/worktrees"
WORKTREE_PREFIX = "pm-"
WORK_BRANCH = "pm/"  # the work branch the plugin makes for an item; a copy the app made keeps the app's branch
# Recommended first; the person picks once per clone. auto falls back to acceptEdits where it is unavailable.
PERMISSION_MODES = ("auto", "acceptEdits", "default", "bypassPermissions")
RECOMMENDED_MODE = "auto"
FALLBACK_MODE = "acceptEdits"
EFFORTS = ("low", "medium", "high", "xhigh", "max")
# The Agent tool starts a subagent by model family; an alias means another model once a new one ships, so the
# person's choices are recorded as exact versions and only the family is derived from them.
MODEL_FAMILIES = ("fable", "opus", "sonnet", "haiku")
MODEL_ALIASES = MODEL_FAMILIES + ("best", "default", "opusplan")
# Tools that schedule a later turn of the same session. A worker's turn ends with its report, so it never gets them.
SCHEDULING_TOOLS = ("ScheduleWakeup", "CronCreate")
# An update replaces the `claude` executable in place, so it can be missing for a few seconds.
CLAUDE_WAIT_SECONDS = 30
BACKGROUND, APP, HANDOVER = "background", "app", "handover"
STARTED = {BACKGROUND: "a background session", APP: "a session the Claude app started",
           HANDOVER: "a session the person opened"}
POLL_SECONDS = 1  # how often a waiting command re-reads the worker's record
SESSIONS_EVERY_SECONDS = 5  # how often it asks `claude agents` what the session is doing
SESSION_WAIT_SECONDS = 20  # how long a new background session may take to appear in that list
GONE_GRACE_SECONDS = 15  # a session that is not running and has not reported for this long has ended without one
SILENT_GRACE_SECONDS = 45  # a session idle this long with no report recorded: its turn ended unrecorded
LISTEN_FRESH_SECONDS = 10  # a mailbox listener that touched its marker this recently is listening
DELIVER_WAIT_SECONDS = 30  # how long a listening session may take to pick a message up
LISTEN_SECONDS = 86000  # a listener gives up just before its hook's 24 hour limit
MAIL_HEADER = "pm mailbox: the coordinating session's next message for board item {item} (not an error: act on it, then report again):"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def short(text: str, limit: int = 100) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


# --- where the records live ------------------------------------------------------------------------------------

def git_out(cwd: Path, *args: str) -> str:
    """A git command's output, or "" when it fails."""
    try:
        result = subprocess.run(["git", "-C", str(cwd), *args], text=True, capture_output=True)
    except (OSError, ValueError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def git_common_dir(root: Path) -> Path:
    try:
        out = subprocess.check_output(["git", "-C", str(root), "rev-parse", "--git-common-dir"], text=True,
                                      stderr=subprocess.DEVNULL).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise ValueError("Worker sessions need a Git repository: each runs in its own git worktree.")
    path = Path(out)
    return path if path.is_absolute() else (root / path).resolve()


def toplevel(path: Path) -> Path | None:
    out = git_out(path, "rev-parse", "--show-toplevel")
    return Path(out) if out else None


def same_path(one, other) -> bool:
    if not one or not other:
        return False
    return os.path.normcase(os.path.realpath(str(one))) == os.path.normcase(os.path.realpath(str(other)))


def main_checkout(root: Path) -> Path:
    """The clone's main checkout: the first entry of `git worktree list`."""
    first = git_out(root, "worktree", "list", "--porcelain").split("\n\n", 1)[0].splitlines()
    if first and first[0].startswith("worktree ") and "bare" not in first:
        return Path(first[0][len("worktree "):])
    return root


def state_dir(root: Path) -> Path:
    path = git_common_dir(root) / "pm-workers"
    path.mkdir(parents=True, exist_ok=True)
    return path


def sessions_dir(root: Path) -> Path:
    path = state_dir(root) / "sessions"
    path.mkdir(exist_ok=True)
    return path


def mail_dir(root: Path) -> Path:
    path = state_dir(root) / "mail"
    path.mkdir(exist_ok=True)
    return path


def state_path(root: Path, item_id: str) -> Path:
    return sessions_dir(root) / f"{item_id}.json"


def log_path(root: Path, item_id: str) -> Path:
    return sessions_dir(root) / f"{item_id}.log"


def settings_path(root: Path, item_id: str) -> Path:
    path = state_dir(root) / "launch"
    path.mkdir(exist_ok=True)
    return path / f"{item_id}.json"


def mail_path(root: Path, item_id: str) -> Path:
    return mail_dir(root) / f"{item_id}.msg"


def listening_path(root: Path, item_id: str) -> Path:
    return mail_dir(root) / f"{item_id}.listening"


def write_json(path: Path, data: dict) -> None:
    temp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    for attempt in range(20):  # on Windows a reader holding the file open makes the replace fail for a moment
        try:
            temp.replace(path)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.05)


def read_json(path: Path) -> dict | None:
    for attempt in range(20):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (PermissionError, json.JSONDecodeError):
            if attempt == 19:
                raise ValueError(f"Cannot read {path}.")
            time.sleep(0.05)
    return None


@contextmanager
def locked(root: Path):
    """One writer at a time: a hook inside a worker session and a coordinator's command both update a record."""
    with (state_dir(root) / "records.lock").open("a+") as lock:
        if fcntl:
            fcntl.flock(lock, fcntl.LOCK_EX)
        else:  # pragma: no cover - exercised on Windows
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
            else:  # pragma: no cover
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def load_state(root: Path, item_id: str) -> dict | None:
    return read_json(state_path(root, item_id))


def save_state(root: Path, state: dict) -> None:
    write_json(state_path(root, state["item"]), state)


def update_state(root: Path, item_id: str, **changes) -> dict | None:
    """Change a record's fields without losing what another process wrote in between; None when it is gone."""
    with locked(root):
        state = load_state(root, item_id)
        if state is None:
            return None
        state.update(changes)
        save_state(root, state)
        return state


def all_states(root: Path) -> list[dict]:
    found = (read_json(path) for path in sorted(sessions_dir(root).glob("*.json")))
    return [state for state in found if state]


def append_log(root: Path, item_id: str, event: dict) -> None:
    with log_path(root, item_id).open("ab") as log:
        log.write(json.dumps({"at": now(), **event}).encode() + b"\n")


def forget(root: Path, item_id: str) -> None:
    for file in (state_path(root, item_id), log_path(root, item_id), settings_path(root, item_id),
                 mail_path(root, item_id), listening_path(root, item_id)):
        try:
            file.unlink()
        except OSError:
            pass


# --- the person's choices -------------------------------------------------------------------------------------

def local_settings(root: Path) -> dict:
    return read_json(state_dir(root) / "settings.json") or {}


def save_local_settings(root: Path, settings: dict) -> None:
    write_json(state_dir(root) / "settings.json", settings)


MODE_CHOICES = (
    "No permission setting is chosen for worker sessions in this copy of the project. A worker is a full Claude "
    "Code session that usually runs with nobody watching: when it needs a permission its setting does not give, it "
    "waits until the person answers in that session. Ask the person once which setting to use, then run "
    "`pm.py worker mode MODE`:\n"
    "- auto (recommended): a safety check approves routine edits and commands and blocks risky ones; "
    "falls back to acceptEdits where auto mode is unavailable\n"
    "- acceptEdits: file edits are approved, but the worker's own `pm.py` and `git` calls wait for the person's yes "
    "in its session: about 5 permission prompts per item, which allow rules do not prevent\n"
    "- default: only what the person's allow rules already permit; every other edit or command waits for their yes\n"
    "- bypassPermissions: no checks at all\n"
    "A worker the Claude app starts takes the app's own permission setting instead.")


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


def model_base(value: str) -> str:
    return re.sub(r"\[[^\]]*\]\s*$", "", str(value).strip()).casefold()


def model_family(value: str) -> str:
    base = model_base(value)
    return next((family for family in MODEL_FAMILIES if family in base), "")


def exact_model(value: str) -> bool:
    """True for an exact Claude model version (claude-sonnet-5-5): it names Claude, a model family, and a version
    number. An alias (sonnet) moves between models, and a mistyped name matches none."""
    base = model_base(value)
    return "claude" in base and bool(model_family(base)) and any(char.isdigit() for char in base)


def check_model(role: str, value: str) -> None:
    """Refuse an alias: the person's worker and validator models are recorded and passed on as exact versions."""
    if role == "validator" and value == "inherit":
        return
    if not exact_model(value):
        raise ValueError(f"The {role} model must be an exact model version such as claude-sonnet-5-5 (Claude, the model "
                         f"family, its version number), not `{value}`: an alias like sonnet or opus means a different "
                         "model once a new one ships. Ask the person which exact version they want"
                         + (", or `inherit` for the worker's model" if role == "validator" else "") + "; do not pick it yourself.")


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


def choices(config: dict, args) -> dict:
    """The model and effort for this worker and its validator: the person's for this item, else the project's."""
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
    for role, key, flag, given in (("worker", "model", "--worker-model", args.model),
                                   ("validator", "validator_model", "--validator-model", args.validator_model)):
        try:
            check_model(role, chosen[key])
        except ValueError as exc:
            raise ValueError(str(exc) + ("" if given else f" Then record it with `pm.py defaults {flag} MODEL`."))
    return chosen


# --- the claude command ---------------------------------------------------------------------------------------

def claude_candidates() -> list[tuple[str, str]]:
    """Where the `claude` executable is looked for, in order: (what it is, the name or path tried)."""
    override = os.environ.get("PM_CLAUDE")
    if override:  # the person's explicit choice is the only place looked
        return [("PM_CLAUDE", override)]
    places = [("`claude` on PATH", "claude")]
    if os.environ.get("CLAUDE_CODE_EXECPATH"):
        places.append(("CLAUDE_CODE_EXECPATH, the Claude Code running this session", os.environ["CLAUDE_CODE_EXECPATH"]))
    home = Path.home()
    places += [("the usual install path", str(home / ".local" / "bin" / "claude")),
               ("the older local install path", str(home / ".claude" / "local" / "claude"))]
    return places


def claude_binary(deadline: float | None = None) -> str:
    """The `claude` executable for worker sessions. An update can remove it for a few seconds, so keep looking
    until the deadline (CLAUDE_WAIT_SECONDS from now by default) before reporting it missing."""
    deadline = time.time() + CLAUDE_WAIT_SECONDS if deadline is None else deadline
    while True:
        for _, tried in claude_candidates():
            found = shutil.which(tried)
            if found:
                return found
        if time.time() >= deadline:
            break
        time.sleep(0.5)
    looked = "; ".join(f"{what} ({tried})" for what, tried in claude_candidates())
    raise ValueError(f"No `claude` executable was found after looking for {CLAUDE_WAIT_SECONDS} seconds, so no worker "
                     f"session can start or continue. Looked for: {looked}. PATH is {os.environ.get('PATH', '')!r}. "
                     "Install the Claude Code CLI, or set PM_CLAUDE to its full path.")


def claude(args: list[str], cwd: Path, wait: float | None = None, timeout: float = 180) -> subprocess.CompletedProcess:
    """Run one `claude` command and return when it does. Every session it starts is a full background session:
    this never passes -p or any other flag that makes Claude Code run without its interface."""
    env = dict(os.environ)
    # The coordinating session's identity must not pass to a worker as if it were the same session.
    for key in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN",
                "CLAUDE_CODE_SESSION_ATTENDED", "CLAUDE_PID", "PM_WORKER"):
        env.pop(key, None)
    deadline = time.time() + (CLAUDE_WAIT_SECONDS if wait is None else wait)
    while True:
        binary = claude_binary(deadline)
        try:
            return subprocess.run([binary, *args], cwd=str(cwd), env=env, stdin=subprocess.DEVNULL, capture_output=True,
                                  text=True, encoding="utf-8", errors="replace", timeout=timeout)
        except subprocess.TimeoutExpired:
            raise ValueError(f"`claude {args[0]}` did not return within {int(timeout)} seconds.")
        except OSError as exc:  # replaced between the lookup and the start: look again until the deadline
            if time.time() >= deadline:
                raise ValueError(f"Could not run `claude` at {binary}: {exc}. Check that it is installed and runs, "
                                 "or set PM_CLAUDE to its full path.")
            time.sleep(0.5)


def sessions_listed(root: Path) -> list[dict] | None:
    """The Claude Code sessions the command line lists on this machine (`claude agents --json --all`): each
    background session with its state, and each open interactive one. None when it cannot say."""
    try:
        result = claude(["agents", "--json", "--all"], root, wait=0, timeout=60)
        listed = json.loads(result.stdout) if result.returncode == 0 else None
    except (ValueError, json.JSONDecodeError):
        return None
    return [entry for entry in listed if isinstance(entry, dict)] if isinstance(listed, list) else None


def session_entry(listed: list[dict] | None, state: dict) -> dict | None:
    """The listed session that is this worker: by its background ID first, which names the entry started last."""
    for key, value in (("id", state.get("job")), ("sessionId", state.get("session"))):
        for entry in listed or []:
            if value and entry.get(key) == value:
                return entry
    return None


def running(entry: dict | None) -> bool:
    """A listed session whose process is running (a stopped background session stays listed without one)."""
    return bool(entry and entry.get("pid"))


def waiting_on_person(entry: dict | None) -> str:
    """What a session is waiting on the person for (a permission prompt, a question), or ""."""
    if not entry:
        return ""
    if entry.get("waitingFor"):
        return str(entry["waitingFor"])
    # An idle session listed as blocked has ended its turn with a question; its report carries it.
    return "the person" if entry.get("status") == "waiting" else ""


# --- the item's copy -------------------------------------------------------------------------------------------

def ensure_worktree(root: Path, item_id: str, base: str) -> Path:
    """The item's own worktree under .claude/worktrees/, detached at the commit new work starts from (the tip of
    the board's branch, whatever the coordinating checkout has checked out); reused when it exists."""
    path = root / WORKTREE_DIR / f"{WORKTREE_PREFIX}{item_id}"
    if path.exists():
        if not (path / ".git").exists():
            raise ValueError(f"{path} exists but is not a git worktree; move it aside first.")
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(["git", "-C", str(root), "worktree", "add", "--quiet", "--detach", str(path), base],
                            text=True, capture_output=True)
    if result.returncode:
        raise ValueError(result.stderr.strip() or f"git worktree add {path} failed")
    return path


def work_branch(state: dict) -> str:
    return state.get("branch") or f"{WORK_BRANCH}{state['item']}"


def restore_copy(root: Path, state: dict) -> str:
    """Put back a copy that was removed when its item finished, on the item's branch, so its session can continue."""
    if not state.get("checkout"):
        return ""
    path = Path(state["checkout"])
    if path.exists():
        return ""
    branch = work_branch(state)
    fresh = f"Start a fresh one with `pm.py worker start {state['item']} --resume --fresh`."
    if not state.get("own_worktree"):
        raise ValueError(f"The worker's checkout {path} is gone, so its session cannot continue there. {fresh}")
    if subprocess.run(["git", "-C", str(root), "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"]).returncode:
        raise ValueError(f"The worker's copy {path} is gone and there is no branch {branch} to put it back on. {fresh}")
    path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(["git", "-C", str(root), "worktree", "add", "--quiet", str(path), branch],
                            text=True, capture_output=True)
    if result.returncode:
        raise ValueError(f"The worker's copy {path} could not be put back on {branch}: {result.stderr.strip()} {fresh}")
    update_state(root, state["item"], copy_removed=False)
    return f"Its copy {path} was put back on {branch}."


def remove_copy(root: Path, state: dict) -> tuple[bool, str]:
    """Remove the item's copy when nothing in it would be lost: (removed or nothing to remove, why it was kept).

    A copy is removed only when it is a worktree of its own, every file in it is committed, and its commits are
    on a branch. The branch and its commits stay. The person's own checkout is never removed.
    """
    if not state.get("checkout") or not state.get("own_worktree"):
        return True, ""
    path = Path(state["checkout"])
    if not path.exists():
        return True, ""
    if same_path(path, main_checkout(root)) or not (path / ".git").is_file():
        return False, "it is not a worktree this command may remove"
    status = subprocess.run(["git", "-C", str(path), "status", "--porcelain"], text=True, capture_output=True)
    if status.returncode:
        return False, status.stderr.strip() or "git could not read its state"
    dirty = [line[3:] for line in status.stdout.splitlines() if line.strip()]
    if dirty:
        shown = ", ".join(dirty[:5]) + (f", and {len(dirty) - 5} more" if len(dirty) > 5 else "")
        return False, f"{len(dirty)} file{'s' if len(dirty) != 1 else ''} in it not committed ({shown})"
    if not git_out(path, "for-each-ref", "--count=1", "--contains", "HEAD", "refs/heads", "refs/remotes"):
        return False, "its latest commits are on no branch"
    removed = subprocess.run(["git", "-C", str(main_checkout(root)), "worktree", "remove", str(path)],
                             text=True, capture_output=True)
    if removed.returncode:
        return False, "git could not remove it (" + short(removed.stderr.strip() or "no reason given", 200) + ")"
    return True, ""


def running_in(checkout: Path) -> str:
    """The item whose worker session is working in this checkout right now, or ""."""
    try:
        states = all_states(checkout)
    except ValueError:
        return ""
    busy = [state for state in states if state.get("state") in ("starting", "working")
            and same_path(state.get("checkout"), checkout)]
    if not busy:
        return ""
    listed = sessions_listed(checkout)
    for state in busy:
        if state["started_by"] != BACKGROUND or listed is None or running(session_entry(listed, state)):
            return state["item"]
    return ""


# --- the ticket ------------------------------------------------------------------------------------------------

def pm_command(plugin_root: Path) -> str:
    python = "python3" if os.name != "nt" else Path(sys.executable).stem  # Windows has `python` or `py`, rarely python3
    return f'{python} "{(plugin_root / "scripts" / "pm.py").as_posix()}"'


def kick_line(state: dict, plugin_root: Path) -> str:
    """A worker's whole first message: one line, enough for any session to find its ticket. It says what the
    person asked for, so the session's permission setting sees their request and not only a command to run."""
    return (f"pm worker session for board item {state['item']}, which the person asked to have done (claim it, build it, "
            f"have it validated, then finish it or park it with a question): run `{pm_command(plugin_root)} worker join "
            f"{state['item']}` first. It records this session as the item's worker and prints your ticket.")


SUBAGENT_MODEL = "CLAUDE_CODE_SUBAGENT_MODEL"  # the session setting that runs its subagents on one exact model


def validator_line(state: dict) -> str:
    """What the worker passes when it starts its validator, said from inside its session. A session the plugin
    started runs its subagents on the exact validator model already; the Agent tool itself takes only a family."""
    model = state["validator_model"]
    if model == "inherit":
        how = "your own model: pass the Agent tool no model"
    elif os.environ.get(SUBAGENT_MODEL) == model:
        how = "this session runs its subagents on it: pass the Agent tool no model"
    else:
        how = f"this session is not set to it: pass the Agent tool the model {model_family(model)}, the nearest it takes"
    return f"Validator: model {model} ({how}), effort {state['validator_effort']}"


def message_text(item_id: str, message: str) -> str:
    return f"Message from the coordinating session for board item {item_id}:\n{message.strip()}"


# --- starting a session ----------------------------------------------------------------------------------------

def new_state(item_id: str, person: str, chosen: dict, **fields) -> dict:
    return {"item": item_id, "started_by": BACKGROUND, "session": "", "job": "", "checkout": "", "own_worktree": False,
            "made_copy": False, "branch": "", "person": person, "permission_mode": "", "created": now(), "turns": 0,
            "state": "starting", "prompted_at": 0, "report": "", "report_at": 0, "facts": "", "needs": "",
            "seen_mode": "", "pending_mail": False, "claim_resume": False, "note": "", **chosen, **fields}


def session_settings(root: Path, state: dict) -> Path:
    """The settings file a worker session is started with: which item it is, the exact model its subagents (its
    validator is the only one) run on, and that it stays in the copy it was started in."""
    # The validator agent names no model of its own, so this setting decides it: the person's exact choice, or for
    # `inherit` the worker's own model, which also keeps a subagent model set elsewhere from taking over.
    env = {"PM_WORKER": state["item"], "PM_COORDINATOR_ROOT": str(root),
           SUBAGENT_MODEL: state["model"] if state["validator_model"] == "inherit" else state["validator_model"]}
    path = settings_path(root, state["item"])
    write_json(path, {"env": env, "worktree": {"bgIsolation": "none"}})
    return path


def session_flags(root: Path, state: dict, plugin_root: Path) -> list[str]:
    """The person's choices for this worker, as `claude` flags: the same for a background start and a handover."""
    # A --plugin-dir copy replaces an installed plugin of the same name, so the worker runs this exact copy.
    # Paths with forward slashes: every shell on Windows takes them, and a person may paste these flags into any.
    flags = ["--name", f"pm worker {state['item']}", "--agent", "pm:worker", "--plugin-dir", plugin_root.as_posix()]
    if state["permission_mode"] != "default":
        flags += ["--permission-mode", state["permission_mode"]]
    return flags + ["--model", state["model"], "--effort", state["effort"],
                    "--settings", session_settings(root, state).as_posix()]


BACKGROUNDED = re.compile(r"backgrounded\W+([0-9a-f]{6,})")  # what `claude --bg` prints; used only when it cannot be listed


def started_sessions(root: Path, state: dict) -> list[dict]:
    """The running background sessions named for this item in its copy, the one started last first."""
    name = f"pm worker {state['item']}"
    found = [entry for entry in sessions_listed(root) or [] if entry.get("name") == name and running(entry)
             and entry.get("id") and same_path(entry.get("cwd"), state["checkout"])]
    return sorted(found, key=lambda entry: entry.get("startedAt") or 0, reverse=True)


def dispatch(root: Path, state: dict, prompt: str, plugin_root: Path, resume: bool = False) -> tuple[bool, str]:
    """Start (or wake) the worker as a full background session: (started, what `claude` said when it did not).

    The record says the turn began before the session exists, and is only added to afterwards: the session's own
    hooks write to it as soon as it runs, and a quick turn can end before this returns.
    """
    item_id = state["item"]
    before = {key: state.get(key) for key in ("state", "prompted_at", "turns", "pending_mail", "needs")}
    update_state(root, item_id, state="working", prompted_at=time.time(), turns=state.get("turns", 0) + 1,
                 pending_mail=False, needs="", background=False)
    args = (["--resume", state["session"]] if resume else []) + ["--bg", prompt, *session_flags(root, state, plugin_root)]
    args += ["--disallowedTools", *SCHEDULING_TOOLS]
    args += shlex.split(os.environ.get("PM_WORKER_EXTRA_ARGS", ""))  # for evals: e.g. --setting-sources project
    try:
        if resume and state.get("job"):
            # Waking a session that is still listed (running or stopped) continues it as a copy under a new ID.
            # Taken off the list first, the same session continues; its conversation is kept either way.
            claude(["stop", state["job"]], root)
            claude(["rm", state["job"]], root)
            stop_listening(root, item_id)
        result = claude(args, Path(state["checkout"]))
        output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
        said = "" if not result.returncode else (
            next((line.strip() for line in output.splitlines() if line.strip()), "") or f"`claude --bg` exited {result.returncode}")
    except ValueError as exc:
        said = str(exc)
    found, worded = [], None
    if not said:  # the session is found by its name in the list, not by how `claude --bg` words its answer
        deadline = time.time() + SESSION_WAIT_SECONDS
        worded = BACKGROUNDED.search(output)
        while not found and time.time() < deadline:
            found = started_sessions(root, state)
            if not found:
                time.sleep(1)
        if not found and not worded:
            said = (next((line.strip() for line in output.splitlines() if line.strip()), "")
                    or f"`claude --bg` started no session named pm worker {item_id}")
    if said:
        state.update(update_state(root, item_id, **before) or {})
        return False, said
    for extra in found[1:]:  # an earlier session Claude Code continued as a copy: the one started last is the worker
        claude(["stop", extra["id"]], root, wait=0)
        claude(["rm", extra["id"]], root, wait=0)
    job = found[0]["id"] if found else worded.group(1)
    session = (found[0].get("sessionId") if found else "") or (state.get("session", "") if state.get("session", "").startswith(job) else "")
    update_state(root, item_id, job=job, session=session)
    state.update(load_state(root, item_id) or {})
    append_log(root, item_id, {"event": "resume" if resume else "start", "job": job, "session": session,
                               "prompt": prompt, "permission_mode": state["permission_mode"]})
    return True, ""


def handover_text(root: Path, state: dict, plugin_root: Path, why: str) -> str:
    """What the person does when no session can be started for them: open one in the item's copy."""
    item, path = state["item"], state["checkout"]
    flags = session_flags(root, state, plugin_root)
    quote = subprocess.list2cmdline if os.name == "nt" else shlex.join
    lines = [f"Could not start {item}'s worker as a background session: {why}" if why else
             f"{item}'s worker is handed over to a session the person opens.",
             f"Its ticket is ready in the item's copy. Ask the person to open a Claude Code session there, one of:",
             f"  terminal, in the folder {path}: claude {quote(flags)}",
             f"  Claude app: a new session in the folder {path}, model {state['model']}",
             "The session gets its first message by itself when it opens. If it sits idle, they paste this one line into it:",
             f"  {kick_line(state, plugin_root)}",
             f"Then run `pm.py worker wait {item}` in the background: it returns when that session's turn ends."]
    return "\n".join(lines)


def close_session(root: Path, state: dict) -> str:
    """Stop a background worker's session and take it off the list; its conversation stays resumable. Returns
    what could not be closed, or ""."""
    if state["started_by"] == BACKGROUND and state.get("job"):
        try:
            claude(["stop", state["job"]], root, wait=0)
            claude(["rm", state["job"]], root, wait=0)
        except ValueError:
            pass
        stop_listening(root, state["item"])
        return ""
    entry = session_entry(sessions_listed(root), state)
    if running(entry) or (state.get("session") and listener_fresh(root, state["item"])):
        return "its session is still open"
    return ""


def refuse_second_session(root: Path, item_id: str, fresh: bool) -> dict | None:
    existing = load_state(root, item_id)
    if not existing:
        return None
    if existing.get("state") in ("starting", "working") and existing["started_by"] == BACKGROUND \
            and running(session_entry(sessions_listed(root), existing)):
        raise ValueError(f"A worker session for {item_id} is already running ({existing.get('job')}). Wait for it with "
                         f"`pm.py worker wait {item_id}`, or stop it with `pm.py worker stop {item_id}`.")
    if not fresh:
        raise ValueError(f"{item_id} already has a worker session ({existing.get('session') or 'not opened yet'}). "
                         f"Continue it with `pm.py worker answer {item_id}` so it keeps its context, or pass --fresh to "
                         "start a new one.")
    still_open = close_session(root, existing)
    if still_open:
        session = existing.get("session") or existing.get("job")
        close_it = ("close it in the Claude app first" if existing["started_by"] == APP else
                    "close it in its open terminal session first" if existing["started_by"] == HANDOVER else
                    f"run `pm.py worker stop {item_id}` first")
        raise ValueError(f"Worker session {session} {still_open}; {close_it}.")
    for file in (mail_path(root, item_id), listening_path(root, item_id)):
        try:
            file.unlink()
        except OSError:
            pass
    append_log(root, item_id, {"event": "fresh", "replaces": existing.get("session")})
    return existing


def cmd_start(root: Path, args, plugin_root: Path, config: dict, person: str, note: str, base: str = "HEAD") -> int:
    refuse_second_session(root, args.id, args.fresh)
    chosen = choices(config, args)
    mode = permission_mode(root)
    here = args.here and not args.handover
    checkout = root if here else ensure_worktree(root, args.id, base)
    state = new_state(args.id, person, chosen, checkout=str(checkout), own_worktree=not here, made_copy=not here,
                      permission_mode=mode, claim_resume=bool(args.resume), note=note,
                      branch=f"{WORK_BRANCH}{args.id}")
    save_state(root, state)
    why = ""
    if not args.handover:
        started, why = dispatch(root, state, kick_line(state, plugin_root), plugin_root)
        if started:
            print(f"Started worker session {state['session'] or state['job']} for {args.id} in {checkout}: a background "
                  f"session, `claude attach {state['job']}` opens it (model {state['model']}, effort {state['effort']}; "
                  f"validator {state['validator_model']}, {state['validator_effort']}).", flush=True)
            return 0 if args.no_wait else finish_turn(root, args.id)
    if here:  # a session the person opens gets the item's own worktree: one opened in their checkout could be any
        checkout = ensure_worktree(root, args.id, base)
        state.update(checkout=str(checkout), own_worktree=True, made_copy=True)
    state.update(started_by=HANDOVER, state="awaiting-session", job="", session="")
    save_state(root, state)
    append_log(root, args.id, {"event": "handover", "why": why})
    print(handover_text(root, state, plugin_root, why), flush=True)
    return 0


def cmd_brief(root: Path, args, plugin_root: Path, config: dict, person: str, note: str) -> int:
    """The app path: the coordinating session starts the worker with the app's own session-starting tool."""
    refuse_second_session(root, args.id, args.fresh)
    chosen = choices(config, args)
    state = new_state(args.id, person, chosen, started_by=APP, state="awaiting-session", permission_mode="the app's",
                      claim_resume=bool(args.resume), note=note)
    save_state(root, state)
    append_log(root, args.id, {"event": "brief"})
    print("\n".join([
        f"Start {args.id}'s worker now with your session-starting tool: `start_session` in the Claude app, or whichever "
        "tool in your list starts a full Claude Code session you can message later. Give it:",
        f"- model: {state['model']} (the exact version from setup; pass it as it is)",
        f"- effort: {state['effort']}, if the tool takes one",
        "- its own copy of the project (a worktree), if the tool makes one; the worker records the copy and branch it got",
        "- first message: this one line, unchanged",
        kick_line(state, plugin_root),
        f"When you are told its turn ended, run `pm.py worker wait {args.id}`. Later messages for it go through "
        f"`pm.py worker answer {args.id}`, which prints what to send it as a follow-up."]))
    return 0


def cmd_join(root: Path, args, plugin_root: Path) -> int:
    """A worker's first step: record this session, its copy, and its branch as the item's worker, and print the ticket."""
    session = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    with locked(root):
        state = load_state(root, args.id)
        if not state:
            raise ValueError(f"{args.id} has no worker ticket in this copy of the project. Worker sessions are started by "
                             "the coordinating session (/pm:work); report this and stop.")
        elsewhere = state.get("checkout") and not same_path(state["checkout"], root)
        if elsewhere and state.get("session") and session and state["session"] != session:
            raise ValueError(f"{args.id} already has a worker session ({state['session']}) in {state['checkout']}; this "
                             "session is not it. Change nothing, report this, and stop.")
        if elsewhere and state["started_by"] != APP:
            raise ValueError(f"{args.id}'s worker runs in its copy {state['checkout']}, not here ({root}). Run this there.")
        own = git_out(root, "rev-parse", "--git-dir") != git_out(root, "rev-parse", "--git-common-dir")
        current = git_out(root, "branch", "--show-current")
        if not state.get("checkout") or elsewhere:  # the copy the app gave this session
            state.update(checkout=str(root), own_worktree=own, made_copy=False)
        made_for_it = state["own_worktree"] and not state.get("made_copy") and bool(current)
        state["branch"] = current if made_for_it else f"{WORK_BRANCH}{args.id}"
        if session:
            state["session"] = session
        if state.get("state") in ("starting", "awaiting-session"):
            state.update(state="working", prompted_at=time.time(), turns=max(state.get("turns", 0), 1))
        save_state(root, state)
    append_log(root, args.id, {"event": "join", "session": session, "checkout": str(root), "branch": state["branch"]})
    if not state["own_worktree"]:
        where = "the person's checkout"
    elif state.get("made_copy"):
        where = "your own worktree, made for this item"
    else:
        where = "your own worktree, made for this session"
    branch = (f"{state['branch']} (already made for this copy: it is the work branch, do not create {WORK_BRANCH}{args.id}; "
              "step 3 brings the claim into it)"
              if made_for_it else f"{state['branch']} (create or switch to it in step 3)")
    claim = "resume the existing claim (claim --resume)" if state.get("claim_resume") else "new claim"
    plugin = plugin_root.as_posix()
    lines = [f"Joined: this session is the worker for {args.id}, not the coordinating session: the session-start note about "
             "not editing project files does not apply to you.",
             f"Instructions: {plugin}/agents/worker.md. If you were not started as the pm:worker agent, read that file now "
             f"and follow it exactly; where it says ${{CLAUDE_PLUGIN_ROOT}}, use {plugin}.",
             f"Item: {args.id}", f"Claim under: {state['person']}",
             f"Claim: {claim}", f"Copy: {root} ({where})", f"Work branch: {branch}", validator_line(state)]
    if state.get("note", "").strip():
        lines.append(state["note"].strip())
    print("\n".join(lines))
    return 0


# --- the mailbox -----------------------------------------------------------------------------------------------

def listener_fresh(root: Path, item_id: str) -> bool:
    """True while a listener of the item's mailbox touched its marker a moment ago."""
    try:
        return time.time() - listening_path(root, item_id).stat().st_mtime < LISTEN_FRESH_SECONDS
    except OSError:
        return False


def listening(root: Path, state: dict, listed: list[dict] | None) -> bool:
    """True while the worker's session is idle and listening for its next message. A background session the
    command line lists as not running is not, whatever marker its last listener left."""
    if state["started_by"] == BACKGROUND and listed is not None and not running(session_entry(listed, state)):
        return False
    return listener_fresh(root, state["item"])


def stop_listening(root: Path, item_id: str) -> None:
    try:
        listening_path(root, item_id).unlink()
    except OSError:
        pass


def listen(root: Path, item_id: str) -> int:
    """Run by the Stop hook of an idle worker session: wait for the item's next message. Printing it to stderr
    and exiting 2 makes Claude Code wake the session with it."""
    token = uuid.uuid4().hex
    marker, box = listening_path(root, item_id), mail_path(root, item_id)
    marker.write_text(token, encoding="utf-8")
    deadline = time.time() + LISTEN_SECONDS
    while time.time() < deadline:
        try:
            mine = marker.read_text(encoding="utf-8") == token
        except OSError:
            mine = False
        if not mine:  # a later turn of this session listens now, or the item's record was removed
            return 0
        if box.exists():
            taken = box.with_name(f"{box.name}.{token}")
            try:
                box.replace(taken)
                text = taken.read_text(encoding="utf-8")
                taken.unlink()
            except OSError:
                time.sleep(0.2)
                continue
            try:
                marker.unlink()
            except OSError:
                pass
            state = load_state(root, item_id) or {}
            update_state(root, item_id, state="working", prompted_at=time.time(), pending_mail=False,
                         turns=state.get("turns", 0) + 1)
            append_log(root, item_id, {"event": "delivered", "message": text})
            sys.stderr.write(MAIL_HEADER.format(item=item_id) + "\n" + text + "\n")
            return 2
        try:
            os.utime(marker)
        except OSError:
            pass
        time.sleep(POLL_SECONDS)
    try:
        marker.unlink()
    except OSError:
        pass
    return 0


def take_back(root: Path, item_id: str) -> bool:
    """Withdraw an undelivered message; False when a listener already took it."""
    box = mail_path(root, item_id)
    try:
        box.replace(box.with_name(box.name + ".withdrawn"))
        box.with_name(box.name + ".withdrawn").unlink()
        return True
    except OSError:
        return False


def post(root: Path, item_id: str, text: str) -> None:
    box = mail_path(root, item_id)
    temp = box.with_name(box.name + ".new")
    temp.write_text(text, encoding="utf-8")
    temp.replace(box)


def cmd_answer(root: Path, args, plugin_root: Path, message: str) -> int:
    state = load_state(root, args.id)
    if not state:
        raise ValueError(f"{args.id} has no worker session yet; start one with `pm.py worker start {args.id}`.")
    restored = restore_copy(root, state)
    if restored:
        print(restored, flush=True)
    text = message_text(args.id, message)
    if state["started_by"] == APP:
        update_state(root, args.id, state="working", prompted_at=time.time(), turns=state.get("turns", 0) + 1)
        append_log(root, args.id, {"event": "follow-up", "message": text})
        print("\n".join([
            f"{args.id}'s worker runs in a session the Claude app started (session {state.get('session') or 'not joined yet'}"
            + (f", copy {state['checkout']}" if state.get("checkout") else "") + "). Send it this as a follow-up message with "
            "your tool that messages a session you started, unchanged:",
            "----- message -----", text, "----- end of message -----",
            f"When you are told its turn ended, run `pm.py worker wait {args.id}`."]))
        return 0
    if state.get("state") == "awaiting-session":
        raise ValueError(f"{args.id}'s worker session has not been opened yet. The person opens one in {state['checkout']}; "
                         f"`pm.py worker wait {args.id}` returns when its turn ends.")
    listed = sessions_listed(root)
    entry = session_entry(listed, state)
    working = state.get("state") in ("starting", "working") and running(entry)
    # An idle background session is woken with the message as its next prompt (below): a prompt carries the
    # person's authority for the session's permission setting, which a message handed over by a hook does not.
    # The mailbox is for a session that cannot be woken that way: one mid-turn, or one the person opened.
    if working or (state["started_by"] != BACKGROUND and listening(root, state, listed)):
        update_state(root, args.id, pending_mail=True)
        post(root, args.id, text)
        if working and not listening(root, state, listed):
            print(f"The worker session for {args.id} is mid-turn; it gets this message as soon as its current turn ends.",
                  flush=True)
            return 0 if args.no_wait else finish_turn(root, args.id)
        deadline = time.time() + DELIVER_WAIT_SECONDS
        while mail_path(root, args.id).exists() and time.time() < deadline:
            time.sleep(0.2)
        if not mail_path(root, args.id).exists() or not take_back(root, args.id):
            print(f"Delivered into the open worker session {state.get('session') or state.get('job')} for {args.id}.", flush=True)
            return 0 if args.no_wait else finish_turn(root, args.id)
        update_state(root, args.id, pending_mail=False)
        entry = session_entry(sessions_listed(root), state)
    # The session is not listening: wake the same conversation as a background session.
    if not state.get("session"):
        raise ValueError(f"{args.id}'s worker has no recorded session to continue. Start a fresh one with "
                         f"`pm.py worker start {args.id} --resume --fresh`.")
    if running(entry) and state["started_by"] != BACKGROUND:
        raise ValueError(f"{args.id}'s worker session is open in {state['checkout']} but is not taking messages. The "
                         "person types the message into it, or closes it; then run this again.")
    state = update_state(root, args.id, started_by=BACKGROUND) or state
    woke, why = dispatch(root, state, text, plugin_root, resume=True)
    if not woke:
        raise ValueError(f"Could not continue {args.id}'s worker session {state['session']}: {why} The person can open it "
                         f"themselves with `claude --resume {state['session']}` in {state['checkout']} and give it the "
                         "message.")
    print(f"Continued worker session {state['session']} for {args.id}: a background session, `claude attach {state['job']}` "
          "opens it.", flush=True)
    return 0 if args.no_wait else finish_turn(root, args.id)


# --- hooks inside a worker session -----------------------------------------------------------------------------

def hook_state(root: Path, payload: dict, bind_handover: bool = False) -> dict | None:
    """The record of the worker this session is, or None for any other session."""
    session = str(payload.get("session_id") or os.environ.get("CLAUDE_CODE_SESSION_ID") or "")
    named = os.environ.get("PM_WORKER", "")
    states = all_states(root)
    found = next((state for state in states if session and state.get("session") == session), None)
    if not found:
        top = toplevel(Path(str(payload.get("cwd") or root))) or root
        found = next((state for state in states if named and state["item"] == named
                      and same_path(state.get("checkout"), top)), None)
        if not found and bind_handover:
            found = next((state for state in states if state["started_by"] == HANDOVER and not state.get("session")
                          and same_path(state.get("checkout"), top)), None)
        if found and session:
            found = update_state(root, found["item"], session=session)
    return found


BOARD_COMMAND = r"\b(claim|hold|resume|validated|finish|correct)\s+[\"']?{item}\b([^\n;&|]*)"


def validator_models(path: str, since: float) -> list[str]:
    """The model each pm:validator subagent started this turn ran on, as Claude Code recorded it: its replies in the
    subagent's own transcript (`<session>/subagents/agent-*.jsonl`), else the model its `.meta.json` names."""
    models = []
    folder = Path(path).with_suffix("") / "subagents" if path else None
    metas = sorted(folder.glob("*.meta.json"), key=lambda found: found.stat().st_mtime) if folder and folder.is_dir() else []
    for meta_path in metas:
        meta = read_json(meta_path) or {}
        log = meta_path.with_name(meta_path.name[:-len(".meta.json")] + ".jsonl")
        if meta.get("agentType") != "pm:validator" or (log if log.exists() else meta_path).stat().st_mtime < since - 1:
            continue
        ran = ""
        try:
            for line in log.read_text(encoding="utf-8", errors="replace").splitlines() if log.exists() else []:
                event = json.loads(line)
                message = event.get("message") if event.get("type") == "assistant" else None
                if isinstance(message, dict) and message.get("model"):
                    ran = message["model"]
                    break
        except (OSError, ValueError, AttributeError):
            pass
        models.append(ran or str(meta.get("pickedEffortModel") or "unknown"))
    return models


def transcript_facts(path: str, item_id: str, since: float, chosen: str = "") -> str:
    """What the worker's own session did this turn, read from its transcript rather than from its report. `chosen`
    is the exact model its validator should run on; one that ran on another model is named, so a mismatch shows."""
    board_command = re.compile(BOARD_COMMAND.format(item=re.escape(item_id)))
    commands, validators = [], 0
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except (OSError, TypeError):
        return ""
    for line in lines:
        try:
            event = json.loads(line)
            if event.get("type") != "assistant" or event.get("isSidechain"):
                continue
            stamp = str(event.get("timestamp") or "")
            if stamp and datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp() < since - 1:
                continue
            blocks = event.get("message", {}).get("content", [])
        except (ValueError, AttributeError):
            continue
        for block in blocks if isinstance(blocks, list) else []:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            data = block.get("input") or {}
            if block.get("name") in ("Agent", "Task") and data.get("subagent_type") == "pm:validator":
                validators += 1
            elif block.get("name") in ("Agent", "Task"):
                commands.append(f"subagent {data.get('subagent_type') or 'general'}")
            elif block.get("name") in ("Bash", "PowerShell"):
                # The CLI is often called through a shell variable, so match the subcommand next to this item's ID.
                for name, rest in board_command.findall(str(data.get("command", ""))):
                    verdict = re.search(r"--verdict\s+(pass|findings)", rest)
                    commands.append(f"{name} --verdict {verdict.group(1)}" if verdict else name)
    text = f"Its board commands this turn: {', '.join(commands) or 'none'}; validator subagents started: {validators}"
    ran = validator_models(path, since)
    if ran:
        text += f", ran on {', '.join(ran)}"
        if chosen and any(model != chosen for model in ran):
            text += f" (not the chosen validator model {chosen})"
    return text + "."


def cmd_hook(root: Path, event: str, payload: dict, plugin_root: Path, places_block) -> int:
    """Called by the plugin's hooks in every session; does nothing unless the session is a worker's."""
    if event == "whoami":
        state = hook_state(root, payload, bind_handover=False)
        if not state:
            top = toplevel(Path(str(payload.get("cwd") or root))) or root
            state = next((found for found in all_states(root) if found["started_by"] == HANDOVER
                          and found.get("state") == "awaiting-session" and same_path(found.get("checkout"), top)), None)
        if state:
            print(state["item"])
        return 0
    state = hook_state(root, payload, bind_handover=event == "session-start")
    if not state:
        return 0
    item_id, mode = state["item"], str(payload.get("permission_mode") or state.get("seen_mode") or "")
    if event == "session-start":
        if state["started_by"] != HANDOVER or state.get("state") != "awaiting-session":
            return 0
        update_state(root, item_id, state="working", prompted_at=time.time(), turns=1)
        append_log(root, item_id, {"event": "handed", "session": state.get("session")})
        sys.stderr.write(kick_line(state, plugin_root) + "\n")
        return 2  # wakes the session the person opened with its ticket, nothing typed
    if event == "permission":
        data = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
        detail = data.get("command") or data.get("file_path") or data.get("path") or ""
        update_state(root, item_id, needs=short(f"{payload.get('tool_name') or 'a tool'} {detail}".strip(), 200),
                     seen_mode=mode)
        return 0
    if event != "stop":
        return 0
    text = str(payload.get("last_assistant_message") or "").strip()
    if payload.get("background_tasks") or places_block():
        # Not the end of its turn: a background task (its validator) wakes it again, or the places check sends it back.
        update_state(root, item_id, interim=text, seen_mode=mode, background=bool(payload.get("background_tasks")))
        return 0
    chosen = state.get("model", "") if state.get("validator_model") == "inherit" else state.get("validator_model", "")
    facts = transcript_facts(str(payload.get("transcript_path") or ""), item_id, float(state.get("prompted_at") or 0), chosen)
    state = update_state(root, item_id, state="reported", report=text, report_at=time.time(), facts=facts,
                         seen_mode=mode, needs="", interim="", background=False)
    append_log(root, item_id, {"event": "report", "report": text})
    if not state or state["started_by"] == APP:  # the app tells the coordinating session itself and carries its follow-ups
        return 0
    return listen(root, item_id)


# --- waiting for a turn and reading its report -----------------------------------------------------------------

def turn_ended(state: dict) -> bool:
    return (state.get("state") == "reported" and not state.get("pending_mail")
            and float(state.get("report_at") or 0) >= float(state.get("prompted_at") or 0))


def wait_for(root: Path, item_id: str) -> str:
    """Wait until the worker's turn has ended, or it needs the person, or its session is gone. Returns which:
    reported, needs-you, ended, silent, stopped, app, or removed."""
    asked, gone_since, idle_since, seen_running = 0.0, None, None, False
    while True:
        state = load_state(root, item_id)
        if state is None:
            return "removed"
        if state["started_by"] == APP:
            return "reported" if turn_ended(state) else "app"
        if turn_ended(state):
            return "reported"
        if state.get("state") in ("stopped", "finished"):
            return "stopped"
        if state.get("state") != "awaiting-session" and time.time() - asked >= SESSIONS_EVERY_SECONDS:
            listed, asked = sessions_listed(root), time.time()
            entry = session_entry(listed, state)
            if waiting_on_person(entry):
                return "needs-you"
            seen_running = seen_running or running(entry)
            # Only a background session, or one this command saw running, is known to be gone when it is not listed:
            # a session the person opened in the Claude app may never be on the command line's list.
            if listed is not None and not running(entry) and (state["started_by"] == BACKGROUND or seen_running):
                gone_since = gone_since or time.time()
                if time.time() - gone_since >= GONE_GRACE_SECONDS:
                    return "ended"
            else:
                gone_since = None
            if running(entry) and entry.get("status") == "idle" and not state.get("pending_mail") \
                    and not state.get("background"):
                idle_since = idle_since or time.time()
                if time.time() - idle_since >= SILENT_GRACE_SECONDS:
                    return "silent"
            else:
                idle_since = None
        time.sleep(POLL_SECONDS)


def branch_facts(root: Path, state: dict) -> tuple[str, bool]:
    """The item as its work branch has it, the state finish and validation leave there, and whether it is Done."""
    item_id, branch = state["item"], work_branch(state)
    shown = subprocess.run(["git", "-C", str(root), "show", f"{branch}:docs/pm/items/{item_id}.md"],
                           text=True, capture_output=True)
    if shown.returncode:
        return f"No branch {branch} with the item on it.", False
    status = re.search(r'^status: "([^"]*)"', shown.stdout, re.M)
    validation = re.search(r"^Validation: (pass|findings) at ([0-9a-f]{7})[0-9a-f]*", shown.stdout, re.M)
    done = bool(status and status.group(1) == "done" and validation and validation.group(1) == "pass")
    return (f"On branch {branch}: status {status.group(1) if status else 'unknown'}; "
            + (f"validation {validation.group(1)} at {validation.group(2)}." if validation else "no validation recorded.")), done


def how_to_open(state: dict) -> str:
    if state["started_by"] == BACKGROUND and state.get("job"):
        return f"`claude attach {state['job']}` opens it"
    if state["started_by"] == APP:
        return "it is in the Claude app's session list"
    return f"it is the session open in {state.get('checkout')}"


def auto_fallback(root: Path, state: dict) -> str:
    """Auto mode chosen but not available to this account or model: later workers fall back to acceptEdits."""
    seen = state.get("seen_mode")
    if state.get("permission_mode") != "auto" or not seen or seen == "auto":
        return ""
    note = (f"Auto mode was unavailable to worker sessions (this one runs in {seen} mode and asks the person in its own "
            f"session for what that does not allow), so this copy falls back to {FALLBACK_MODE} for the next ones, as "
            "chosen. Change it with `pm.py worker mode MODE`.")
    settings = local_settings(root)
    if settings.get("permission_mode") == "auto":
        settings.update(permission_mode=FALLBACK_MODE, fallback_note=note)
        save_local_settings(root, settings)
        append_log(root, state["item"], {"event": "fallback", "from": "auto", "started_as": seen, "to": FALLBACK_MODE})
    return note


def report(root: Path, item_id: str, outcome: str) -> tuple[str, bool]:
    """What the coordinating session reads when a worker's turn ends, and whether the item is Done on its branch."""
    state = load_state(root, item_id)
    if state is None:
        return f"{item_id} has no worker session any more.", False
    session = state.get("session") or "not opened yet"
    where = f"session {session}, {STARTED[state['started_by']]}"
    if state.get("checkout"):
        where += f", copy {state['checkout']}"
    where += f", permission setting {state.get('seen_mode') or state.get('permission_mode')}"
    facts, done = branch_facts(root, state)
    text = str(state.get("report") or "").strip()
    if outcome == "needs-you":
        entry = session_entry(sessions_listed(root), state)
        what = waiting_on_person(entry) or "the person"
        asks = f" for {state['needs']}" if state.get("needs") and "permission" in what else ""
        lines = [f"Worker session for {item_id} is waiting on {what}{asks}"
                 + f": {where}. Only the person can answer it, in that session ({how_to_open(state)}). Tell them what it "
                 f"asks; once they have answered, run `pm.py worker wait {item_id}` again."]
    elif outcome == "awaiting":
        lines = [f"Worker session for {item_id} has not been opened yet: {where}."]
    elif outcome == "app":
        lines = [f"Worker session for {item_id} runs in the Claude app, which tells you when its turn ends and carries its "
                 f"report: {where}. No report of its latest turn is recorded here."]
    elif outcome in ("ended", "silent", "stopped"):
        why = {"ended": "is no longer running and left no final report",
               "silent": "is idle, but no report of its turn was recorded (the plugin's Stop hook did not run in it)",
               "stopped": "is stopped"}[outcome]
        lines = [f"Worker session for {item_id} {why}: {where}. `pm.py worker answer {item_id}` continues it with a message; "
                 f"{how_to_open(state)}."]
        text = text or str(state.get("interim") or "").strip()
    else:
        lines = [f"Worker session for {item_id} ended its turn: {where}; {how_to_open(state)}."]
    fallback = auto_fallback(root, state)
    if fallback:
        lines.append(fallback)
    if state.get("facts") and outcome == "reported":
        lines.append(state["facts"])
    lines.append(facts)
    if text:
        lines += ["Report:" if outcome == "reported" else "Its last message:", text]
    return "\n".join(lines), done


def tidy(root: Path, item_id: str) -> str:
    """Once an item is Done on its branch: close its worker's session and remove its copy, when nothing is lost."""
    state = load_state(root, item_id)
    if not state or state.get("state") == "finished":
        return ""
    branch = work_branch(state)
    kept = close_session(root, state)
    removed, why = (False, kept) if kept else remove_copy(root, state)
    update_state(root, item_id, state="finished", copy_removed=bool(removed and state.get("own_worktree")))
    append_log(root, item_id, {"event": "tidy", "removed": removed, "why": why})
    if not state.get("own_worktree") or not state.get("checkout"):
        return (f"{item_id} is Done on {branch}" + ("; its worker session was closed." if state["started_by"] == BACKGROUND
                                                     else "."))
    if removed:
        return (f"{item_id} is Done on {branch}, so its copy {state['checkout']} was removed"
                + (" and its worker session closed" if state["started_by"] == BACKGROUND else "")
                + f"; {branch} keeps the commits for review and merge. `pm.py worker answer {item_id}` still reaches that "
                "session: the copy comes back for it."
                + (" The session stays in the Claude app's list until the person archives it there."
                   if state["started_by"] == APP else ""))
    return (f"{item_id} is Done on {branch}, but its copy {state['checkout']} was kept: {why}. Once that is settled, "
            f"`pm.py worker remove {item_id}` removes it.")


def finish_turn(root: Path, item_id: str) -> int:
    """Wait for the worker's turn, print its report, and tidy up when the item is Done."""
    outcome = wait_for(root, item_id)
    if outcome == "removed":
        print(f"{item_id}'s worker session record was removed while waiting.")
        return 1
    text, done = report(root, item_id, outcome)
    print(text, flush=True)
    if done and outcome != "needs-you":
        print(tidy(root, item_id), flush=True)
    return 1 if outcome in ("ended", "silent") and not done else 0


def cmd_wait(root: Path, args) -> int:
    state = load_state(root, args.id)
    if not state:
        raise ValueError(f"{args.id} has no worker session.")
    if state.get("state") == "finished":
        text, _ = report(root, args.id, "reported")
        print(text)
        return 0
    return finish_turn(root, args.id)


def cmd_stop(root: Path, args) -> int:
    state = load_state(root, args.id)
    entry = session_entry(sessions_listed(root), state) if state else None
    if not state or not running(entry):
        print(f"No running worker session for {args.id}.")
        return 0
    if state["started_by"] != BACKGROUND:
        raise ValueError(f"{args.id}'s worker is {STARTED[state['started_by']]} ({how_to_open(state)}); only the person can "
                         "close it, there.")
    claude(["stop", state["job"]], root, wait=0)
    update_state(root, args.id, state="stopped", pending_mail=False)
    take_back(root, args.id)
    stop_listening(root, args.id)
    append_log(root, args.id, {"event": "stop"})
    print(f"Stopped the worker session for {args.id}; its conversation is kept, so `pm.py worker answer {args.id}` continues it.")
    return 0


def doing(root: Path, state: dict, listed: list[dict] | None) -> str:
    entry = session_entry(listed, state)
    kind = state.get("state")
    if kind == "awaiting-session":
        return ("waiting for the app to start it" if state["started_by"] == APP
                else f"waiting for the person to open a session in {state['checkout']}")
    if kind == "finished":
        return "finished" + ("; its copy was removed" if state.get("copy_removed") else "")
    if waiting_on_person(entry):
        what = waiting_on_person(entry)
        return (f"waiting on {what}" + (f" for {state['needs']}" if state.get("needs") and "permission" in what else "")
                + f", in its own session ({how_to_open(state)})")
    if turn_ended(state):
        ended = "turn ended: " + short(state.get("report") or "no final report", 160)
        if branch_facts(root, state)[1]:  # Done on its branch, but nothing has tidied it yet
            ended += (f"; it is Done on its branch: run `pm.py worker wait {state['item']}` to close its session and "
                      "remove its copy")
        return ended
    if kind == "stopped":
        return "stopped; `pm.py worker answer` continues it"
    if state["started_by"] == BACKGROUND and listed is not None and not running(entry):
        return f"its session is not running; `pm.py worker wait {state['item']}` says how it ended"
    return "working" + (" (a message waits for the end of its turn)" if state.get("pending_mail") else "")


def prune(root: Path, items: dict[str, dict]) -> None:
    """Drop the records of finished workers whose item is Done on the board and whose copy is gone: nothing is left to continue."""
    for state in all_states(root):
        gone = not state.get("checkout") or not state.get("own_worktree") or not Path(state["checkout"]).exists()
        if state.get("state") == "finished" and gone and items.get(state["item"], {"status": "done"}).get("status") == "done":
            forget(root, state["item"])


def cmd_list(root: Path, items: dict[str, dict]) -> int:
    prune(root, items)
    states = all_states(root)
    if not states:
        print("No worker sessions.")
        return 0
    listed = sessions_listed(root)
    for state in states:
        item = items.get(state["item"], {})
        line = f"- {state['item']} {item.get('title', '')}: board {item.get('status', 'not on this board')}"
        if item.get("hold"):
            line += f", waiting on: {short(item['hold'], 160)}"
        session = (state.get("job") or state.get("session") or "")[:8] or "not opened yet"
        line += f"; {STARTED[state['started_by']]} ({session}), turn {state.get('turns', 0)}; {doing(root, state, listed)}"
        print(line)
    return 0


def cmd_remove(root: Path, args) -> int:
    state = load_state(root, args.id)
    if not state:  # no record: a worktree left by an earlier version is still this item's copy
        state = {"item": args.id, "started_by": HANDOVER, "own_worktree": True, "made_copy": True,
                 "checkout": str(root / WORKTREE_DIR / f"{WORKTREE_PREFIX}{args.id}")}
    elif state["started_by"] == BACKGROUND and state.get("state") in ("starting", "working") \
            and running(session_entry(sessions_listed(root), state)):
        raise ValueError(f"The worker session for {args.id} is still running; stop it first (`pm.py worker stop {args.id}`).")
    kept = close_session(root, state)
    removed, why = (False, kept) if kept else remove_copy(root, state)
    if not removed:
        raise ValueError(f"{args.id}'s copy {state['checkout']} was kept: {why}. Commit or discard what is there"
                         + (", or close the session in it," if kept else "") + " then run this again.")
    forget(root, args.id)
    print(f"Removed {args.id}'s worker session record"
          + (f" and its copy {state['checkout']}" if state.get("own_worktree") and state.get("checkout") else "")
          + "; its branch and commits are kept.")
    return 0
