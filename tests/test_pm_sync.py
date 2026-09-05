import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pm_lib  # noqa: E402
import pm_sync  # noqa: E402
from adapters import github  # noqa: E402
from fixtures import make_repo  # noqa: E402


class FakeAdapter:
    def __init__(self):
        self.calls = []
        self.milestones = {}
        self.issues = {}
        self.counter = 100

    def list_milestones(self):
        return dict(self.milestones)

    def create_milestone(self, title, description):
        self.counter += 1
        self.milestones[title] = self.counter
        self.calls.append(("create_milestone", title))
        return self.counter

    def ensure_label(self, name):
        self.calls.append(("ensure_label", name))

    def create_issue(self, title, body, labels, milestone):
        self.counter += 1
        self.issues[self.counter] = dict(title=title, body=body, labels=labels, milestone=milestone, state="open")
        self.calls.append(("create_issue", title))
        return self.counter

    def update_issue(self, number, title, body, labels, milestone):
        self.issues[number].update(title=title, body=body, labels=labels, milestone=milestone)
        self.calls.append(("update_issue", number))

    def close_issue(self, number, reason=None):
        self.issues[number]["state"] = "closed"
        self.issues[number]["reason"] = reason
        self.calls.append(("close_issue", number, reason))
        self.calls.append(("close_issue", number))


class SyncTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_repo(Path(self.tmp.name))
        self.fake = FakeAdapter()

    def tearDown(self):
        self.tmp.cleanup()

    def test_first_sync_creates_everything_and_writes_numbers_back(self):
        log = pm_sync.sync(self.root, self.fake)
        self.assertIn("create_milestone", [c[0] for c in self.fake.calls])
        self.assertEqual(set(self.fake.milestones), {"M1: First usable version", "M2: Sharing"})
        tickets = {t.id: t for t in pm_lib.load_tickets(self.root)}
        self.assertTrue(all(t.issue for t in tickets.values()))
        epics = {e.id: e for e in pm_lib.load_epics(self.root)}
        self.assertTrue(all(e.meta.get("issue") for e in epics.values()))
        epic_issue = self.fake.issues[int(epics["E01"].meta["issue"])]
        self.assertEqual(epic_issue["labels"], ["epic"])
        self.assertIn(f"- [x] #{tickets['T001'].issue} T001 Add login attempt counter", epic_issue["body"])
        self.assertIn(f"- [ ] #{tickets['T002'].issue} T002 Rate-limit login attempts", epic_issue["body"])
        t1_issue = self.fake.issues[int(tickets["T001"].issue)]
        self.assertEqual(t1_issue["state"], "closed")
        self.assertEqual(t1_issue["labels"], ["E01", "P1"])
        self.assertEqual(t1_issue["milestone"], "M1: First usable version")
        self.assertIn("## Acceptance", t1_issue["body"])
        self.assertTrue(any("T001" in line and "created" in line for line in log))

    def test_second_sync_updates_instead_of_creating(self):
        pm_sync.sync(self.root, self.fake)
        creates_before = sum(1 for c in self.fake.calls if c[0] == "create_issue")
        pm_lib.set_fields(self.root, "T002", status="done")
        pm_sync.sync(self.root, self.fake)
        creates_after = sum(1 for c in self.fake.calls if c[0] == "create_issue")
        self.assertEqual(creates_before, creates_after)
        t2 = next(t for t in pm_lib.load_tickets(self.root) if t.id == "T002")
        self.assertEqual(self.fake.issues[int(t2.issue)]["state"], "closed")

    def test_dry_run_changes_nothing(self):
        log = pm_sync.sync(self.root, self.fake, dry_run=True)
        self.assertEqual(self.fake.calls, [])
        self.assertTrue(any("would create" in line for line in log))
        self.assertFalse(any(t.issue for t in pm_lib.load_tickets(self.root)))


class GithubAdapterTest(unittest.TestCase):
    def test_parses_issue_number_from_url(self):
        self.assertEqual(github.issue_number("https://github.com/o/r/issues/31\n"), 31)

    def test_builds_gh_commands(self):
        seen = []

        def runner(args):
            seen.append(args)
            if args[:2] == ["gh", "api"] and "milestones" in args[2] and "-X" not in args:
                return "7\tM1: First usable version\n"
            if args[:3] == ["gh", "issue", "create"]:
                return "https://github.com/o/r/issues/31\n"
            return "9\n"

        gh = github.GithubAdapter(runner=runner)
        self.assertEqual(gh.list_milestones(), {"M1: First usable version": 7})
        self.assertEqual(gh.create_milestone("M2: Sharing", "goal"), 9)
        self.assertEqual(gh.create_issue("T001: x", "body", ["E01", "P1"], "M1: First usable version"), 31)
        gh.update_issue(31, "T001: x", "body2", ["E01", "P1"], None)
        gh.close_issue(31)
        gh.ensure_label("epic")
        flat = [" ".join(a) for a in seen]
        self.assertTrue(any(f.startswith("gh issue create --title T001: x") and "--label E01 --label P1 --milestone M1: First usable version" in f for f in flat), flat)
        self.assertTrue(any(f.startswith("gh issue edit 31 --title T001: x --body body2 --add-label E01 --add-label P1") for f in flat), flat)
        self.assertIn("gh issue close 31", flat)
        self.assertIn("gh label create epic --force", flat)


if __name__ == "__main__":
    unittest.main()


class DismissedSyncTest(unittest.TestCase):
    def test_dismissed_ticket_closes_its_issue_as_not_planned_and_epic_can_close(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp))
            for tid in ("T002", "T003", "T005"):
                pm_lib.set_fields(root, tid, status="done", owner="")
            pm_lib.set_fields(root, "T004", status="dismissed", owner="")
            adapter = FakeAdapter()
            pm_sync.sync(root, adapter)
            t4 = pm_lib.load_tickets(root)
            t4 = next(t for t in t4 if t.id == "T004")
            self.assertEqual(adapter.issues[int(t4.issue)]["state"], "closed")
            self.assertEqual(adapter.issues[int(t4.issue)]["reason"], "not planned")
            e01 = next(e for e in pm_lib.load_epics(root) if e.id == "E01")
            self.assertEqual(adapter.issues[int(e01.meta["issue"])]["state"], "closed")
            self.assertIn("- [x] #%s T004 Tidy login log format (dismissed)" % t4.issue, adapter.issues[int(e01.meta["issue"])]["body"])

    def test_close_issue_passes_the_reason_to_gh(self):
        calls = []
        adapter = github.GithubAdapter(runner=lambda args: calls.append(args) or "")
        adapter.close_issue(7, reason="not planned")
        self.assertEqual(calls[-1], ["gh", "issue", "close", "7", "--reason", "not planned"])
