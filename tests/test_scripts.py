import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures import make_repo  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def sh(script, cwd, stdin="", env=None):
    full_env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT), CLAUDE_PROJECT_DIR=str(cwd))
    full_env.update(env or {})
    return subprocess.run(["bash", str(ROOT / script)], cwd=cwd, input=stdin,
                          capture_output=True, text=True, env=full_env)


def kv(text):
    return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t"))


class DoctorTest(unittest.TestCase):
    def test_reports_tools_and_pm_presence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp))
            out = kv(sh("scripts/doctor.sh", root).stdout)
            self.assertEqual(out["python3"], "yes")
            self.assertEqual(out["git"], "yes")
            self.assertIn(out["gh"], ("yes", "no"))
            self.assertEqual(out["pm"], "yes")
            empty = Path(tmp) / "empty"
            empty.mkdir()
            self.assertEqual(kv(sh("scripts/doctor.sh", empty).stdout)["pm"], "no")


class DetectTest(unittest.TestCase):
    def test_node_repo_with_github_remote(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            git(root, "init", "-q", "-b", "main")
            (root / "package.json").write_text('{"scripts": {"test": "jest", "lint": "eslint ."}}')
            (root / "README.md").write_text("# x")
            (root / "docs").mkdir()
            (root / "docs" / "ROADMAP.md").write_text("old plan")
            (root / "TODO.md").write_text("- old todo")
            git(root, "add", ".")
            git(root, "commit", "-q", "-m", "init")
            git(root, "remote", "add", "origin", "git@github.com:someone/thing.git")
            out = kv(sh("scripts/pm_detect.sh", root).stdout)
            self.assertEqual(out["git"], "yes")
            self.assertEqual(out["host"], "github")
            self.assertEqual(out["remote"], "git@github.com:someone/thing.git")
            self.assertEqual(out["branch"], "main")
            self.assertEqual(out["languages"], "node")
            self.assertEqual(out["check_guess"], "npm run lint && npm test")
            self.assertEqual(out["readme"], "yes")
            self.assertEqual(out["context_md"], "no")
            self.assertEqual(out["pm"], "no")
            self.assertEqual(out["planning_docs"], "TODO.md,docs/ROADMAP.md")
            self.assertEqual(out["commits"], "1")
            self.assertEqual(out["flow_suggest"], "branch-pr")

    def test_python_repo_without_remote(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            git(root, "init", "-q", "-b", "main")
            (root / "pyproject.toml").write_text("[project]\nname='x'\n")
            (root / "Makefile").write_text("test:\n\tpytest\n")
            (root / "CONTEXT.md").write_text("# ctx")
            out = kv(sh("scripts/pm_detect.sh", root).stdout)
            self.assertEqual(out["host"], "none")
            self.assertEqual(out["remote"], "")
            self.assertIn("python", out["languages"])
            self.assertEqual(out["check_guess"], "make test")
            self.assertEqual(out["context_md"], "yes")
            self.assertEqual(out["commits"], "0")
            self.assertEqual(out["flow_suggest"], "branch-local")

    def test_folder_without_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = kv(sh("scripts/pm_detect.sh", Path(tmp)).stdout)
            self.assertEqual(out["git"], "no")
            self.assertEqual(out["host"], "none")
            self.assertEqual(out["flow_suggest"], "direct")


class HookTest(unittest.TestCase):
    def test_session_start_prints_board_line_only_with_pm(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp))
            out = sh("hooks/session-start.sh", root, stdin=json.dumps({"cwd": str(root)})).stdout
            self.assertIn("pm: M1 1/5 done", out)
            self.assertIn("/pm:status", out)
            empty = Path(tmp) / "empty"
            empty.mkdir()
            self.assertEqual(sh("hooks/session-start.sh", empty, stdin=json.dumps({"cwd": str(empty)})).stdout, "")

    def test_stop_warns_once_when_code_changed_but_no_ticket(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp) / "repo")
            git(root, "init", "-q", "-b", "main")
            (root / "app.py").write_text("print(1)\n")
            git(root, "add", ".")
            git(root, "commit", "-q", "-m", "init")
            state = Path(tmp) / "state"
            env = {"CLAUDE_PLUGIN_DATA": str(state)}
            payload = json.dumps({"cwd": str(root), "session_id": "s1", "stop_hook_active": False})
            # nothing changed: silent
            proc = sh("hooks/stop.sh", root, stdin=payload, env=env)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout.strip(), "")
            # code changed, no ticket touched: warn
            (root / "app.py").write_text("print(2)\n")
            proc = sh("hooks/stop.sh", root, stdin=payload, env=env)
            self.assertEqual(proc.returncode, 0)
            data = json.loads(proc.stdout)
            self.assertIn("no ticket", data["systemMessage"])
            # same state again: stay quiet
            proc = sh("hooks/stop.sh", root, stdin=payload, env=env)
            self.assertEqual(proc.stdout.strip(), "")
            # a ticket changed too: no warning
            (root / "app.py").write_text("print(3)\n")
            t = root / "docs/pm/tickets/T002-rate-limit.md"
            t.write_text(t.read_text().replace("status: todo", "status: in progress"))
            proc = sh("hooks/stop.sh", root, stdin=payload, env=env)
            self.assertEqual(proc.stdout.strip(), "")

    def test_stop_is_silent_outside_pm_repos(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = sh("hooks/stop.sh", Path(tmp), stdin=json.dumps({"cwd": tmp, "session_id": "s2"}))
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout.strip(), "")

    def test_hooks_json_points_at_scripts(self):
        data = json.loads((ROOT / "hooks" / "hooks.json").read_text())
        cmds = [h["command"] for group in data["hooks"].values() for entry in group for h in entry["hooks"]]
        self.assertTrue(any("session-start.sh" in c for c in cmds))
        self.assertTrue(any("stop.sh" in c for c in cmds))
        self.assertEqual(set(data["hooks"]), {"SessionStart", "PreToolUse", "Stop"})


