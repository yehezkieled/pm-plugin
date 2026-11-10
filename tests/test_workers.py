import contextlib
import io
import json
import os
import shutil
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

sys.path.insert(0, str(REPO / "scripts"))
import pm  # noqa: E402
import pm_workers  # noqa: E402


def gone(pid):
    """True when no process with this pid is running (a zombie awaiting its parent counts as gone)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    stat = Path(f"/proc/{pid}/stat")
    return stat.exists() and stat.read_text().rsplit(")", 1)[1].split()[0] == "Z"


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
        for key in ("FAKE_CLAUDE_MODE", "FAKE_CLAUDE_SLEEP", "FAKE_CLAUDE_LINGER", "FAKE_CLAUDE_BACKGROUND", "PM_WORKER",
                    "PM_WORKER_EXTRA_ARGS", "CLAUDE_CODE_EXECPATH"):
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

    def finish_on_its_branch(self, item):
        """What a lone worker leaves behind: the item Done on pm/ITEM, and the person's checkout parked there."""
        self.cli("claim", item, input_text="Ari")
        self.git("switch", "-qc", f"pm/{item}")
        (self.root / f"{item}.txt").write_text("the work\n")
        self.git("add", f"{item}.txt")
        self.git("commit", "-qm", f"{item}: the work")
        self.cli("validated", item, "--verdict", "pass", input_text="Checked.")
        self.cli("finish", item, input_text="Done.")

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

    # ---- a worker's turn ends with its report: nothing keeps its process, or the coordinator, waiting after it

    def test_workers_are_not_given_tools_that_schedule_a_later_turn(self):
        self.ready()
        self.cli("worker", "start", self.item, input_text="Ari")
        self.cli("worker", "answer", self.item, "--allow", "Bash(npm test:*)", input_text="Carry on.")
        for call in self.calls_made():
            argv = call["argv"]
            denied = argv[argv.index("--disallowedTools") + 1:argv.index("--model")]
            self.assertEqual(denied, ["ScheduleWakeup", "CronCreate"],
                             "a wakeup left scheduled keeps a headless session open after its final report")

    def test_a_worker_left_open_after_its_final_report_is_stopped_and_its_report_returned(self):
        self.ready()
        env = dict(self.env, FAKE_CLAUDE_LINGER="120")  # as a session does with a wakeup scheduled 20 minutes out
        began = time.time()
        code, out, err = self.cli_here("worker", "start", self.item, input_text="Ari", env=env, IDLE_GRACE_SECONDS=1)
        self.assertEqual(code, 0, err)
        self.assertLess(time.time() - began, 30, "the coordinator gets the report without waiting for the process")
        self.assertIn("Report:\nResult: done", out)
        self.assertIn("was still open 1 seconds after its final report", out)
        self.assertIn(f"`pm.py worker answer {self.item}` continues it", out)
        state = self.state(self.item)
        self.assertTrue(gone(state["pid"]), "no worker process is left running after its turn")
        self.assertEqual((state["running"], state["exit_code"]), (False, 0))
        self.assertIn("turn ended: Result: done", self.cli("worker", "list").stdout)
        answered = self.cli("worker", "answer", self.item, input_text="One more thing.")  # the conversation is kept
        self.assertIn("Seen: One more thing.", answered.stdout)
        self.assertNotIn("was still open", answered.stdout)

    def test_a_worker_waiting_on_its_validator_is_not_stopped_after_an_early_report(self):
        self.ready()
        env = dict(self.env, FAKE_CLAUDE_BACKGROUND="4")
        code, out, err = self.cli_here("worker", "start", self.item, input_text="Ari", env=env, IDLE_GRACE_SECONDS=1)
        self.assertEqual(code, 0, err)
        self.assertIn("Report:\nResult: done", out, "it waited for the report that followed the background task")
        self.assertNotIn("was still open", out)
        self.assertNotIn("stopped-after-report", (self.root / ".git/pm-workers/sessions" / f"{self.item}.log").read_text())

    def test_an_unwatched_worker_left_open_is_stopped_by_the_next_worker_command(self):
        self.ready()
        env = dict(self.env, FAKE_CLAUDE_LINGER="120")
        self.cli("worker", "start", self.item, "--no-wait", input_text="Ari", env=env)
        pid = self.state(self.item)["pid"]
        deadline = time.time() + 20
        while "turn ended" not in self.cli_here("worker", "list", IDLE_GRACE_SECONDS=1)[1] and time.time() < deadline:
            time.sleep(0.5)
        self.assertTrue(gone(pid), "listing the workers stops one whose turn ended but whose process stayed open")
        self.assertIn("was still open", self.cli("worker", "wait", self.item).stdout)
        self.cli("worker", "remove", self.item)

    # ---- the claude executable is found for every worker action, also while an update replaces it

    def lookup_env(self):
        """An environment where `claude` is found only where the test puts it: no real install is reachable."""
        tools = Path(self.temp.name) / "tools"
        tools.mkdir()
        home = Path(self.temp.name) / "home"
        home.mkdir()
        rest = [folder for folder in self.env["PATH"].split(os.pathsep) if folder and not (Path(folder) / "claude").exists()]
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
        env, tools, _ = self.lookup_env()
        self.reinstall_soon(tools / "claude")  # gone when the answer is sent, back two seconds later
        answered = self.cli("worker", "answer", self.item, input_text="The owner answered: yes.", env=env)
        self.assertIn("Seen: The owner answered: yes.", answered.stdout)
        self.assertEqual(self.flag(self.calls_made()[1], "--resume"), self.flag(self.calls_made()[0], "--session-id"))

    def test_start_survives_a_claude_that_cannot_run_yet(self):
        self.ready()
        env, tools, _ = self.lookup_env()
        half_written = tools / "claude"
        half_written.write_text("#!/no/such/interpreter\n")  # found by name, but it cannot be started
        half_written.chmod(0o755)
        self.reinstall_soon(half_written)
        started = self.cli("worker", "start", self.item, input_text="Ari", env=env)
        self.assertIn("Report:\nResult: done", started.stdout)

    def test_a_missing_claude_is_reported_with_every_place_looked(self):
        self.ready()
        env, tools, home = self.lookup_env()
        env["CLAUDE_CODE_EXECPATH"] = "/opt/claude/versions/9/claude"
        code, out, err = self.cli_here("worker", "start", self.item, input_text="Ari", env=env, CLAUDE_WAIT_SECONDS=1)
        self.assertEqual(code, 1)
        for looked in ("No `claude` executable was found after looking for 1 seconds", "`claude` on PATH (claude)",
                       "CLAUDE_CODE_EXECPATH, the Claude Code running this session (/opt/claude/versions/9/claude)",
                       f"({home}/.local/bin/claude)", f"({home}/.claude/local/claude)", f"PATH is '{env['PATH']}'",
                       "set PM_CLAUDE to its full path"):
            self.assertIn(looked, err)
        self.assertEqual(self.calls_made(), [])
        env["PM_CLAUDE"] = "/nowhere/claude"
        code, out, err = self.cli_here("worker", "start", self.item, input_text="Ari", env=env, CLAUDE_WAIT_SECONDS=0)
        self.assertIn("Looked for: PM_CLAUDE (/nowhere/claude).", err, "the person's own path is the only place looked")

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
        call = self.calls_made()[-1]
        self.assertEqual(call["branch"], home, "the lone worker starts on the board's branch")
        self.assertEqual(call["head"], self.git("rev-parse", home))

        third = self.add("Count pages", "Add a page count")
        self.git("switch", "-q", f"pm/{self.item}")
        self.cli("worker", "start", third, input_text="Ari")  # in its own worktree
        call = self.calls_made()[-1]
        self.assertEqual(call["head"], self.git("rev-parse", home), "its worktree starts at the board branch's tip")
        self.assertEqual(self.git("branch", "--show-current"), home)
        carried = subprocess.run(["git", "merge-base", "--is-ancestor", finished, call["head"]], cwd=self.root)
        self.assertNotEqual(carried.returncode, 0, "the new item's start does not carry the finished item's commits")

    def test_an_items_own_branch_and_an_unfinished_one_are_left_alone(self):
        self.ready()
        second = self.add("Count lines", "Add a line count")
        self.cli("claim", self.item, input_text="Ari")
        self.git("switch", "-qc", f"pm/{self.item}")
        kept = self.cli("claim", self.item, "--resume", input_text="Ari")  # the item's own worker, on its own branch
        self.assertNotIn("returned to", kept.stdout)
        self.assertEqual(self.git("branch", "--show-current"), f"pm/{self.item}")
        for new_work in (("add",), ("claim", second), ("worker", "start", second), ("worker", "start", second, "--here")):
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
        self.assertEqual(self.calls_made()[-1]["head"], shared, "not the coordinating checkout's commit")

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
