import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CLI = REPO / "scripts" / "pm.py"
FAKE = Path(__file__).resolve().parent / "fake_claude.py"
START_HOOK = REPO / "hooks" / "session-start.sh"


class WorkerSessionTests(unittest.TestCase):
    """`pm.py worker`: each item runs in its own Claude Code session (here a stand-in that records its calls)."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "project"
        self.root.mkdir()
        self.calls = Path(self.temp.name) / "calls.jsonl"
        fake = Path(self.temp.name) / "claude"
        fake.write_text(f"#!/bin/sh\nexec {sys.executable} {FAKE} \"$@\"\n")
        fake.chmod(0o755)
        self.env = dict(os.environ, PM_CLAUDE=str(fake), FAKE_CLAUDE_CALLS=str(self.calls),
                        CLAUDE_CODE_SESSION_ID="coordinator-session")
        for key in ("FAKE_CLAUDE_MODE", "FAKE_CLAUDE_SLEEP", "PM_WORKER", "PM_WORKER_EXTRA_ARGS"):
            self.env.pop(key, None)
        for command in (["git", "init", "-q"], ["git", "config", "user.name", "Test"],
                        ["git", "config", "user.email", "test@example.com"]):
            subprocess.run(command, cwd=self.root, check=True)
        self.cli("init")
        self.item = self.add("Count words", "Add a word count")

    def tearDown(self):
        self.temp.cleanup()

    def cli(self, *args, input_text="", ok=True, env=None):
        result = subprocess.run([sys.executable, str(CLI), *args], cwd=self.root, text=True, input=input_text,
                                capture_output=True, env=env or self.env)
        self.assertEqual(result.returncode == 0, ok, result.stderr + result.stdout)
        return result

    def add(self, title, intent):
        return self.cli("add", input_text=f"{title}\n{intent}").stdout.split(":", 1)[0].split()[-1]

    def calls_made(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []

    def flag(self, call, name):
        argv = call["argv"]
        return argv[argv.index(name) + 1] if name in argv else None

    def ready(self, mode="auto"):
        self.cli("defaults", "--worker-model", "sonnet", "--worker-effort", "medium",
                 "--validator-model", "haiku", "--validator-effort", "low")
        self.cli("worker", "mode", mode)

    # ---- the person's choices are asked, never picked

    def test_start_refuses_until_the_person_chose_defaults_and_a_permission_setting(self):
        refused = self.cli("worker", "start", self.item, input_text="Ari", ok=False)
        self.assertIn("No default model and effort are recorded", refused.stderr)
        self.assertIn("Ask the person once", refused.stderr)
        self.assertIn("do not pick them yourself", refused.stderr)
        self.assertIn("Not recorded yet: workers model, workers effort, validators model, validators effort",
                      self.cli("defaults").stdout)
        self.cli("defaults", "--worker-model", "opus", "--worker-effort", "high",
                 "--validator-model", "inherit", "--validator-effort", "medium")
        config = json.loads((self.root / "docs/pm/config.json").read_text())
        self.assertEqual(config["workers"], {"model": "opus", "effort": "high"})
        self.assertEqual(config["validators"], {"model": "inherit", "effort": "medium"})
        log = subprocess.check_output(["git", "log", "--format=%s", "-1"], cwd=self.root, text=True)
        self.assertIn("pm: Recorded defaults.", log)
        refused = self.cli("worker", "start", self.item, input_text="Ari", ok=False)
        self.assertIn("No permission setting is chosen for worker sessions", refused.stderr)
        self.assertIn("auto (recommended)", refused.stderr)
        self.assertEqual(self.calls_made(), [])
        self.cli("worker", "mode", "acceptEdits")
        self.assertIn("permission setting: acceptEdits", self.cli("worker", "mode").stdout)
        self.assertFalse((self.root / "docs/pm/config.json").read_text().count("acceptEdits"),
                         "the permission setting is the person's, kept in this clone, not committed")

    # ---- each item gets its own session in its own worktree

    def test_start_runs_a_separate_worker_session_in_the_items_own_worktree(self):
        self.ready()
        started = self.cli("worker", "start", self.item, input_text="Ari\nThe person left data.csv here.")
        call = self.calls_made()[0]
        worktree = self.root / ".claude/worktrees" / f"pm-{self.item}"
        self.assertEqual(Path(call["cwd"]).resolve(), worktree.resolve())
        self.assertTrue((worktree / ".git").is_file(), "a git worktree of the project")
        self.assertEqual(self.flag(call, "--agent"), "pm:worker")
        self.assertEqual(self.flag(call, "--model"), "sonnet")
        self.assertEqual(self.flag(call, "--effort"), "medium")
        self.assertEqual(self.flag(call, "--permission-mode"), "auto")
        self.assertEqual(Path(self.flag(call, "--plugin-dir")), REPO)
        self.assertEqual(call["pm_worker"], self.item)
        self.assertIsNone(call["session_env"], "the coordinator's session identity is not passed on")
        prompt = self.flag(call, "-p")
        for line in (f"Item: {self.item}", "Claim under: Ari", "Claim: new claim",
                     "Validator: model haiku, effort low", "The person left data.csv here."):
            self.assertIn(line, prompt)
        session = self.flag(call, "--session-id")
        self.assertIn(f"Started worker session {session}", started.stdout)
        self.assertIn("Report:\nResult: done", started.stdout)
        self.assertIn("Its board commands this turn: claim; validator subagents started: 1.", started.stdout,
                      "read from the worker's own session log, not its report")
        self.assertIn(f"No branch pm/{self.item} with the item on it.", started.stdout)
        self.assertEqual(self.cli("places", "--paths").stdout, "", "the worktree is not a stray file")

    def test_the_persons_model_and_effort_for_one_worker_win_over_the_defaults(self):
        self.ready()
        self.cli("worker", "start", self.item, "--here", "--model", "opus", "--effort", "max",
                 "--validator-model", "sonnet", "--validator-effort", "high", input_text="Ari")
        call = self.calls_made()[0]
        self.assertEqual(Path(call["cwd"]).resolve(), self.root.resolve())
        self.assertEqual((self.flag(call, "--model"), self.flag(call, "--effort")), ("opus", "max"))
        self.assertIn("Validator: model sonnet, effort high", self.flag(call, "-p"))
        self.assertFalse((self.root / ".claude/worktrees").exists())

    def test_two_items_run_in_two_sessions_at_once(self):
        self.ready()
        second = self.add("Count lines", "Add a line count")
        env = dict(self.env, FAKE_CLAUDE_SLEEP="2")
        runs = [subprocess.Popen([sys.executable, str(CLI), "worker", "start", item], cwd=self.root, env=env, text=True,
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                for item in (self.item, second)]
        for run in runs:
            run.stdin.write("Ari")
            run.stdin.close()
        for run in runs:
            self.assertEqual(run.wait(), 0, run.stderr.read())
            run.stdout.close(); run.stderr.close()
        calls = self.calls_made()
        self.assertLess(abs(calls[0]["at"] - calls[1]["at"]), 2, "the second session started while the first ran")
        self.assertEqual({call["pm_worker"] for call in calls}, {self.item, second})
        self.assertEqual(len({self.flag(call, "--session-id") for call in calls}), 2)
        self.assertEqual(len({call["cwd"] for call in calls}), 2)

    # ---- a question comes back and the answer continues the same session

    def test_answer_continues_the_same_session_in_the_same_checkout(self):
        self.ready()
        self.cli("worker", "start", self.item, input_text="Ari")
        first = self.calls_made()[0]
        again = self.cli("worker", "start", self.item, input_text="Ari", ok=False)
        self.assertIn("already has a worker session", again.stderr)
        self.assertIn("worker answer", again.stderr)
        answered = self.cli("worker", "answer", self.item, "--allow", "Bash(npm test:*)",
                            input_text="The owner answered: use the CSV. Saved in the item's notes.")
        resumed = self.calls_made()[1]
        self.assertEqual(self.flag(resumed, "--resume"), self.flag(first, "--session-id"))
        self.assertIsNone(self.flag(resumed, "--agent"), "a resumed session keeps its agent")
        self.assertEqual(resumed["cwd"], first["cwd"])
        self.assertEqual(self.flag(resumed, "--allowedTools"), "Bash(npm test:*)")
        self.assertEqual((self.flag(resumed, "--model"), self.flag(resumed, "--permission-mode")), ("sonnet", "auto"))
        self.assertIn("Seen: The owner answered: use the CSV.", answered.stdout)
        self.cli("worker", "answer", self.item, input_text="Carry on.")
        self.assertEqual(self.flag(self.calls_made()[2], "--allowedTools"), "Bash(npm test:*)", "a grant stays for that worker")
        fresh = self.cli("worker", "start", self.item, "--fresh", "--resume", input_text="Ari")
        self.assertNotEqual(self.flag(self.calls_made()[3], "--session-id"), self.flag(first, "--session-id"))
        self.assertIn("Claim: resume the existing claim", self.flag(self.calls_made()[3], "-p"))
        self.assertIn("Started worker session", fresh.stdout)

    def test_a_refused_permission_is_reported_to_the_coordinator(self):
        self.ready()
        self.cli("worker", "start", self.item, "--here", input_text="Ari")
        reply = self.cli("worker", "answer", self.item, input_text="refuse npm please")
        self.assertIn("Permission was refused for: Bash npm test", reply.stdout)

    def test_auto_mode_unavailable_falls_back_to_accept_edits(self):
        self.ready("auto")
        env = dict(self.env, FAKE_CLAUDE_MODE="default")
        started = self.cli("worker", "start", self.item, "--here", input_text="Ari", env=env)
        self.assertIn("Auto mode was unavailable", started.stdout)
        calls = self.calls_made()
        self.assertEqual([self.flag(call, "--permission-mode") for call in calls], ["auto", "acceptEdits"])
        self.assertNotEqual(self.flag(calls[0], "--session-id"), self.flag(calls[1], "--session-id"))
        self.assertIn("permission setting: acceptEdits", self.cli("worker", "mode").stdout)
        self.assertIn("falls back to acceptEdits", self.cli("worker", "mode").stdout)

    # ---- the coordinator sees each worker, and finds them again after a restart

    def test_workers_shows_what_each_is_doing_or_waiting_on(self):
        self.ready()
        self.assertIn("No worker sessions.", self.cli("worker", "list").stdout)
        env = dict(self.env, FAKE_CLAUDE_SLEEP="3")
        self.cli("worker", "start", self.item, "--no-wait", input_text="Ari", env=env)
        time.sleep(1)
        listing = self.cli("worker", "list").stdout
        self.assertIn(f"- {self.item} Count words: board queued", listing)
        self.assertIn("working: Agent: pm:validator", listing)  # its latest step, not its validator's
        waited = self.cli("worker", "wait", self.item)  # a restarted coordinator reattaches the same way
        self.assertIn("Report:\nResult: done", waited.stdout)
        self.cli("claim", self.item, input_text="Ari")
        self.cli("hold", self.item, input_text="Which file format?")
        listing = self.cli("worker", "list").stdout
        self.assertIn("board waiting, waiting on: Which file format?", listing)
        self.assertIn("turn ended: Result: done", listing)

    def test_stop_and_remove(self):
        self.ready()
        env = dict(self.env, FAKE_CLAUDE_SLEEP="30")
        self.cli("worker", "start", self.item, "--no-wait", input_text="Ari", env=env)
        time.sleep(0.5)
        self.assertIn("still running", self.cli("worker", "remove", self.item, ok=False).stderr)
        self.assertIn("conversation is kept", self.cli("worker", "stop", self.item).stdout)
        self.cli("worker", "remove", self.item)
        self.assertFalse((self.root / ".claude/worktrees" / f"pm-{self.item}").exists())
        self.assertIn("No worker sessions.", self.cli("worker", "list").stdout)

    def test_a_worker_sessions_start_hook_does_not_tell_it_to_stay_hands_off(self):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.root), PM_WORKER=self.item)
        out = subprocess.run(["bash", str(START_HOOK)], cwd=self.root, env=env, input="{}", text=True,
                             capture_output=True, check=True).stdout.strip().splitlines()[-1]
        self.assertIn(f"This is the worker session for board item {self.item}", out)
        self.assertNotIn("Do not edit project files", out)


if __name__ == "__main__":
    unittest.main()