if __name__ == "__main__":
    unittest.main()


class StopHookIgnoresGeneratedFilesTest(unittest.TestCase):
    def test_generated_files_alone_do_not_warn(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp) / "repo")
            git(root, "init", "-q", "-b", "main")
            (root / "app.py").write_text("print(1)\n")
            git(root, "add", ".")
            git(root, "commit", "-q", "-m", "init")
            (root / "__pycache__").mkdir()
            (root / "__pycache__" / "app.cpython-312.pyc").write_bytes(b"\x00")
            (root / "node_modules" / "x").mkdir(parents=True)
            (root / "node_modules" / "x" / "index.js").write_text("1")
            (root / ".pytest_cache").mkdir()
            (root / ".pytest_cache" / "v").write_text("1")
            env = {"CLAUDE_PLUGIN_DATA": str(Path(tmp) / "state")}
            payload = json.dumps({"cwd": str(root), "session_id": "s3"})
            proc = sh("hooks/stop.sh", root, stdin=payload, env=env)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout.strip(), "")


class PlanGateHookTest(unittest.TestCase):
    """hooks/plan-gate.sh: a PreToolUse hook that blocks code edits until the ticket's plan exists and is approved."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_repo(Path(self.tmp.name) / "repo")
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "add", ".")
        git(self.root, "commit", "-q", "-m", "initial")

    def tearDown(self):
        self.tmp.cleanup()

    def gate(self, tool, tool_input):
        payload = json.dumps({"tool_name": tool, "tool_input": tool_input, "cwd": str(self.root)})
        return sh("hooks/plan-gate.sh", self.root, stdin=payload)

    def set_plan(self, tid_file, approach="", approved="no"):
        p = self.root / "docs/pm/tickets" / tid_file
        s = p.read_text()
        s = s.split("## Plan")[0] + f"## Plan\nApproach: {approach}\nTouches: x\nTests first: y\nDecisions to record: none\napproved: {approved}\n\n## Notes\n\n## Proposed changes\n"
        p.write_text(s)

    def test_no_ticket_branch_means_no_gate(self):
        proc = self.gate("Edit", {"file_path": str(self.root / "app.py")})
        self.assertEqual(proc.returncode, 0)

    def test_blocks_code_edit_when_plan_is_empty(self):
        git(self.root, "switch", "-q", "-c", "t002-rate-limit")
        proc = self.gate("Edit", {"file_path": str(self.root / "app.py")})
        self.assertEqual(proc.returncode, 2)
        self.assertIn("T002", proc.stderr)
        self.assertIn("## Plan", proc.stderr)

    def test_allows_ticket_and_docs_edits_while_plan_is_empty(self):
        git(self.root, "switch", "-q", "-c", "t002-rate-limit")
        self.assertEqual(self.gate("Edit", {"file_path": str(self.root / "docs/pm/tickets/T002-rate-limit.md")}).returncode, 0)
        self.assertEqual(self.gate("Write", {"file_path": str(self.root / "docs/pm/decisions.md")}).returncode, 0)
        self.assertEqual(self.gate("Bash", {"command": "python3 -m unittest discover -s tests 2>&1 | tail -3"}).returncode, 0)
        self.assertEqual(self.gate("Bash", {"command": "git add docs/pm && git commit -m 'pm: claim T002'"}).returncode, 0)

    def test_blocks_bash_that_writes_code_while_plan_is_empty(self):
        git(self.root, "switch", "-q", "-c", "t002-rate-limit")
        self.assertEqual(self.gate("Bash", {"command": "cat > app.py <<'EOF'\nprint(1)\nEOF"}).returncode, 2)
        self.assertEqual(self.gate("Bash", {"command": "sed -i 's/a/b/' app.py"}).returncode, 2)

    def test_plan_written_and_not_required_allows_code(self):
        git(self.root, "switch", "-q", "-c", "t002-rate-limit")
        self.set_plan("T002-rate-limit.md", approach="add a counter")
        self.assertEqual(self.gate("Edit", {"file_path": str(self.root / "app.py")}).returncode, 0)

    def test_plan_required_blocks_until_approved(self):
        git(self.root, "switch", "-q", "-c", "t006-share-link")
        self.set_plan("T006-share-link.md", approach="token in the url")
        proc = self.gate("Edit", {"file_path": str(self.root / "app.py")})
        self.assertEqual(proc.returncode, 2)
        self.assertIn("approv", proc.stderr)
        self.set_plan("T006-share-link.md", approach="token in the url", approved="yes")
        self.assertEqual(self.gate("Edit", {"file_path": str(self.root / "app.py")}).returncode, 0)

    def test_hook_is_registered(self):
        cfg = json.loads((Path(__file__).resolve().parents[1] / "hooks/hooks.json").read_text())
        pre = cfg["hooks"]["PreToolUse"]
        cmds = [h["command"] for entry in pre for h in entry["hooks"]]
        self.assertTrue(any("plan-gate.sh" in c for c in cmds))
        self.assertTrue(any("Bash" in entry.get("matcher", "") and "Edit" in entry.get("matcher", "") for entry in pre))

    def test_gate_works_without_python3(self):
        """A machine without python3: the hook reads the JSON fields with grep instead."""
        nopy = Path(self.tmp.name) / "nopy-bin"
        nopy.mkdir()
        for d in os.environ.get("PATH", "").split(os.pathsep):
            for exe in (Path(d).glob("*") if Path(d).is_dir() else []):
                if exe.name.startswith("python") or (nopy / exe.name).exists():
                    continue
                (nopy / exe.name).symlink_to(exe)
        env = {"PATH": str(nopy)}
        probe = subprocess.run(["bash", "-c", "command -v python3"], env=dict(os.environ, **env), capture_output=True)
        self.assertNotEqual(probe.returncode, 0, "python3 is still on the test PATH")

        def gate(tool, tool_input):
            payload = json.dumps({"tool_name": tool, "tool_input": tool_input, "cwd": str(self.root)})
            return sh("hooks/plan-gate.sh", self.root, stdin=payload, env=env)

        git(self.root, "switch", "-q", "-c", "t002-rate-limit")
        blocked = gate("Edit", {"file_path": str(self.root / "app.py")})
        self.assertEqual(blocked.returncode, 2, blocked.stderr)
        self.assertIn("T002", blocked.stderr)
        self.assertEqual(gate("Bash", {"command": "cat > app.py <<'EOF'\nprint(1)\nEOF"}).returncode, 2)
        self.assertEqual(gate("Edit", {"file_path": str(self.root / "docs/pm/tickets/T002-rate-limit.md")}).returncode, 0)
        self.assertEqual(gate("Bash", {"command": "git add docs/pm && git commit -m 'pm: claim T002'"}).returncode, 0)
        self.set_plan("T002-rate-limit.md", approach="add a counter")
        self.assertEqual(gate("Edit", {"file_path": str(self.root / "app.py")}).returncode, 0)


class RoutineMergeGateTest(unittest.TestCase):
    """The gate also refuses merges on a ticket claimed by a routine (owner routine-*)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_repo(Path(self.tmp.name) / "repo")
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "add", ".")
        git(self.root, "commit", "-q", "-m", "initial")
        git(self.root, "switch", "-q", "-c", "t004-log-format")
        p = self.root / "docs/pm/tickets/T004-log-format.md"
        s = p.read_text().replace("owner: ", "owner: routine-t004").split("## Plan")[0]
        p.write_text(s + "## Plan\nApproach: tidy\nTouches: x\nTests first: y\nDecisions to record: none\napproved: no\n\n## Notes\n\n## Proposed changes\n")

    def tearDown(self):
        self.tmp.cleanup()

    def gate(self, command):
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(self.root)})
        return sh("hooks/plan-gate.sh", self.root, stdin=payload)

    def test_routine_owner_cannot_merge(self):
        proc = self.gate("git switch main && git merge --no-ff t004-log-format")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("routine", proc.stderr)
        self.assertEqual(self.gate("gh pr merge 12 --squash --delete-branch").returncode, 2)
        self.assertEqual(self.gate("git add calc.py && git commit -m 'T004: tidy'").returncode, 0)

    def test_person_owner_can_merge(self):
        p = self.root / "docs/pm/tickets/T004-log-format.md"
        p.write_text(p.read_text().replace("owner: routine-t004", "owner: work-t004"))
        self.assertEqual(self.gate("git switch main && git merge --no-ff t004-log-format").returncode, 0)


class NextRoutineHintTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_repo(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_next_routine_says_how_to_claim(self):
        proc = subprocess.run([sys.executable, str(ROOT / "scripts/pm.py"), "--root", str(self.root), "next", "--routine"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(proc.stdout.startswith("T004 "))
        self.assertIn("pm.py claim T004 routine-t004", proc.stdout)
        self.assertIn("never merge", proc.stdout)


class FreezeGateTest(unittest.TestCase):
    """plan-gate.sh also blocks test-file edits while the ticket says tests: frozen."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_repo(Path(self.tmp.name) / "repo")
        (self.root / "tests").mkdir()
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "add", ".")
        git(self.root, "commit", "-q", "-m", "initial")
        git(self.root, "switch", "-q", "-c", "t005-session")
        p = self.root / "docs/pm/tickets/T005-session.md"
        s = p.read_text().split("## Plan")[0] + "## Plan\nApproach: fix it\nTouches: x\nTests first: y\nDecisions to record: none\napproved: no\n\n## Notes\n\n## Proposed changes\n"
        p.write_text(s)
        self.ticket = p

    def tearDown(self):
        self.tmp.cleanup()

    def gate(self, tool, tool_input):
        payload = json.dumps({"tool_name": tool, "tool_input": tool_input, "cwd": str(self.root)})
        return sh("hooks/plan-gate.sh", self.root, stdin=payload)

    def freeze(self, owner="agent-a"):
        self.ticket.write_text(self.ticket.read_text().replace("owner: agent-a", f"owner: {owner}\ntests: frozen"))

    def test_open_ticket_allows_test_edits(self):
        self.assertEqual(self.gate("Edit", {"file_path": str(self.root / "tests/test_login.py")}).returncode, 0)

    def test_frozen_ticket_blocks_test_files_but_not_code(self):
        self.freeze()
        for path in ("tests/test_login.py", "test_login.py", "app_test.go", "src/__tests__/login.test.ts", "spec/login_spec.rb", "src/login.spec.js"):
            proc = self.gate("Edit", {"file_path": str(self.root / path)})
            self.assertEqual(proc.returncode, 2, path)
            self.assertIn("frozen", proc.stderr)
            self.assertIn("unfreeze T005", proc.stderr)
        self.assertEqual(self.gate("Write", {"file_path": str(self.root / "tests/conftest.py")}).returncode, 2)
        self.assertEqual(self.gate("Edit", {"file_path": str(self.root / "app.py")}).returncode, 0)
        self.assertEqual(self.gate("Edit", {"file_path": str(self.root / "docs/pm/tickets/T005-session.md")}).returncode, 0)

    def test_frozen_ticket_blocks_bash_that_writes_a_test_file(self):
        self.freeze()
        self.assertEqual(self.gate("Bash", {"command": "sed -i 's/5/6/' tests/test_login.py"}).returncode, 2)
        self.assertEqual(self.gate("Bash", {"command": "cat > tests/test_login.py <<'EOF'\nx\nEOF"}).returncode, 2)
        self.assertEqual(self.gate("Bash", {"command": "python3 -m unittest discover -s tests"}).returncode, 0)
        self.assertEqual(self.gate("Bash", {"command": "cat >> app.py <<'EOF'\nx\nEOF"}).returncode, 0)

    def test_a_person_may_unfreeze_a_routine_may_not(self):
        self.freeze()
        cmd = {"command": "python3 /plugin/scripts/pm.py unfreeze T005 --reason 'old test encoded the bug'"}
        self.assertEqual(self.gate("Bash", cmd).returncode, 0)
        self.freeze(owner="routine-t005")
        proc = self.gate("Bash", cmd)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("routine", proc.stderr)
        self.assertEqual(self.gate("Bash", {"command": "python3 /plugin/scripts/pm.py set T005 tests=open"}).returncode, 2)

    def test_unfrozen_again_allows_test_edits(self):
        self.freeze()
        self.ticket.write_text(self.ticket.read_text().replace("tests: frozen", "tests: open"))
        self.assertEqual(self.gate("Edit", {"file_path": str(self.root / "tests/test_login.py")}).returncode, 0)
