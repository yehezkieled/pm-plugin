import contextlib
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
CLI = REPO / "scripts" / "pm.py"
FAKE = Path(__file__).resolve().parent / "fake_claude.py"
START_HOOK = REPO / "hooks" / "session-start.sh"
WORKER_HOOK = REPO / "hooks" / "worker.sh"
SESSION_STARTS = ("bg", "resume")

sys.path.insert(0, str(REPO / "scripts"))
import pm  # noqa: E402
import pm_workers  # noqa: E402


def stop_group(pid):
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


class WorkerSessionTests(unittest.TestCase):
    """`pm.py worker`: each item runs in its own full Claude Code session (here a stand-in that keeps a session
    open, runs the plugin's real hooks at the end of each turn, and has no print mode)."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "project"
        self.root.mkdir()
        self.home = Path(self.temp.name) / "claude-home"
        fake = Path(self.temp.name) / "claude"
        fake.write_text(f"#!/bin/sh\nexec {sys.executable} {FAKE} \"$@\"\n")
        fake.chmod(0o755)
        self.env = dict(os.environ, PM_CLAUDE=str(fake), FAKE_CLAUDE_HOME=str(self.home),
                        CLAUDE_CODE_SESSION_ID="coordinator-session")
        for key in ("FAKE_CLAUDE_MODE", "FAKE_CLAUDE_SLEEP", "FAKE_CLAUDE_BG_FAIL", "FAKE_CLAUDE_BACKGROUND", "FAKE_CLAUDE_WORK",
                    "FAKE_CLAUDE_PERMISSION", "PM_WORKER", "PM_WORKER_EXTRA_ARGS", "CLAUDE_CODE_EXECPATH", "CLAUDE_PROJECT_DIR",
                    "CLAUDE_PLUGIN_ROOT"):
            self.env.pop(key, None)
        for command in (["git", "init", "-q"], ["git", "config", "user.name", "Test"],
                        ["git", "config", "user.email", "test@example.com"]):
            subprocess.run(command, cwd=self.root, check=True)
        self.addCleanup(self.close_sessions)
        self.cli("init")
        self.item = self.add("Count words", "Add a word count")

    def close_sessions(self):
        for session in self.sessions():
            if session.get("pid"):
                stop_group(session["pid"])
        self.temp.cleanup()

    def cli(self, *args, input_text="", ok=True, env=None, cwd=None):
        result = subprocess.run([sys.executable, str(CLI), *args], cwd=cwd or self.root, text=True, input=input_text,
                                capture_output=True, env=env or self.env)
        self.assertEqual(result.returncode == 0, ok, result.stderr + result.stdout)
        return result

    def add(self, title, intent):
        return self.cli("add", input_text=f"{title}\n{intent}").stdout.split(":", 1)[0].split()[-1]

    def cli_here(self, *args, input_text="", env=None, **constants):
        """The CLI in this process, so a test can shorten the waits it would otherwise sit through."""
        out, err, cwd = io.StringIO(), io.StringIO(), os.getcwd()
        patches = [mock.patch.object(pm_workers, name, value) for name, value in constants.items()]
        with contextlib.ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            stack.enter_context(mock.patch.dict(os.environ, env or self.env, clear=True))
            stack.enter_context(mock.patch.object(sys, "argv", ["pm.py", *args]))
            stack.enter_context(mock.patch.object(sys, "stdin", io.StringIO(input_text)))
            stack.enter_context(contextlib.redirect_stdout(out))
            stack.enter_context(contextlib.redirect_stderr(err))
            os.chdir(self.root)
            try:
                code = pm.main()
            finally:
                os.chdir(cwd)
        return code, out.getvalue(), err.getvalue()

    def state(self, item):
        return json.loads((self.root / ".git/pm-workers/sessions" / f"{item}.json").read_text())

    def git(self, *args, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd or self.root, text=True, capture_output=True, check=True).stdout.strip()

    def worktree(self, item):
        return self.root / ".claude/worktrees" / f"pm-{item}"

    def do_the_item(self, item, cwd=None, branch=None, sync=None):
        """What a worker does for its item in the copy it works in: claim, commit on the work branch, validate, finish.
        `branch` is the work branch it makes; `sync` the board's branch it brings into a branch made for it."""
        cwd = cwd or self.root
        self.cli("claim", item, input_text="Ari", cwd=cwd)
        if branch:
            self.git("switch", "-qc", branch, cwd=cwd)
        if sync:
            self.git("merge", "-q", sync, cwd=cwd)
        (cwd / f"{item}.txt").write_text("the work\n")
        self.git("add", f"{item}.txt", cwd=cwd)
        self.git("commit", "-qm", f"{item}: the work", cwd=cwd)
        self.cli("validated", item, "--verdict", "pass", input_text="Checked.", cwd=cwd)
        self.cli("finish", item, input_text="Done.", cwd=cwd)

    def finish_on_its_branch(self, item):
        """What a lone worker leaves behind: the item Done on pm/ITEM, and the person's checkout parked there."""
        self.do_the_item(item, branch=f"pm/{item}")

    def records(self, name):
        path = self.home / name
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def calls_made(self, kinds=SESSION_STARTS):
        """The stand-in's CLI calls; by default only those that start or wake a session."""
        return [call for call in self.records("calls.jsonl") if kinds is None or call["kind"] in kinds]

    def turns(self):
        """Each turn a session ran: what it was given, and where it ran."""
        return self.records("turns.jsonl")

    def sessions(self):
        folder = self.home / "sessions"
        return [json.loads(path.read_text()) for path in sorted(folder.glob("*.json"))] if folder.exists() else []

    def flag(self, call, name):
        argv = call["argv"]
        return argv[argv.index(name) + 1] if name in argv else None

    def settings(self, call):
        return json.loads(Path(self.flag(call, "--settings")).read_text())

    def open_session(self, cwd, *flags):
        """The person opens a Claude Code session in a folder and types nothing."""
        process = subprocess.Popen([self.env["PM_CLAUDE"], *flags], cwd=cwd, env=self.env, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        self.addCleanup(process.wait)
        self.addCleanup(stop_group, process.pid)
        return process

    def hook(self, cwd, event, payload, script=WORKER_HOOK, **env):
        return subprocess.run(["bash", str(script), event], cwd=cwd, input=json.dumps(payload), text=True, capture_output=True,
                              env=dict(self.env, CLAUDE_PROJECT_DIR=str(cwd), CLAUDE_PLUGIN_ROOT=str(REPO), **env), timeout=60)

    def join(self, item, cwd, session, **settings_env):
        """What the worker's first step prints in its session (which has its settings file's environment): its ticket."""
        return self.cli("worker", "join", item, cwd=cwd, env=dict(self.env, CLAUDE_CODE_SESSION_ID=session, **settings_env)).stdout

    def ready(self, mode="auto"):
        self.cli("defaults", "--worker-model", "claude-sonnet-5-5", "--worker-effort", "medium",
                 "--validator-model", "claude-haiku-5-5", "--validator-effort", "low")
        self.cli("worker", "mode", mode)

    # ---- the person's choices are asked, never picked

    def test_start_refuses_until_the_person_chose_defaults_and_a_permission_setting(self):
        refused = self.cli("worker", "start", self.item, input_text="Ari", ok=False)
        self.assertIn("No default model and effort are recorded", refused.stderr)
        self.assertIn("Ask the person once", refused.stderr)
        self.assertIn("do not pick them yourself", refused.stderr)
        self.assertIn("Not recorded yet: workers model, workers effort, validators model, validators effort",
                      self.cli("defaults").stdout)
        self.cli("defaults", "--worker-model", "claude-opus-5-5", "--worker-effort", "high",
                 "--validator-model", "inherit", "--validator-effort", "medium")
        config = json.loads((self.root / "docs/pm/config.json").read_text())
        self.assertEqual(config["workers"], {"model": "claude-opus-5-5", "effort": "high"})
        self.assertEqual(config["validators"], {"model": "inherit", "effort": "medium"})
        log = subprocess.check_output(["git", "log", "--format=%s", "-1"], cwd=self.root, text=True)
        self.assertIn("pm: Recorded defaults.", log)
        refused = self.cli("worker", "start", self.item, input_text="Ari", ok=False)
        self.assertIn("No permission setting is chosen for worker sessions", refused.stderr)
        self.assertIn("auto (recommended)", refused.stderr)
        self.assertEqual(self.calls_made(None), [])
        self.cli("worker", "mode", "acceptEdits")
        self.assertIn("permission setting: acceptEdits", self.cli("worker", "mode").stdout)
        self.assertFalse((self.root / "docs/pm/config.json").read_text().count("acceptEdits"),
                         "the permission setting is the person's, kept in this clone, not committed")

    def test_models_are_exact_versions_never_aliases(self):
        for flag, alias in (("--worker-model", "sonnet"), ("--worker-model", "opus[1m]"), ("--worker-model", "inherit"),
                            ("--validator-model", "haiku")):
            refused = self.cli("defaults", flag, alias, ok=False)
            self.assertIn("must be an exact model version such as claude-sonnet-5-5", refused.stderr)
            self.assertIn(f"not `{alias}`", refused.stderr)
        for typo in ("gpt-4", "sonnet5", "claude-sonet-5-5", "claude-sonnet"):  # no Claude, no family, or no version
            self.assertIn(f"not `{typo}`", self.cli("defaults", "--validator-model", typo, ok=False).stderr)
        self.ready()
        refused = self.cli("worker", "start", self.item, "--model", "opus", input_text="Ari", ok=False)
        self.assertIn("not `opus`", refused.stderr)
        # A project set up before exact versions were required has an alias recorded: the person is asked again.
        config = self.root / "docs/pm/config.json"
        config.write_text(json.dumps(dict(json.loads(config.read_text()), workers={"model": "sonnet", "effort": "medium"})) + "\n")
        for start in ("start", "brief"):
            refused = self.cli("worker", start, self.item, input_text="Ari", ok=False)
            self.assertIn("not `sonnet`", refused.stderr)
            self.assertIn("record it with `pm.py defaults --worker-model MODEL`", refused.stderr)
        self.assertEqual(self.calls_made(None), [])

    # ---- each item gets its own full session in its own worktree

    def test_start_runs_a_full_background_session_in_the_items_own_worktree(self):
        self.ready()
        started = self.cli("worker", "start", self.item, input_text="Ari\nThe person left data.csv here.")
        call = self.calls_made()[0]
        worktree = self.worktree(self.item)
        self.assertEqual(Path(call["cwd"]).resolve(), worktree.resolve())
        self.assertTrue((worktree / ".git").is_file(), "a git worktree of the project")
        self.assertEqual(call["argv"][0], "--bg", "a full background session, opened later with `claude attach`")
        for headless in ("-p", "--print", "--output-format", "--session-id"):
            self.assertNotIn(headless, call["argv"])
        self.assertEqual(self.flag(call, "--agent"), "pm:worker")
        self.assertEqual(self.flag(call, "--model"), "claude-sonnet-5-5")
        self.assertEqual(self.flag(call, "--effort"), "medium")
        self.assertEqual(self.flag(call, "--permission-mode"), "auto")
        self.assertEqual(self.flag(call, "--name"), f"pm worker {self.item}")
        self.assertEqual(Path(self.flag(call, "--plugin-dir")), REPO)
        settings = self.settings(call)
        self.assertEqual(settings["env"]["PM_WORKER"], self.item)
        self.assertEqual(settings["env"]["CLAUDE_CODE_SUBAGENT_MODEL"], "claude-haiku-5-5",
                         "its validator, the only subagent it starts, runs on the exact version the person chose")
        self.assertEqual(settings["worktree"], {"bgIsolation": "none"}, "it stays in the copy it was started in")
        self.assertIsNone(call["session_env"], "the coordinator's session identity is not passed on")
        prompt = call["argv"][1]
        self.assertTrue(prompt.startswith(f"pm worker session for board item {self.item}, which the person asked to have done"))
        self.assertIn(f'scripts/pm.py" worker join {self.item}` first', prompt)
        self.assertNotIn("\n", prompt, "the first message is one line; the ticket comes from the join it names")
        turn = self.turns()[0]
        self.assertEqual((turn["pm_worker"], Path(turn["cwd"]).resolve()), (self.item, worktree.resolve()))
        state = self.state(self.item)
        ticket = self.join(self.item, worktree, state["session"], **settings["env"])
        for line in (f"Joined: this session is the worker for {self.item}, not the coordinating session",
                     f"Instructions: {REPO.as_posix()}/agents/worker.md", f"Item: {self.item}", "Claim under: Ari",
                     "Claim: new claim", f"Copy: {worktree} (your own worktree, made for this item)",
                     f"Work branch: pm/{self.item} (create or switch to it in step 3)",
                     "Validator: model claude-haiku-5-5 (this session runs its subagents on it: pass the Agent tool no model), "
                     "effort low", "The person left data.csv here."):
            self.assertIn(line, ticket)
        self.assertEqual((state["started_by"], state["session"][:8]), ("background", state["job"]))
        self.assertIn(f"Started worker session {state['session']}", started.stdout)
        self.assertIn(f"`claude attach {state['job']}` opens it", started.stdout)
        self.assertIn("Report:\nResult: done", started.stdout)
        self.assertIn("Its board commands this turn: claim; validator subagents started: 1.", started.stdout,
                      "read from the worker's own session transcript, not its report")
        self.assertIn(f"No branch pm/{self.item} with the item on it.", started.stdout)
        self.assertEqual(self.cli("places", "--paths").stdout, "", "the worktree is not a stray file")
        self.assertEqual([call["kind"] for call in self.calls_made(None) if call["kind"] not in ("bg", "agents")], [])

    def test_the_persons_model_and_effort_for_one_worker_win_over_the_defaults(self):
        self.ready()
        self.cli("worker", "start", self.item, "--here", "--model", "claude-opus-5-5", "--effort", "max",
                 "--validator-model", "claude-sonnet-5-5", "--validator-effort", "high", input_text="Ari")
        call = self.calls_made()[0]
        self.assertEqual(Path(call["cwd"]).resolve(), self.root.resolve())
        self.assertEqual((self.flag(call, "--model"), self.flag(call, "--effort")), ("claude-opus-5-5", "max"))
        ticket = self.join(self.item, self.root, self.state(self.item)["session"], **self.settings(call)["env"])
        self.assertIn("Validator: model claude-sonnet-5-5 (this session runs its subagents on it: pass the Agent tool no model), "
                      "effort high", ticket)
        self.assertIn(f"Copy: {self.root} (the person's checkout)", ticket)
        self.assertFalse((self.root / ".claude/worktrees").exists())
        self.cli("defaults", "--validator-model", "inherit")
        second = self.add("Count lines", "Add a line count")
        self.cli("worker", "start", second, input_text="Ari")
        call = self.calls_made()[1]
        self.assertIn("Validator: model inherit (your own model: pass the Agent tool no model), effort low",
                      self.join(second, self.worktree(second), self.state(second)["session"]))
        self.assertEqual(list(self.settings(call)["env"]), ["PM_WORKER", "PM_COORDINATOR_ROOT"])

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
        turns = self.turns()
        self.assertLess(abs(turns[0]["at"] - turns[1]["at"]), 2, "the second session started while the first ran")
        self.assertEqual({turn["pm_worker"] for turn in turns}, {self.item, second})
        self.assertEqual(len({turn["session"] for turn in turns}), 2)
        self.assertEqual(len({turn["cwd"] for turn in turns}), 2)

    # ---- a question comes back and the answer goes into the same open session

    def test_answer_continues_the_same_session_with_the_message_as_its_next_prompt(self):
        self.ready()
        self.cli("worker", "start", self.item, input_text="Ari")
        again = self.cli("worker", "start", self.item, input_text="Ari", ok=False)
        self.assertIn("already has a worker session", again.stderr)
        self.assertIn("worker answer", again.stderr)
        answered = self.cli("worker", "answer", self.item,
                            input_text="The owner answered: use the CSV. Saved in the item's notes.")
        first, second = self.turns()
        self.assertEqual((second["session"], second["id"], second["cwd"]), (first["session"], first["id"], first["cwd"]),
                         "the same session and conversation took the message")
        self.assertEqual(second["prompt"], f"Message from the coordinating session for board item {self.item}:\n"
                         "The owner answered: use the CSV. Saved in the item's notes.",
                         "as a prompt, which carries the person's authority, not as a hook's note")
        self.assertEqual([call["kind"] for call in self.calls_made(("bg", "resume", "stop", "rm"))], ["bg", "stop", "rm", "resume"],
                         "it is taken off the list first, so the wake-up continues it instead of copying it")
        self.assertEqual(len(self.sessions()), 1, "no second session was made")
        self.assertIn(f"Continued worker session {first['session']}", answered.stdout)
        self.assertIn("Report:\nResult: done\nSeen: Message from the coordinating session", answered.stdout)
        self.assertEqual(self.state(self.item)["turns"], 2)
        fresh = self.cli("worker", "start", self.item, "--fresh", "--resume", input_text="Ari")
        self.assertNotEqual(self.turns()[2]["session"], first["session"])
        self.assertIn("Claim: resume the existing claim (claim --resume)",
                      self.join(self.item, self.worktree(self.item), self.state(self.item)["session"]))
        self.assertIn("Started worker session", fresh.stdout)
        self.assertEqual([session["sessionId"] for session in self.sessions()], [self.turns()[2]["session"]],
                         "the session it replaced was closed and taken off the list")

    def test_a_message_for_a_worker_mid_turn_arrives_when_its_turn_ends(self):
        self.ready()
        self.cli("worker", "start", self.item, "--no-wait", input_text="Ari", env=dict(self.env, FAKE_CLAUDE_SLEEP="3"))
        time.sleep(1)
        answered = self.cli("worker", "answer", self.item, input_text="Also count hyphenated words once.")
        self.assertIn("is mid-turn; it gets this message as soon as its current turn ends", answered.stdout)
        first, second = self.turns()
        self.assertEqual(second["pid"], first["pid"])
        self.assertIn("Also count hyphenated words once.", second["prompt"])
        self.assertIn("Report:\nResult: done\nSeen: pm mailbox", answered.stdout, "it waited for the turn the message started")
        self.assertEqual(len(self.calls_made()), 1)

    def test_a_stopped_worker_is_woken_with_its_conversation(self):
        self.ready()
        self.cli("worker", "start", self.item, input_text="Ari")
        first, session = self.calls_made()[0], self.state(self.item)["session"]
        self.assertIn("conversation is kept", self.cli("worker", "stop", self.item).stdout)
        self.assertIn("stopped; `pm.py worker answer` continues it", self.cli("worker", "list").stdout)
        answered = self.cli("worker", "answer", self.item, input_text="- carry on")
        resumed = self.calls_made()[1]
        self.assertEqual(resumed["argv"][:3], ["--resume", session, "--bg"], "the same conversation, as a full session")
        self.assertEqual(resumed["argv"][3], f"Message from the coordinating session for board item {self.item}:\n- carry on")
        self.assertEqual(resumed["cwd"], first["cwd"])
        self.assertEqual((self.flag(resumed, "--model"), self.flag(resumed, "--permission-mode")), ("claude-sonnet-5-5", "auto"))
        self.assertNotIn("-p", resumed["argv"])
        self.assertIn(f"Continued worker session {session}", answered.stdout)
        self.assertIn("Report:\nResult: done\nSeen: Message from the coordinating session", answered.stdout)
        self.assertEqual(self.state(self.item)["session"], session)

    def test_a_permission_prompt_comes_back_as_a_question_for_the_person(self):
        self.ready("acceptEdits")
        env = dict(self.env, FAKE_CLAUDE_PERMISSION="Bash npm test")
        code, out, err = self.cli_here("worker", "start", self.item, input_text="Ari", env=env, SESSIONS_EVERY_SECONDS=1)
        self.assertEqual(code, 0, err)
        state = self.state(self.item)
        self.assertIn(f"Worker session for {self.item} is waiting on permission prompt for Bash npm test", out)
        self.assertIn(f"Only the person can answer it, in that session (`claude attach {state['job']}` opens it)", out)
        self.assertNotIn("Report:", out)
        self.assertIn("waiting on permission prompt for Bash npm test, in its own session", self.cli("worker", "list").stdout)
        (self.home / f"approve-{state['session']}").touch()  # the person allows it in the worker's session
        time.sleep(1)
        waited = self.cli("worker", "wait", self.item)
        self.assertIn("Report:\nResult: done", waited.stdout)
        self.assertEqual(len(self.turns()), 1, "the same turn went on after their answer")

    def test_auto_mode_unavailable_falls_back_to_accept_edits(self):
        self.ready("auto")
        env = dict(self.env, FAKE_CLAUDE_MODE="default")
        started = self.cli("worker", "start", self.item, "--here", input_text="Ari", env=env)
        self.assertIn("Auto mode was unavailable to worker sessions (this one runs in default mode", started.stdout)
        self.assertIn("Report:\nResult: done", started.stdout)
        self.assertEqual(len(self.calls_made()), 1, "the open session is kept: its prompts are answered in it")
        self.assertIn("permission setting: acceptEdits", self.cli("worker", "mode").stdout)
        self.assertIn("falls back to acceptEdits", self.cli("worker", "mode").stdout)
        second = self.add("Count lines", "Add a line count")
        self.cli("worker", "start", second, input_text="Ari")
        self.assertEqual(self.flag(self.calls_made()[1], "--permission-mode"), "acceptEdits")

    # ---- a worker's turn ends with its report

    def test_workers_are_not_given_tools_that_schedule_a_later_turn(self):
        self.ready()
        self.cli("worker", "start", self.item, input_text="Ari")
        self.cli("worker", "stop", self.item)
        self.cli("worker", "answer", self.item, input_text="Carry on.")
        calls = self.calls_made()
        self.assertEqual([call["kind"] for call in calls], ["bg", "resume"])
        for call in calls:
            argv = call["argv"]
            self.assertEqual(argv[argv.index("--disallowedTools") + 1:], ["ScheduleWakeup", "CronCreate"],
                             "a worker's turn ends with its report, not with a wakeup it scheduled")

    def test_a_worker_waiting_on_its_validator_has_not_ended_its_turn(self):
        self.ready()
        started = self.cli("worker", "start", self.item, input_text="Ari", env=dict(self.env, FAKE_CLAUDE_BACKGROUND="3"))
        self.assertIn("Report:\nResult: done", started.stdout, "it waited for the report that followed the background task")
        self.assertNotIn("Validation is still running", started.stdout)

    def test_a_session_that_ends_without_a_report_is_said_so(self):
        self.ready()
        self.cli("worker", "start", self.item, "--no-wait", input_text="Ari", env=dict(self.env, FAKE_CLAUDE_SLEEP="30"))
        subprocess.run([self.env["PM_CLAUDE"], "stop", self.state(self.item)["job"]], env=self.env, capture_output=True, check=True)
        code, out, err = self.cli_here("worker", "wait", self.item, GONE_GRACE_SECONDS=1, SESSIONS_EVERY_SECONDS=1)
        self.assertEqual(code, 1, out + err)
        self.assertIn(f"Worker session for {self.item} is no longer running and left no final report", out)
        self.assertIn(f"`pm.py worker answer {self.item}` continues it", out)
        self.assertIn("its session is not running", self.cli("worker", "list").stdout)

    # ---- where no session can be started for the person, they open it and it gets its ticket

    def test_where_background_sessions_are_blocked_the_person_opens_the_session_and_it_gets_its_ticket(self):
        self.ready()
        env = dict(self.env, FAKE_CLAUDE_BG_FAIL="Background sessions are disabled by your organization's policy.")
        started = self.cli("worker", "start", self.item, "--here", input_text="Ari\nUse the CSV.", env=env)
        worktree = self.worktree(self.item)
        self.assertIn(f"Could not start {self.item}'s worker as a background session: Background sessions are disabled",
                      started.stdout)
        self.assertIn(f"terminal, in the folder {worktree}: claude --name 'pm worker {self.item}' --agent pm:worker", started.stdout)
        self.assertIn("--model claude-sonnet-5-5 --effort medium", started.stdout)
        self.assertIn(f"Claude app: a new session in the folder {worktree}, model claude-sonnet-5-5", started.stdout)
        self.assertIn(f"Then run `pm.py worker wait {self.item}` in the background", started.stdout)
        state = self.state(self.item)
        self.assertEqual((state["started_by"], state["state"], state["session"]), ("handover", "awaiting-session", ""))
        self.assertTrue(state["own_worktree"], "a session the person opens gets the item's own copy, never their checkout")
        self.assertIn(f"waiting for the person to open a session in {worktree}", self.cli("worker", "list").stdout)
        refused = self.cli("worker", "answer", self.item, input_text="Hello?", ok=False)
        self.assertIn("has not been opened yet", refused.stderr)
        note = self.hook(worktree, "", {}, script=START_HOOK).stdout.strip().splitlines()[-1]
        self.assertIn(f"This is the worker session for board item {self.item}", note)
        self.open_session(worktree)  # plain `claude`, nothing typed
        waited = self.cli("worker", "wait", self.item)
        turn = self.turns()[0]
        self.assertTrue(turn["prompt"].startswith(f"pm worker session for board item {self.item}, which the person asked"))
        self.assertIn(f"worker join {self.item}` first", turn["prompt"])
        self.assertEqual(Path(turn["cwd"]).resolve(), worktree.resolve())
        ticket = self.join(self.item, worktree, turn["session"])
        for line in ("the session-start note about not editing project files does not apply to you",
                     "If you were not started as the pm:worker agent, read that file now and follow it exactly",
                     f"Item: {self.item}", "Claim under: Ari", "Use the CSV."):
            self.assertIn(line, ticket)
        self.assertIn("a session the person opened", waited.stdout)
        self.assertIn("Report:\nResult: done", waited.stdout)
        self.assertEqual(self.state(self.item)["session"], turn["session"])
        answered = self.cli("worker", "answer", self.item, input_text="The owner answered: yes.")
        self.assertIn("Delivered into the open worker session", answered.stdout)
        self.assertEqual(self.turns()[1]["pid"], turn["pid"], "the answer went into the session the person opened")
        self.assertIn("The owner answered: yes.", self.turns()[1]["prompt"])
        self.assertEqual([call["kind"] for call in self.calls_made()], ["bg"], "only the refused start; nothing headless after it")

    def test_a_worker_can_be_handed_over_on_request(self):
        self.ready()
        started = self.cli("worker", "start", self.item, "--handover", input_text="Ari")
        self.assertIn(f"{self.item}'s worker is handed over to a session the person opens.", started.stdout)
        self.assertEqual(self.calls_made(None), [])
        self.open_session(self.worktree(self.item), "--agent", "pm:worker")
        self.assertIn("Report:\nResult: done", self.cli("worker", "wait", self.item).stdout)
        other = self.git("rev-parse", "--show-toplevel")
        self.assertEqual(self.hook(Path(other), "session-start", {"session_id": "someone-else", "cwd": other}).returncode, 0,
                         "a session opened anywhere else is handed nothing")

    def test_a_missing_claude_falls_back_to_a_session_the_person_opens(self):
        self.ready()
        env, tools, home = self.lookup_env()
        env["CLAUDE_CODE_EXECPATH"] = "/opt/claude/versions/9/claude"
        code, out, err = self.cli_here("worker", "start", self.item, input_text="Ari", env=env, CLAUDE_WAIT_SECONDS=1)
        self.assertEqual(code, 0, err)
        for looked in ("as a background session: No `claude` executable was found after looking for 1 seconds",
                       "`claude` on PATH (claude)",
                       "CLAUDE_CODE_EXECPATH, the Claude Code running this session (/opt/claude/versions/9/claude)",
                       f"({home}/.local/bin/claude)", f"({home}/.claude/local/claude)", f"PATH is '{env['PATH']}'",
                       "set PM_CLAUDE to its full path", "Ask the person to open a Claude Code session there"):
            self.assertIn(looked, out)
        self.assertEqual(self.state(self.item)["started_by"], "handover")
        second = self.add("Count lines", "Add a line count")
        env["PM_CLAUDE"] = "/nowhere/claude"
        code, out, err = self.cli_here("worker", "start", second, input_text="Ari", env=env, CLAUDE_WAIT_SECONDS=0)
        self.assertIn("Looked for: PM_CLAUDE (/nowhere/claude).", out, "the person's own path is the only place looked")

    # ---- in the Claude app the coordinating session starts the worker; the plugin records what the app made

    def test_in_the_app_the_worker_is_started_by_the_apps_own_tool_and_joins_with_the_copy_it_was_given(self):
        self.cli("defaults", "--worker-model", "claude-sonnet-5-5", "--worker-effort", "medium",
                 "--validator-model", "claude-haiku-5-5", "--validator-effort", "low")  # no `worker mode`: the app's applies
        brief = self.cli("worker", "brief", self.item, input_text="Ari\nUse the CSV.").stdout
        self.assertIn("`start_session` in the Claude app, or whichever tool in your list starts a full Claude Code session", brief)
        self.assertIn("- model: claude-sonnet-5-5 (the exact version from setup; pass it as it is)", brief)
        self.assertIn("- first message: this one line, unchanged\n"
                      f"pm worker session for board item {self.item}, which the person asked to have done", brief)
        self.assertIn(f"worker join {self.item}` first", brief)
        self.assertEqual(self.calls_made(None), [], "the plugin starts nothing here: the app's tool does")
        self.assertIn("a session the Claude app started (not opened yet), turn 0; waiting for the app to start it",
                      self.cli("worker", "list").stdout)
        self.assertIn("already has a worker session", self.cli("worker", "brief", self.item, input_text="Ari", ok=False).stderr)
        # The app makes the copy and the branch; the worker's first step records them.
        home = self.git("branch", "--show-current")
        copy = self.root / ".claude" / "worktrees" / "tidy-otter"
        self.git("worktree", "add", "-q", "-b", "claude/tidy-otter", str(copy))
        app_session = dict(self.env, CLAUDE_CODE_SESSION_ID="app-session-1")
        joined = self.cli("worker", "join", self.item, cwd=copy, env=app_session).stdout
        for line in (f"Joined: this session is the worker for {self.item}, not the coordinating session",
                     f"Instructions: {REPO.as_posix()}/agents/worker.md", "Claim: new claim",
                     "Validator: model claude-haiku-5-5 (this session is not set to it: pass the Agent tool the model haiku, "
                     "the nearest it takes), effort low",
                     f"Copy: {copy} (your own worktree, made for this session)",
                     f"Work branch: claude/tidy-otter (already made for this copy: it is the work branch, do not create pm/{self.item}; "
                     "step 3 brings the claim into it)",
                     "Claim under: Ari", "Use the CSV."):
            self.assertIn(line, joined)
        state = self.state(self.item)
        self.assertEqual((state["session"], state["branch"], state["started_by"], state["made_copy"]),
                         ("app-session-1", "claude/tidy-otter", "app", False))
        self.assertTrue(Path(state["checkout"]).samefile(copy))
        self.assertEqual(self.cli("places", "--paths").stdout, "", "a copy the app made is not a stray file")
        other = self.root / ".claude" / "worktrees" / "other"
        self.git("worktree", "add", "-q", "-b", "claude/other", str(other))
        refused = self.cli("worker", "join", self.item, cwd=other, env=dict(self.env, CLAUDE_CODE_SESSION_ID="app-session-2"), ok=False)
        self.assertIn(f"{self.item} already has a worker session (app-session-1)", refused.stderr)
        # A later message is a follow-up the coordinating session sends with the app's tool.
        answered = self.cli("worker", "answer", self.item, input_text="The owner answered: yes.").stdout
        self.assertIn("Send it this as a follow-up message with your tool that messages a session you started", answered)
        self.assertIn(f"Message from the coordinating session for board item {self.item}:\nThe owner answered: yes.", answered)
        # The worker finishes on the app's branch; its Stop hook saves the report and holds no mailbox.
        self.do_the_item(self.item, cwd=copy, sync=home)
        stopped = self.hook(copy, "stop", {"session_id": "app-session-1", "cwd": str(copy), "permission_mode": "auto",
                                           "last_assistant_message": "Result: done", "background_tasks": []})
        self.assertEqual((stopped.returncode, stopped.stderr), (0, ""))
        waited = self.cli("worker", "wait", self.item).stdout
        self.assertIn("a session the Claude app started", waited)
        self.assertIn("permission setting auto", waited)
        self.assertIn("On branch claude/tidy-otter: status done; validation pass", waited)
        self.assertIn("Report:\nResult: done", waited)
        self.assertIn(f"{self.item} is Done on claude/tidy-otter, so its copy {copy} was removed", waited)
        self.assertIn("The session stays in the Claude app's list until the person archives it there.", waited)
        self.assertFalse(copy.exists())
        self.assertTrue(self.git("rev-parse", "--verify", "claude/tidy-otter"), "the branch and its commits are kept")
        self.assertEqual(self.calls_made(SESSION_STARTS + ("stop", "rm", "open")), [])

    def test_an_app_worker_whose_hooks_did_not_run_is_still_tidied_from_its_branch(self):
        self.ready()
        self.cli("worker", "brief", self.item, input_text="Ari")
        waited = self.cli("worker", "wait", self.item).stdout  # returns at once: the app says when a turn ends
        self.assertIn("runs in the Claude app, which tells you when its turn ends and carries its report", waited)
        self.assertIn(f"No branch pm/{self.item} with the item on it.", waited)
        copy = self.root / ".claude" / "worktrees" / "quiet-heron"
        self.git("worktree", "add", "-q", "-b", "claude/quiet-heron", str(copy))
        self.cli("worker", "join", self.item, cwd=copy, env=dict(self.env, CLAUDE_CODE_SESSION_ID="app-session-1"))
        self.do_the_item(self.item, cwd=copy, sync=self.git("branch", "--show-current"))
        (copy / "scratch.txt").write_text("not committed\n")
        waited = self.cli("worker", "wait", self.item).stdout
        self.assertIn("No report of its latest turn is recorded here.", waited)
        self.assertIn(f"but its copy {copy} was kept: 1 file in it not committed (scratch.txt)", waited)
        self.assertTrue(copy.exists())
        (copy / "scratch.txt").unlink()
        self.assertIn(f"and its copy {copy}; its branch and commits are kept", self.cli("worker", "remove", self.item).stdout)
        self.assertFalse(copy.exists())

    # ---- a finished item takes its copy with it, when nothing in it would be lost

    def test_a_finished_item_takes_its_copy_and_its_session_with_it(self):
        self.ready()
        started = self.cli("worker", "start", self.item, input_text="Ari", env=dict(self.env, FAKE_CLAUDE_WORK="finish")).stdout
        worktree, branch = self.worktree(self.item), f"pm/{self.item}"
        self.assertIn(f"On branch {branch}: status done; validation pass", started)
        self.assertIn(f"{self.item} is Done on {branch}, so its copy {worktree} was removed and its worker session closed; "
                      f"{branch} keeps the commits for review and merge.", started)
        self.assertFalse(worktree.exists())
        self.assertIn(f"{self.item}: the work", self.git("log", "--format=%s", branch))
        self.assertEqual(self.sessions(), [], "its session is closed and off the list")
        session = self.state(self.item)["session"]
        self.assertIn("finished; its copy was removed", self.cli("worker", "list").stdout)
        # The person's correction still reaches the same conversation: the copy comes back for it.
        answered = self.cli("worker", "answer", self.item, input_text="The person corrected: count hyphenated words once.").stdout
        self.assertIn(f"Its copy {worktree} was put back on {branch}.", answered)
        self.assertEqual(self.calls_made()[1]["argv"][:2], ["--resume", session])
        self.assertEqual(self.turns()[1]["branch"], branch)
        self.assertIn(f"so its copy {worktree} was removed", answered)
        self.assertFalse(worktree.exists())
        # Once the branch is merged the item is Done on the board, and nothing is left to keep a record for.
        self.git("merge", "-q", branch)
        self.assertIn("No worker sessions.", self.cli("worker", "list").stdout)
        self.assertEqual(list((self.root / ".git/pm-workers/sessions").iterdir()), [])

    def test_a_copy_with_work_that_is_not_committed_is_kept(self):
        self.ready()
        started = self.cli("worker", "start", self.item, input_text="Ari", env=dict(self.env, FAKE_CLAUDE_WORK="litter")).stdout
        worktree = self.worktree(self.item)
        self.assertIn(f"{self.item} is Done on pm/{self.item}, but its copy {worktree} was kept: 1 file in it not committed "
                      f"(scratch.txt). Once that is settled, `pm.py worker remove {self.item}` removes it.", started)
        self.assertTrue((worktree / "scratch.txt").exists())
        refused = self.cli("worker", "remove", self.item, ok=False)
        self.assertIn("was kept: 1 file in it not committed (scratch.txt)", refused.stderr)
        self.git("switch", "-q", "--detach", cwd=worktree)
        (worktree / "scratch.txt").unlink()
        (worktree / "late.txt").write_text("a late idea\n")
        self.git("add", "late.txt", cwd=worktree)
        self.git("commit", "-qm", "late idea", cwd=worktree)
        refused = self.cli("worker", "remove", self.item, ok=False)
        self.assertIn("was kept: its latest commits are on no branch", refused.stderr)
        self.git("branch", "late-idea", cwd=worktree)
        self.cli("worker", "remove", self.item)
        self.assertFalse(worktree.exists())

    def test_a_lone_worker_leaves_the_persons_checkout_in_place(self):
        self.ready()
        started = self.cli("worker", "start", self.item, "--here", input_text="Ari", env=dict(self.env, FAKE_CLAUDE_WORK="finish"))
        self.assertIn(f"{self.item} is Done on pm/{self.item}; its worker session was closed.", started.stdout)
        self.assertEqual(self.git("branch", "--show-current"), f"pm/{self.item}", "the person sees the result in their checkout")
        self.assertEqual(self.sessions(), [])

    # ---- the claude executable is found for every worker action, also while an update replaces it

    def lookup_env(self):
        """An environment where `claude` is found only where the test puts it: no real install is reachable."""
        tools = Path(self.temp.name) / "tools"
        tools.mkdir()
        home = Path(self.temp.name) / "home"
        home.mkdir()
        # The real install folders are left out by name too: an update removes `claude` from them for a moment,
        # and a folder that looked empty then would bring the real one back.
        installs = [Path.home() / ".local" / "bin", Path.home() / ".claude" / "local"]
        rest = [folder for folder in self.env["PATH"].split(os.pathsep)
                if folder and Path(folder) not in installs and not (Path(folder) / "claude").exists()]
        env = dict(self.env, PATH=os.pathsep.join([str(tools), *rest]), HOME=str(home))
        env.pop("PM_CLAUDE")
        return env, tools, home

    def reinstall_soon(self, target, seconds=2):
        """What an update does: the working `claude` appears at its path a moment later."""
        def install():
            shutil.copy(self.env["PM_CLAUDE"], f"{target}.new")
            os.replace(f"{target}.new", target)
        timer = threading.Timer(seconds, install)
        timer.start()
        self.addCleanup(timer.join)

    def test_answer_finds_claude_again_after_an_update_replaced_it(self):
        self.ready()
        self.cli("worker", "start", self.item, input_text="Ari")
        session = self.state(self.item)["session"]
        self.cli("worker", "stop", self.item)
        env, tools, _ = self.lookup_env()
        self.reinstall_soon(tools / "claude")  # gone when the answer is sent, back two seconds later
        answered = self.cli("worker", "answer", self.item, input_text="The owner answered: yes.", env=env)
        self.assertIn("Report:\nResult: done\nSeen: Message from the coordinating session", answered.stdout)
        self.assertEqual(self.flag(self.calls_made()[1], "--resume"), session)

    def test_start_survives_a_claude_that_cannot_run_yet(self):
        self.ready()
        env, tools, _ = self.lookup_env()
        half_written = tools / "claude"
        half_written.write_text("#!/no/such/interpreter\n")  # found by name, but it cannot be started
        half_written.chmod(0o755)
        self.reinstall_soon(half_written)
        started = self.cli("worker", "start", self.item, input_text="Ari", env=env)
        self.assertIn("Report:\nResult: done", started.stdout)

    def test_claude_is_found_beside_the_running_session_or_in_its_install_path_when_not_on_path(self):
        env, tools, home = self.lookup_env()
        fake = Path(self.env["PM_CLAUDE"])
        installed = home / ".local" / "bin" / "claude"
        installed.parent.mkdir(parents=True)
        shutil.copy(fake, installed)
        session_copy = Path(self.temp.name) / "session-claude"
        shutil.copy(fake, session_copy)
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(pm_workers, "CLAUDE_WAIT_SECONDS", 0):
            self.assertEqual(pm_workers.claude_binary(), str(installed))
            os.environ["CLAUDE_CODE_EXECPATH"] = str(session_copy)
            self.assertEqual(pm_workers.claude_binary(), str(session_copy))
            shutil.copy(fake, tools / "claude")
            self.assertEqual(pm_workers.claude_binary(), str(tools / "claude"), "PATH comes first, as before")

    # ---- an item's branch starts from the board's branch, never from another item's

    def test_new_work_never_lands_on_or_starts_from_the_previous_items_branch(self):
        self.ready()
        home = self.git("branch", "--show-current")
        self.finish_on_its_branch(self.item)  # the person's checkout is now parked on pm/ITEM
        finished = self.git("rev-parse", f"pm/{self.item}")
        added = self.cli("add", input_text="Count lines\nAdd a line count")
        second = added.stdout.split(":", 1)[0].split()[-1]
        self.assertIn(f"{self.root} was on pm/{self.item}, another item's finished work branch, so it was returned to {home} "
                      "first", added.stdout)
        self.assertEqual(self.git("branch", "--show-current"), home)
        self.assertEqual(self.git("log", "-1", "--format=%s", home), f"pm: Created {second}: Count lines")
        self.assertEqual(self.git("rev-parse", f"pm/{self.item}"), finished, "nothing was added to the finished branch")

        self.git("switch", "-q", f"pm/{self.item}")  # the person looks at the finished work again
        started = self.cli("worker", "start", second, "--here", input_text="Ari")
        self.assertIn(f"returned to {home} first", started.stdout)
        turn = self.turns()[-1]
        self.assertEqual(turn["branch"], home, "the lone worker starts on the board's branch")
        self.assertEqual(turn["head"], self.git("rev-parse", home))

        third = self.add("Count pages", "Add a page count")
        self.git("switch", "-q", f"pm/{self.item}")
        self.cli("worker", "start", third, input_text="Ari")  # in its own worktree
        turn = self.turns()[-1]
        self.assertEqual(turn["head"], self.git("rev-parse", home), "its worktree starts at the board branch's tip")
        self.assertEqual(self.git("branch", "--show-current"), home)
        carried = subprocess.run(["git", "merge-base", "--is-ancestor", finished, turn["head"]], cwd=self.root)
        self.assertNotEqual(carried.returncode, 0, "the new item's start does not carry the finished item's commits")

    def test_an_items_own_branch_and_an_unfinished_one_are_left_alone(self):
        self.ready()
        second = self.add("Count lines", "Add a line count")
        self.cli("claim", self.item, input_text="Ari")
        self.git("switch", "-qc", f"pm/{self.item}")
        kept = self.cli("claim", self.item, "--resume", input_text="Ari")  # the item's own worker, on its own branch
        self.assertNotIn("returned to", kept.stdout)
        self.assertEqual(self.git("branch", "--show-current"), f"pm/{self.item}")
        for new_work in (("add",), ("claim", second), ("worker", "start", second), ("worker", "start", second, "--here"),
                         ("worker", "brief", second)):
            refused = self.cli(*new_work, input_text="Ari\nAdd a page count", ok=False)
            self.assertIn(f"{self.root} is on pm/{self.item}, another item's work branch, and new work is never saved on "
                          "or started from another item's branch", refused.stderr)
            self.assertIn(f"{self.item} is not finished there. Continue it first", refused.stderr)
        self.assertEqual(self.git("branch", "--show-current"), f"pm/{self.item}", "unfinished work is not switched away from")
        self.assertEqual(self.calls_made(), [], "no worker started on another item's branch")
        # Later board writes about another item (its worker parking it) are saved where the board is, as before.
        held = self.cli("hold", second, input_text="Which lines count?")
        self.assertNotIn("returned to", held.stdout)
        self.assertEqual(self.git("branch", "--show-current"), f"pm/{self.item}")

    def test_a_later_board_write_also_returns_a_checkout_left_on_a_finished_branch(self):
        self.ready()
        home = self.git("branch", "--show-current")
        second = self.add("Count lines", "Add a line count")
        self.cli("claim", second, input_text="Ari")  # the second item's worker runs in its own worktree
        self.finish_on_its_branch(self.item)  # meanwhile a lone worker finished the first here
        held = self.cli("hold", second, input_text="Which lines count?")
        self.assertIn(f"returned to {home} first", held.stdout)
        self.assertEqual(self.git("log", "-1", "--format=%s", home), f"pm: Parked {second}: Which lines count?")

    def test_a_pm_branch_that_is_not_an_items_is_left_alone(self):
        self.ready()
        self.git("switch", "-qc", "pm/setup")  # where setup is committed in a project with a remote
        added = self.cli("add", input_text="Count lines\nAdd a line count")
        self.assertNotIn("returned to", added.stdout)
        self.assertEqual(self.git("branch", "--show-current"), "pm/setup")

    def test_a_checkout_a_worker_is_working_in_is_not_switched(self):
        self.ready()
        env = dict(self.env, FAKE_CLAUDE_SLEEP="30")
        self.cli("worker", "start", self.item, "--here", "--no-wait", input_text="Ari", env=env)
        self.git("switch", "-qc", f"pm/{self.item}")  # as the lone worker does once it has claimed
        refused = self.cli("add", input_text="Count lines\nAdd a line count", ok=False)
        self.assertIn(f"the worker session for {self.item} is working there", refused.stderr)
        self.assertEqual(self.git("branch", "--show-current"), f"pm/{self.item}")
        self.cli("worker", "stop", self.item)

    def test_a_parked_checkout_with_no_branch_to_return_to_says_what_to_do(self):
        self.ready()
        home = self.git("branch", "--show-current")
        self.finish_on_its_branch(self.item)
        self.git("branch", "-qD", home)
        refused = self.cli("add", input_text="Count lines\nAdd a line count", ok=False)
        self.assertIn("Git has no record of the branch it was on before", refused.stderr)
        self.assertIn("git switch main", refused.stderr)

    def test_a_checkout_that_cannot_return_says_why(self):
        self.ready()
        home = self.git("branch", "--show-current")
        self.finish_on_its_branch(self.item)
        elsewhere = Path(self.temp.name) / "elsewhere"
        self.git("worktree", "add", "-q", str(elsewhere), home)  # the branch it was on is checked out somewhere else
        refused = self.cli("add", input_text="Count lines\nAdd a line count", ok=False)
        self.assertIn(f"it could not return to {home}:", refused.stderr)

    def test_with_a_remote_a_worktree_starts_at_the_shared_default_branch(self):
        self.ready()
        home = self.git("branch", "--show-current")
        remote = Path(self.temp.name) / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", f"--initial-branch={home}", str(remote)], check=True)
        self.git("remote", "add", "origin", str(remote))
        self.git("push", "-q", "-u", "origin", home)
        shared = self.git("rev-parse", home)
        self.git("switch", "-qc", "pm/some-other-item")  # the coordinating checkout sits on another item's branch
        (self.root / "other.txt").write_text("another item's work\n")
        self.git("add", "other.txt")
        self.git("commit", "-qm", "some-other-item: its work")
        self.cli("worker", "start", self.item, input_text="Ari")
        self.assertEqual(self.turns()[-1]["head"], shared, "not the coordinating checkout's commit")

    # ---- the coordinator sees each worker, and finds them again after a restart

    def test_workers_shows_what_each_is_doing_or_waiting_on(self):
        self.ready()
        self.assertIn("No worker sessions.", self.cli("worker", "list").stdout)
        env = dict(self.env, FAKE_CLAUDE_SLEEP="3")
        self.cli("worker", "start", self.item, "--no-wait", input_text="Ari", env=env)
        time.sleep(1)
        listing = self.cli("worker", "list").stdout
        job = self.state(self.item)["job"]
        self.assertIn(f"- {self.item} Count words: board queued; a background session ({job}), turn 1; working", listing)
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
        self.assertFalse(self.worktree(self.item).exists())
        self.assertEqual(self.sessions(), [])
        self.assertIn("No worker sessions.", self.cli("worker", "list").stdout)

    # ---- the plugin's hooks act only in a worker's session

    def test_a_worker_sessions_start_hook_does_not_tell_it_to_stay_hands_off(self):
        out = self.hook(self.root, "", {}, script=START_HOOK, PM_WORKER=self.item).stdout.strip().splitlines()[-1]
        self.assertIn(f"This is the worker session for board item {self.item}", out)
        self.assertNotIn("Do not edit project files", out)

    def test_the_worker_hooks_do_nothing_in_any_other_session(self):
        for event in ("session-start", "stop", "permission"):  # a project with no worker sessions at all
            quiet = self.hook(self.root, event, {"session_id": "the-coordinator", "cwd": str(self.root)})
            self.assertEqual((quiet.returncode, quiet.stdout, quiet.stderr), (0, "", ""))
        self.assertFalse((self.root / ".git/pm-workers").exists(), "and they leave nothing behind")
        self.ready()
        self.cli("worker", "start", self.item, input_text="Ari")
        before = self.state(self.item)
        for event in ("session-start", "stop", "permission"):  # the coordinating session, next to a worker's record
            quiet = self.hook(self.root, event, {"session_id": "the-coordinator", "cwd": str(self.root),
                                                 "last_assistant_message": "Nothing to do with the worker.", "tool_name": "Bash"})
            self.assertEqual((quiet.returncode, quiet.stdout, quiet.stderr), (0, "", ""))
        self.assertEqual(self.state(self.item), before)
        note = self.hook(self.root, "", {"session_id": "the-coordinator"}, script=START_HOOK).stdout
        self.assertIn("Do not edit project files in this session yourself", note)

    def test_no_part_of_the_plugin_starts_a_headless_run(self):
        code = [*(REPO / "scripts").glob("*.py"), *(REPO / "hooks").iterdir()]
        for path in code:
            text = path.read_text()
            for headless in ('"-p"', "--print", "stream-json", "--output-format", "claude_agent_sdk", "claude -p"):
                self.assertNotIn(headless, text, f"{path.name} must not depend on a non-interactive run")
        for path in [*(REPO / "skills").glob("*/SKILL.md"), *(REPO / "agents").glob("*.md")]:
            self.assertNotIn("claude -p", path.read_text(), f"{path} must not tell a session to start a headless run")
        hooks = json.loads((REPO / "hooks" / "hooks.json").read_text())["hooks"]
        listener = [hook for group in hooks["Stop"] for hook in group["hooks"] if "worker.sh" in hook["command"]]
        self.assertEqual([(hook["asyncRewake"], hook["timeout"]) for hook in listener], [(True, 86400)],
                         "the mailbox listener wakes an idle session and outlives a long wait")
        refused = subprocess.run([self.env["PM_CLAUDE"], "-p", "hello"], env=self.env, capture_output=True, text=True)
        self.assertEqual(refused.returncode, 2, "the stand-in these tests run against has no print mode either")


if __name__ == "__main__":
    unittest.main()
