import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures import make_repo  # noqa: E402

PM = Path(__file__).resolve().parents[1] / "scripts" / "pm.py"


def run(root, *args, expect=0):
    proc = subprocess.run([sys.executable, str(PM), "--root", str(root), *args],
                          capture_output=True, text=True)
    if expect is not None:
        assert proc.returncode == expect, f"exit {proc.returncode}\nstdout:{proc.stdout}\nstderr:{proc.stderr}"
    return proc


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_repo(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_board_and_line(self):
        self.assertIn("M1: First usable version (current) 1/5 done", run(self.root, "board").stdout)
        self.assertIn("ready: T002, T004, T006", run(self.root, "line").stdout)

    def test_next_text_and_json_and_routine(self):
        self.assertTrue(run(self.root, "next").stdout.startswith("T002 "))
        data = json.loads(run(self.root, "next", "--json").stdout)
        self.assertEqual(data["id"], "T002")
        self.assertEqual(data["epic"], "E01")
        self.assertTrue(run(self.root, "next", "--routine").stdout.startswith("T004 "))
        for t in (self.root / "docs/pm/tickets").glob("*.md"):
            t.write_text(t.read_text().replace("status: todo", "status: done"))
        self.assertEqual(run(self.root, "next").stdout.strip(), "none")

    def test_claim_release_and_set(self):
        out = run(self.root, "claim", "T002", "api-work").stdout
        self.assertIn("T002 claimed by api-work", out)
        self.assertIn("owner: api-work", (self.root / "docs/pm/tickets/T002-rate-limit.md").read_text())
        self.assertIn("status: in progress", (self.root / "docs/pm/tickets/T002-rate-limit.md").read_text())
        proc = run(self.root, "claim", "T002", "someone-else", expect=1)
        self.assertIn("already claimed by api-work", proc.stderr)
        run(self.root, "set", "T002", "status=review", "pr=40")
        text = (self.root / "docs/pm/tickets/T002-rate-limit.md").read_text()
        self.assertIn("status: review", text)
        self.assertIn("pr: 40", text)
        run(self.root, "release", "T002")
        text = (self.root / "docs/pm/tickets/T002-rate-limit.md").read_text()
        self.assertIn("owner:\n", text)
        self.assertIn("status: todo", text)
        proc = run(self.root, "set", "T002", "status=finished", expect=1)
        self.assertIn("status must be one of", proc.stderr)

    def test_flow_updates_epic_file(self):
        out = run(self.root, "flow", "E01").stdout
        self.assertIn("T001 -> T002 -> T003", out)
        self.assertIn("T001 -> T002 -> T003", (self.root / "docs/pm/epics/E01-login.md").read_text())
        out = run(self.root, "flow", "--all").stdout
        self.assertIn("E02", out)

    def test_validate_exit_codes(self):
        proc = run(self.root, "validate", expect=1)
        self.assertIn("T007: owner set but status is todo", proc.stdout)
        p7 = self.root / "docs/pm/tickets/T007-share-revoke.md"
        p7.write_text(p7.read_text().replace("owner: agent-b", "owner:"))
        self.assertEqual(run(self.root, "validate").stdout.strip(), "ok")

    def test_next_id_and_config(self):
        self.assertEqual(run(self.root, "next-id", "ticket").stdout.strip(), "T008")
        self.assertEqual(run(self.root, "next-id", "epic").stdout.strip(), "E03")
        cfg = run(self.root, "config").stdout
        self.assertIn("flow: branch-pr", cfg)
        self.assertIn("check: make test", cfg)
        data = json.loads(run(self.root, "config", "--json").stdout)
        self.assertEqual(data["merge"], "ask")

    def test_new_ticket_epic_milestone(self):
        out = run(self.root, "new", "ticket", "--title", "Password reset email", "--epic", "E01",
                  "--priority", "P1", "--depends", "T002,T004", "--auto", "--plan", "required").stdout
        path = self.root / "docs/pm/tickets/T008-password-reset-email.md"
        self.assertIn(str(path), out)
        text = path.read_text()
        self.assertIn("id: T008", text)
        self.assertIn("milestone: M1", text)  # taken from the epic
        self.assertIn("depends_on: [T002, T004]", text)
        self.assertIn("auto: yes", text)
        self.assertIn("plan: required", text)
        self.assertIn("## Acceptance", text)
        # epic sections were redrawn
        self.assertIn("- T008 todo P1 Password reset email", (self.root / "docs/pm/epics/E01-login.md").read_text())

        out = run(self.root, "new", "epic", "--title", "Billing", "--milestone", "M2").stdout
        epath = self.root / "docs/pm/epics/E03-billing.md"
        self.assertTrue(epath.exists())
        self.assertIn("milestone: M2", epath.read_text())
        self.assertIn("E03", (self.root / "docs/pm/roadmap.md").read_text())

        run(self.root, "new", "milestone", "--title", "Teams", "--goal", "Many people share one list")
        roadmap = (self.root / "docs/pm/roadmap.md").read_text()
        self.assertIn("## M3: Teams\nGoal: Many people share one list", roadmap)
        self.assertLess(roadmap.index("## M3"), roadmap.index("## Backlog"))

    def test_new_ticket_refuses_unknown_epic(self):
        proc = run(self.root, "new", "ticket", "--title", "x", "--epic", "E42", expect=1)
        self.assertIn("unknown epic E42", proc.stderr)

    def test_runs_outside_a_pm_repo(self):
        empty = Path(self.tmp.name) / "empty"
        empty.mkdir()
        self.assertEqual(run(empty, "line").stdout.strip(), "")
        proc = run(empty, "board", expect=1)
        self.assertIn("no docs/pm", proc.stderr)


if __name__ == "__main__":
    unittest.main()


class RoadmapEpicListTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_repo(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_new_epic_does_not_duplicate_ids_already_listed(self):
        roadmap = self.root / "docs/pm/roadmap.md"
        roadmap.write_text(roadmap.read_text().replace("Epics: E02", "Epics: E02, E03"))
        run(self.root, "new", "epic", "--title", "Billing", "--milestone", "M2")
        text = roadmap.read_text()
        self.assertIn("Epics: E02, E03\n", text)
        self.assertEqual(text.count("E03"), 1)

    def test_new_epic_replaces_none_yet_placeholder(self):
        roadmap = self.root / "docs/pm/roadmap.md"
        roadmap.write_text(roadmap.read_text().replace("Epics: E02", "Epics: (none yet)"))
        run(self.root, "new", "epic", "--title", "Billing", "--milestone", "M2")
        self.assertIn("Epics: E03\n", roadmap.read_text())

    def test_new_epic_matches_ids_written_with_a_slug(self):
        roadmap = self.root / "docs/pm/roadmap.md"
        roadmap.write_text(roadmap.read_text().replace("Epics: E02", "Epics: E02-sharing, E03-billing"))
        run(self.root, "new", "epic", "--title", "Billing", "--milestone", "M2")
        text = roadmap.read_text()
        self.assertEqual(text.count("E03"), 1)


class ClaimGuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_repo(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_claim_refuses_open_dependency_unless_forced(self):
        proc = run(self.root, "claim", "T003", "someone", expect=1)
        self.assertIn("T003 depends on T002 (todo)", proc.stderr)
        self.assertIn("status: todo", (self.root / "docs/pm/tickets/T003-lockout.md").read_text())
        run(self.root, "claim", "T003", "someone", "--force")
        self.assertIn("owner: someone", (self.root / "docs/pm/tickets/T003-lockout.md").read_text())

    def test_claim_prints_next_commands_for_the_flow(self):
        out = run(self.root, "claim", "T002", "api-work").stdout
        self.assertIn('git add docs/pm && git commit -m "pm: claim T002" && git push', out)
        self.assertIn("git switch -c t002-rate-limit", out)
        self.assertNotIn("plan: required", out)

    def test_claim_warns_when_plan_is_required_and_not_approved(self):
        out = run(self.root, "claim", "T006", "api-work").stdout
        self.assertIn("plan: required", out)
        self.assertIn("approval before any code edit", out)


class BackupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_repo(Path(self.tmp.name) / "myrepo")
        self.dest = Path(self.tmp.name) / "backups"

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, *args, expect=0):
        import os
        env = dict(os.environ, PM_BACKUP_DIR=str(self.dest))
        proc = subprocess.run([sys.executable, str(PM), "--root", str(self.root), *args],
                              capture_output=True, text=True, env=env)
        assert proc.returncode == expect, f"exit {proc.returncode}\nstdout:{proc.stdout}\nstderr:{proc.stderr}"
        return proc

    def test_not_a_fork_makes_no_copy(self):
        out = self._run("backup").stdout
        self.assertIn("not a fork", out)
        self.assertFalse(self.dest.exists())

    def test_fork_copies_docs_and_context(self):
        (self.root / ".git/info").mkdir(parents=True)
        (self.root / ".git/info/exclude").write_text("docs/pm/\nCONTEXT.md\n")
        out = self._run("backup").stdout
        self.assertIn(str(self.dest / "myrepo"), out)
        self.assertTrue((self.dest / "myrepo/docs/pm/roadmap.md").exists())
        self.assertTrue((self.dest / "myrepo/docs/pm/tickets/T001-counter.md").exists())
        self.assertTrue((self.dest / "myrepo/CONTEXT.md").exists())


class FreezeTest(unittest.TestCase):
    """Bug fixes freeze the test files: pm.py freeze / unfreeze --reason, cleared when the ticket is done."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_repo(Path(self.tmp.name))
        self.t5 = self.root / "docs/pm/tickets/T005-session.md"

    def tearDown(self):
        self.tmp.cleanup()

    def test_freeze_sets_the_field(self):
        out = run(self.root, "freeze", "T005").stdout
        self.assertIn("tests: frozen", self.t5.read_text())
        self.assertIn("frozen", out)

    def test_unfreeze_needs_a_reason_and_records_it(self):
        run(self.root, "freeze", "T005")
        proc = run(self.root, "unfreeze", "T005", expect=None)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("tests: frozen", self.t5.read_text())
        run(self.root, "unfreeze", "T005", "--reason", "the old test expected the buggy order")
        text = self.t5.read_text()
        self.assertIn("tests: open", text)
        self.assertIn("Test change: the old test expected the buggy order", text.split("## Notes")[1])

    def test_done_clears_the_freeze(self):
        run(self.root, "freeze", "T005")
        run(self.root, "set", "T005", "status=done")
        self.assertIn("tests: open", self.t5.read_text())

    def test_validate_rejects_other_values(self):
        run(self.root, "set", "T005", "tests=maybe", expect=None)
        self.t5.write_text(self.t5.read_text().replace("owner: agent-a", "owner: agent-a\ntests: maybe"))
        out = run(self.root, "validate", expect=1).stdout
        self.assertIn("T005: tests must be open or frozen", out)


class DismissTest(unittest.TestCase):
    """A finding can be closed without doing it: status dismissed, with a reason."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_repo(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_dismiss_needs_a_reason(self):
        proc = run(self.root, "dismiss", "T004", expect=None)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("status: todo", (self.root / "docs/pm/tickets/T004-log-format.md").read_text())

    def test_dismiss_sets_status_clears_owner_and_notes_the_reason(self):
        run(self.root, "dismiss", "T007", "--reason", "duplicate of T006")
        text = (self.root / "docs/pm/tickets/T007-share-revoke.md").read_text()
        self.assertIn("status: dismissed", text)
        self.assertIn("owner:\n", text)
        self.assertIn("Dismissed: duplicate of T006", text.split("## Notes")[1])
        run(self.root, "validate")  # no longer "owner set but status is todo"

    def test_dismissed_leaves_the_counts_and_the_ready_list(self):
        run(self.root, "dismiss", "T004", "--reason", "not worth it")
        board = run(self.root, "board").stdout
        self.assertIn("M1: First usable version (current) 1/4 done, 1 dismissed", board)
        self.assertIn("E01 Login  1/4 done, 1 dismissed", board)
        self.assertIn("T004 dismissed", board)
        self.assertIn("ready: T002, T006", run(self.root, "line").stdout)

    def test_validate_flags_a_dependency_on_a_dismissed_ticket(self):
        run(self.root, "dismiss", "T002", "--reason", "rate limiting moved to the gateway")
        out = run(self.root, "validate", expect=1).stdout
        self.assertIn("T003: depends on dismissed T002", out)


class ConfidenceTest(unittest.TestCase):
    """Audit findings carry a confidence rating."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_repo(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_new_ticket_with_confidence(self):
        out = run(self.root, "new", "ticket", "--title", "Bug: average of an empty list crashes", "--epic", "E01",
                  "--confidence", "medium", "--what", "x", "--why", "z", "--acceptance", "y").stdout
        path = self.root / out.split("created ")[1].strip()
        self.assertIn("confidence: medium", path.read_text())
        self.assertIn("T008 todo P2 Bug: average of an empty list crashes  not grilled  confidence: medium", run(self.root, "board").stdout)
        self.assertNotIn("T008", run(self.root, "validate", expect=None).stdout)  # the fixture's T007 is the only problem

    def test_confidence_values_are_checked(self):
        run(self.root, "new", "ticket", "--title", "x", "--epic", "E01", "--confidence", "sure", expect=2)
        proc = run(self.root, "set", "T004", "confidence=sure", expect=None)
        self.assertNotEqual(proc.returncode, 0)


class GrillCliTest(unittest.TestCase):
    """A ticket is created thin (`ready: no`); /pm:grill sets `ready: yes`; work refuses a ticket that was not grilled."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_repo(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def ticket(self, tid):
        return next((self.root / "docs/pm/tickets").glob(f"{tid}-*.md")).read_text()

    def test_new_ticket_is_thin_unless_grilled_at_creation(self):
        run(self.root, "new", "ticket", "--title", "Remember me box", "--epic", "E01")
        self.assertIn("ready: no\n", self.ticket("T008"))
        run(self.root, "new", "ticket", "--title", "Bug: space in password", "--epic", "E01", "--ready")
        self.assertIn("ready: yes\n", self.ticket("T009"))

    def test_claim_refuses_a_ticket_that_was_not_grilled(self):
        run(self.root, "new", "ticket", "--title", "Remember me box", "--epic", "E01")
        proc = run(self.root, "claim", "T008", "api-work", expect=1)
        self.assertIn("T008 is not grilled yet", proc.stderr)
        self.assertIn("/pm:grill T008", proc.stderr)
        self.assertIn("status: todo", self.ticket("T008"))
        run(self.root, "claim", "T008", "api-work", "--force")
        self.assertIn("owner: api-work", self.ticket("T008"))

    def test_set_ready_yes_makes_the_ticket_claimable(self):
        run(self.root, "new", "ticket", "--title", "Remember me box", "--epic", "E01")
        run(self.root, "set", "T008", "ready=yes")
        self.assertIn("ready: yes\n", self.ticket("T008"))
        self.assertIn("T008 claimed by api-work", run(self.root, "claim", "T008", "api-work").stdout)

    def test_next_skips_ungrilled_tickets_and_says_what_to_grill(self):
        t4 = self.root / "docs/pm/tickets/T004-log-format.md"
        t4.write_text(t4.read_text().replace("ready: yes", "ready: no"))
        self.assertTrue(run(self.root, "next").stdout.startswith("T002 "))
        self.assertEqual(json.loads(run(self.root, "next", "--json").stdout)["ready"], True)
        self.assertTrue(run(self.root, "next", "--routine").stdout.startswith("none (to grill: T004"))
        for t in (self.root / "docs/pm/tickets").glob("*.md"):
            if "T004" not in t.name:
                t.write_text(t.read_text().replace("status: todo", "status: done"))
        out = run(self.root, "next").stdout
        self.assertTrue(out.startswith("none"))
        self.assertIn("to grill: T004", out)
        self.assertIn("/pm:grill", out)


class ReadyCommandTest(unittest.TestCase):
    """`pm.py ready Txxx` is how /pm:grill marks a ticket; a blocked ticket needs --early, given only on the user's word."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_repo(Path(self.tmp.name))
        for tid in ("T002-rate-limit", "T003-lockout"):
            p = self.root / f"docs/pm/tickets/{tid}.md"
            p.write_text(p.read_text().replace("ready: yes", "ready: no"))

    def tearDown(self):
        self.tmp.cleanup()

    def text(self, tid):
        return next((self.root / "docs/pm/tickets").glob(f"{tid}-*.md")).read_text()

    def test_ready_marks_an_unblocked_ticket(self):
        out = run(self.root, "ready", "T002").stdout
        self.assertIn("T002 ready", out)
        self.assertIn("ready: yes", self.text("T002"))
        self.assertIn("/pm:work T002", out)

    def test_ready_refuses_a_blocked_ticket_unless_early(self):
        proc = run(self.root, "ready", "T003", expect=1)
        self.assertIn("T003 waits on T002", proc.stderr)
        self.assertIn("--early", proc.stderr)
        self.assertIn("ready: no", self.text("T003"))
        proc = run(self.root, "set", "T003", "ready=yes", expect=1)
        self.assertIn("--early", proc.stderr)
        out = run(self.root, "ready", "T003", "--early").stdout
        self.assertIn("ready: yes", self.text("T003"))
        self.assertIn("grilled early", out)
        self.assertIn("T002", out)
