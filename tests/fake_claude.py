#!/usr/bin/env python3
"""A stand-in for the `claude` CLI in worker-session tests: records how it was called and prints stream-json.

FAKE_CLAUDE_CALLS: a file each call appends its argv, cwd, and PM_WORKER to (one JSON line).
FAKE_CLAUDE_MODE: the permission mode it reports at startup instead of the one it was given.
FAKE_CLAUDE_SLEEP: seconds to stay running before it reports.
FAKE_CLAUDE_LINGER: seconds to stay open after its final report, as a session with a wakeup scheduled does.
FAKE_CLAUDE_BACKGROUND: seconds a background task (its validator) keeps running after an early report, before the
    task ends and the session reports again.
"""
import json
import os
import subprocess
import sys
import time

args = sys.argv[1:]


def value(flag):
    return args[args.index(flag) + 1] if flag in args else None


def git(*command):
    return subprocess.run(["git", *command], text=True, capture_output=True).stdout.strip()


with open(os.environ["FAKE_CLAUDE_CALLS"], "a", encoding="utf-8") as calls:
    calls.write(json.dumps({"argv": args, "cwd": os.getcwd(), "pm_worker": os.environ.get("PM_WORKER"),
                            "session_env": os.environ.get("CLAUDE_CODE_SESSION_ID"), "at": time.time(),
                            "pid": os.getpid(), "branch": git("branch", "--show-current"),
                            "head": git("rev-parse", "HEAD")}) + "\n")
session = value("--resume") or value("--session-id")
mode = os.environ.get("FAKE_CLAUDE_MODE") or value("--permission-mode") or "default"
print(json.dumps({"type": "system", "subtype": "init", "session_id": session, "permissionMode": mode}), flush=True)
prompt = value("-p")
print(json.dumps({"type": "assistant", "parent_tool_use_id": None, "message": {"content": [
    {"type": "tool_use", "name": "Bash", "input": {"description": "Claim the item"}}]}}), flush=True)
item = prompt.splitlines()[0].split("Item: ", 1)[-1] if prompt.startswith("Item: ") else ""
if item:  # what a worker's own session does: claim through a shell variable, then start its validator
    print(json.dumps({"type": "assistant", "parent_tool_use_id": None, "message": {"content": [
        {"type": "tool_use", "name": "Bash", "input": {"command": f'printf Ari | "$PM" claim {item}'}},
        {"type": "tool_use", "name": "Agent", "input": {"subagent_type": "pm:validator"}}]}}), flush=True)
    print(json.dumps({"type": "assistant", "parent_tool_use_id": "toolu_validator", "message": {"content": [
        {"type": "tool_use", "name": "Bash", "input": {"command": f"pm.py validated {item} --verdict pass"}}]}}), flush=True)
time.sleep(float(os.environ.get("FAKE_CLAUDE_SLEEP", "0")))
denials = [{"tool_name": "Bash", "tool_input": {"command": "npm test"}}] if "refuse npm" in prompt else []
background = float(os.environ.get("FAKE_CLAUDE_BACKGROUND", "0"))
if background:  # the turn ends with an early report while a background task still runs, then the session goes on
    task = {"task_id": "validator-1", "task_type": "local_agent"}
    print(json.dumps({"type": "system", "subtype": "background_tasks_changed", "tasks": [task]}), flush=True)
    print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "session_id": session,
                      "result": "Validation is still running, so I haven't finished the item yet."}), flush=True)
    time.sleep(background)
    print(json.dumps({"type": "system", "subtype": "background_tasks_changed", "tasks": []}), flush=True)
    print(json.dumps({"type": "system", "subtype": "init", "session_id": session, "permissionMode": mode}), flush=True)
print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "session_id": session,
                  "permission_denials": denials,
                  "result": f"Result: done\nSeen: {prompt.splitlines()[0]}"}), flush=True)
time.sleep(float(os.environ.get("FAKE_CLAUDE_LINGER", "0")))
