import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "pm.py"
START_HOOK = ROOT / "hooks" / "session-start.sh"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

sys.path.insert(0, str(ROOT / "scripts"))
import pm  # noqa: E402
import pm_migrate  # noqa: E402


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        self.scratch = Path(self.temp.name) / "scratch"
        self.scratch.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def repo(self, fixture):
        shutil.copytree(FIXTURES / fixture, self.root)
        for args in (("init", "-q"), ("config", "user.name", "Test"), ("config", "user.email", "t@example.com"),
                     ("add", "-A"), ("commit", "-qm", "old system")):
            subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)
        return self.root

    def cli(self, *args, cwd=None, ok=True):
        result = subprocess.run(["python3", str(CLI), *args], cwd=cwd or self.root, text=True, capture_output=True)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        return result

    def plan(self, *args):
        out = self.scratch / "plan.json"
        result = self.cli("migrate", "plan", *args, "--out", str(out))
        return json.loads(out.read_text()), result.stdout

    def snapshot(self):
        return sorted((p.relative_to(self.root).as_posix(), p.read_bytes())
                      for p in self.root.rglob("*") if p.is_file() and ".git" not in p.parts)

    def items_by_key(self, plan):
        return {item["key"]: item for item in plan["items"]}

    def board_items(self, root=None):
        return {i["title"]: i for i in pm.read_items(root or self.root)}

    # ---- detection

    def test_scan_finds_the_0x_board_and_says_what_to_run(self):
        self.repo("pm-0x")
        out = self.cli("migrate", "scan").stdout
        self.assertIn("pm-plugin 0.x board: 8 tickets, 2 epics, roadmap.md, decisions.md", out)
        self.assertIn("migrate plan --from pm-0x", out)

    def test_scan_reports_nothing_in_an_empty_repo_and_an_existing_board(self):
        self.root.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        self.assertIn("No existing project-management system found.", self.cli("migrate", "scan").stdout)
        self.cli("init")
        out = self.cli("migrate", "scan").stdout
        self.assertIn("A 1.x board already exists here: 0 items", out)
        self.assertIn("No other system found.", out)

    def test_scan_flags_other_systems_that_need_a_hand_made_plan(self):
        self.repo("checklist")
        for path in (".beads/issues.jsonl", "backlog/tasks/task-1 - Fix.md", "tasks/tasks.py", "linear-export.csv"):
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("x\n")
        found = {f["system"]: f for f in pm_migrate.scan(self.root, "git@github.com:acme/app.git")}
        self.assertEqual(found["checklist"]["importer"], "checklist")
        self.assertIn("3 open, 1 done", found["checklist"]["detail"])
        self.assertEqual(found["beads"]["importer"], "")
        self.assertIn("backlog", found)
        self.assertIn("export", found)
        self.assertIn("github-issues", found)
        self.assertNotIn("tasks", found, "a folder of code is not a task system")

    # ---- pm-plugin 0.x

    def test_0x_plan_maps_statuses_dependencies_and_issues_without_writing(self):
        self.repo("pm-0x")
        before = self.snapshot()
        plan, text = self.plan("--from", "pm-0x")
        self.assertEqual(self.snapshot(), before, "planning must not change the repository")
        items = self.items_by_key(plan)
        self.assertEqual({k: (v["status"], v["owner"]) for k, v in items.items() if k.startswith("T")}, {
            "T002": ("queued", ""), "T003": ("queued", ""), "T005": ("in-flight", "agent-a"),
            "T006": ("in-flight", "agent-b"), "T007": ("queued", "agent-c"), "T008": ("queued", "")})
        self.assertEqual(items["T002"]["depends_on"], [], "a dependency on finished work is already satisfied")
        self.assertEqual(items["T003"]["depends_on"], ["T002"])
        self.assertIn("Not yet clarified", items["T003"]["hold"])
        self.assertEqual(items["T006"]["depends_on"], ["T005"])
        self.assertEqual(items["T002"]["github_issue"], "12")
        self.assertEqual(items["T003"]["github_issue"], "13")
        self.assertEqual(items["T005"]["github_issue"], "14")
        self.assertEqual({h["key"]: h["status"] for h in plan["history"]}, {"T001": "done", "T004": "dismissed"})
        self.assertEqual(plan["before"], {"total": 10, "by_status": {
            "done": 1, "todo": 3, "dismissed": 1, "in progress": 2, "review": 1, "backlog": 2}})
        self.assertEqual(len(plan["items"]) + len(plan["history"]), plan["before"]["total"])
        warnings = " ".join(plan["warnings"])
        for expected in ("unknown ticket T099", "T004, which was dismissed", "T008 is in progress with no owner"):
            self.assertIn(expected, warnings)
        self.assertEqual(plan["retire"], ["docs/pm/tickets", "docs/pm/roadmap.md", "docs/pm/epics", "docs/pm/decisions.md"])
        self.assertIn("After:  8 items on the board (5 queued, 2 in flight, 1 waiting, 0 done)", text)

    def test_0x_intent_keeps_the_original_words_and_notes_hold_the_rest(self):
        self.repo("pm-0x")
        plan, _ = self.plan("--from", "pm-0x")
        item = self.items_by_key(plan)["T002"]
        original = (FIXTURES / "pm-0x/docs/pm/tickets/T002-rate-limit.md").read_text()
        for words in ('Block an account for 15 minutes after 5 failed attempts. Keep "$HOME" and $(touch injected) literal.',
                      "## Current notes\nThis heading text belongs to the requester's words, not to the notes.",
                      "- [ ] The sixth attempt is refused."):
            self.assertIn(words, item["intent"])
            self.assertIn(words, original)
        self.assertNotIn("Check the clock source first", item["intent"])
        self.assertNotIn("approved: no", item["notes"], "an empty plan template is not carried over")
        self.assertIn("Notes (0.x):\nCheck the clock source first.", item["notes"])
        self.assertIn("ticket T002 (epic E01 Login, milestone M1, priority P1)", item["notes"])
        self.assertIn("Epic goal: People can sign in safely.", item["notes"])
        self.assertEqual(self.items_by_key(plan)["T008"]["intent"], "Written by hand, no headings and no owner.")
        self.assertIn("approved: yes", self.items_by_key(plan)["T005"]["notes"], "a filled plan is kept")
        self.assertIn("PR #34", self.items_by_key(plan)["T005"]["notes"])

    def test_0x_backlog_lines_become_queued_items(self):
        self.repo("pm-0x")
        plan, _ = self.plan("--from", "pm-0x")
        backlog = [i for i in plan["items"] if i["key"].startswith("backlog-")]
        self.assertEqual([(i["title"], i["intent"], i["status"]) for i in backlog],
                         [("Dark mode", "Dark mode", "queued"), ("Export to CSV", "Export to CSV", "queued")])

    def test_0x_non_item_knowledge_is_routed_not_dropped(self):
        self.repo("pm-0x")
        plan, text = self.plan("--from", "pm-0x")
        routed = {k["from"]: k for k in plan["knowledge"]}
        self.assertEqual(set(routed), {"docs/pm/roadmap.md", "docs/pm/epics/", "docs/pm/decisions.md", "CONTEXT.md (## pm block)"})
        self.assertIn("README.md", routed["docs/pm/roadmap.md"]["route"])
        self.assertIn("AGENTS.md", routed["docs/pm/decisions.md"]["route"])
        self.assertIn("2 decision(s)", routed["docs/pm/decisions.md"]["what"])
        self.assertIn("`make test` belongs in AGENTS.md", routed["CONTEXT.md (## pm block)"]["route"])
        self.assertIn("mirror was `on`", routed["CONTEXT.md (## pm block)"]["route"])
        self.assertIn("docs/placement.md", text)

    def test_0x_apply_creates_items_keeps_words_and_deletes_nothing(self):
        self.repo("pm-0x")
        plan, _ = self.plan("--from", "pm-0x")
        old_files = self.snapshot()
        out = self.cli("migrate", "apply", str(self.scratch / "plan.json")).stdout
        self.assertIn("Migrated 8 items from pm-0x", out)
        self.assertIn("accounted for 10", out)
        self.assertIn("Board now: 8 items (5 queued, 2 in flight, 1 waiting, 0 done)", out)
        after = {path for path, _ in self.snapshot()} - {path for path, _ in old_files}
        self.assertTrue(all(path.startswith("docs/pm/items/") or path == "docs/pm/config.json" for path in after), after)
        self.assertTrue(set(old_files) <= set(self.snapshot()), "the old system must be left untouched")
        items = self.board_items()
        rate = items["Rate-limit login attempts"]
        self.assertEqual(rate["intent"], self.items_by_key(plan)["T002"]["intent"])
        self.assertEqual(rate["github_issue"], "12")
        self.assertEqual(items["Lock account after limit"]["status"], "waiting")
        self.assertEqual(items["Lock account after limit"]["depends_on"], [rate["id"]])
        self.assertEqual((items["Session cookie flags"]["status"], items["Session cookie flags"]["owner"]), ("in-flight", "agent-a"))
        self.assertEqual(items["Revoke share"]["owner"], "agent-c")
        self.assertRegex(rate["id"], r"^rate-limit-login-attempts-[0-9a-f]{6}$")
        self.assertFalse((self.root / "injected").exists())
        board = self.cli("board").stdout
        self.assertIn("## Waiting", board)
        self.assertIn("Ready next:", board)
        self.assertNotIn(rate["id"], board.split("Ready next:")[0].split("## In flight")[1].split("## Queued")[0])

    def test_migrated_claims_and_dependencies_behave_like_native_ones(self):
        self.repo("pm-0x")
        self.plan("--from", "pm-0x")
        self.cli("migrate", "apply", str(self.scratch / "plan.json"))
        items = self.board_items()
        refused = subprocess.run(["python3", str(CLI), "claim", items["Session cookie flags"]["id"]], cwd=self.root,
                                 input="Bea", text=True, capture_output=True)
        self.assertIn("already claimed by agent-a", refused.stderr)
        waiting = subprocess.run(["python3", str(CLI), "claim", items["Lock account after limit"]["id"]], cwd=self.root,
                                 input="Bea", text=True, capture_output=True)
        self.assertNotEqual(waiting.returncode, 0)
        self.assertEqual(subprocess.run(["python3", str(CLI), "claim", items["Rate-limit login attempts"]["id"]], cwd=self.root,
                                        input="Bea", text=True, capture_output=True).returncode, 0)

    def test_applying_twice_does_not_duplicate_items(self):
        self.repo("pm-0x")
        self.plan("--from", "pm-0x")
        self.cli("migrate", "apply", str(self.scratch / "plan.json"))
        again = self.cli("migrate", "apply", str(self.scratch / "plan.json")).stdout
        self.assertIn("Migrated 0 items from pm-0x (8 already on the board", again)
        self.assertEqual(len(list((self.root / "docs/pm/items").glob("*.md"))), 8)

    def test_0x_done_items_can_be_imported_with_their_dependencies(self):
        self.repo("pm-0x")
        plan, text = self.plan("--from", "pm-0x", "--done", "items")
        items = self.items_by_key(plan)
        self.assertEqual(items["T001"]["status"], "done")
        self.assertEqual(items["T002"]["depends_on"], ["T001"])
        self.assertEqual([h["key"] for h in plan["history"]], ["T004"], "dismissed work is never imported")
        self.assertIn("1 done", text)
        self.cli("migrate", "apply", str(self.scratch / "plan.json"))
        done = self.cli("board").stdout.split("## Done")[1]
        self.assertIn("Add login attempt counter", done)

    def test_apply_publishes_to_the_shared_default_branch(self):
        origin = Path(self.temp.name) / "origin.git"
        self.repo("pm-0x")
        subprocess.run(["git", "branch", "-M", "main"], cwd=self.root, check=True)
        subprocess.run(["git", "init", "-q", "--bare", "--initial-branch=main", str(origin)], check=True)
        subprocess.run(["git", "remote", "add", "origin", str(origin)], cwd=self.root, check=True)
        subprocess.run(["git", "push", "-qu", "origin", "main"], cwd=self.root, check=True, capture_output=True)
        self.plan("--from", "pm-0x")
        out = self.cli("migrate", "apply", str(self.scratch / "plan.json")).stdout
        self.assertIn("Published to shared origin/main", out)
        listing = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", "origin/main"], cwd=self.root, text=True)
        self.assertIn("docs/pm/config.json", listing)
        self.assertEqual(len([l for l in listing.splitlines() if l.startswith("docs/pm/items/")]), 8)
        self.assertIn("docs/pm/tickets/T001-counter.md", listing, "the old system stays in the repository")
        subject = subprocess.check_output(["git", "log", "-1", "--format=%s", "origin/main"], cwd=self.root, text=True)
        self.assertEqual(subject.strip(), "pm: Migrated 8 items from pm-0x")

    # ---- markdown checklist (generic fallback)

    def test_checklist_plan_keeps_each_item_verbatim(self):
        self.repo("checklist")
        plan, text = self.plan("--from", "checklist", "--file", "TODO.md")
        self.assertEqual(plan["source"], "checklist:TODO.md")
        first, second, later = plan["items"]
        self.assertEqual(first["intent"], "Add rate limiting to the login endpoint\n  - [ ] pick a limit\n  - details: 5 per minute per IP")
        self.assertEqual(first["title"], "Add rate limiting to the login endpoint")
        self.assertEqual(first["notes"], 'Migrated from TODO.md, under "Next up".')
        self.assertNotEqual(first["key"], second["key"], "the same text twice must still get distinct keys")
        self.assertEqual(second["status"], "queued")
        self.assertEqual(later["intent"].split("\n")[0][:20], "Dark mode, but only ")
        self.assertTrue(later["title"].endswith("…") and len(later["title"]) <= 81)
        self.assertEqual([(h["title"], h["status"]) for h in plan["history"]], [("Set up CI", "done")])
        self.assertEqual(plan["before"], {"total": 4, "by_status": {"open": 3, "done": 1}})
        self.assertEqual(plan["retire"], [], "a file with other text is never offered for removal")
        self.assertIn("1 line(s) of text that are not checklist items", plan["knowledge"][0]["what"])
        self.assertIn("After:  3 items", text)

    def test_checklist_apply_and_requires_a_file_inside_the_repo(self):
        self.repo("checklist")
        self.plan("--from", "checklist", "--file", "TODO.md")
        self.cli("migrate", "apply", str(self.scratch / "plan.json"))
        self.assertEqual(len(pm.read_items(self.root)), 3)
        self.assertIn("needs --file", self.cli("migrate", "plan", "--from", "checklist", "--out", str(self.scratch / "x.json"), ok=False).stderr)
        self.assertIn("not a file inside this repository",
                      self.cli("migrate", "plan", "--from", "checklist", "--file", "../outside.md", "--out", str(self.scratch / "x.json"), ok=False).stderr)

    # ---- hand-made plans (any other system) and refusal of bad plans

    def write_plan(self, plan):
        path = self.scratch / "hand.json"
        path.write_text(json.dumps(plan))
        return str(path)

    def hand_plan(self):
        return {"source": "beads", "before": {"total": 3, "by_status": {"open": 2, "closed": 1}}, "items": [
            {"key": "bd-1", "title": "Fix login", "intent": "login is broken\non mobile", "status": "queued"},
            {"key": "bd-2", "title": "Fix signup", "intent": "signup too", "status": "in-flight", "owner": "Ari",
             "depends_on": ["bd-1"], "github_issue": "7", "hold": "Which provider?", "hold_until": "2026-12-01"}],
            "history": [{"key": "bd-0", "title": "old", "status": "closed", "why": "closed"}]}

    def test_hand_made_plan_is_applied_like_any_other(self):
        self.root.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        path = self.write_plan(self.hand_plan())
        dry = self.cli("migrate", "apply", path, "--dry-run").stdout
        self.assertIn("Dry run: 2 items would be created from beads", dry)
        self.assertFalse((self.root / "docs").exists())
        out = self.cli("migrate", "apply", path).stdout
        self.assertIn("Board now: 2 items (1 queued, 0 in flight, 1 waiting, 0 done)", out)
        items = self.board_items()
        self.assertEqual(items["Fix login"]["intent"], "login is broken\non mobile")
        signup = items["Fix signup"]
        self.assertEqual((signup["status"], signup["owner"], signup["hold_until"], signup["github_issue"]),
                         ("waiting", "Ari", "2026-12-01", "7"))
        self.assertEqual(signup["depends_on"], [items["Fix login"]["id"]])

    def test_bad_plans_are_refused_and_write_nothing(self):
        self.root.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        cases = {
            "unknown status": (lambda p: p["items"][0].update(status="blocked"), "status must be one of"),
            "missing intent": (lambda p: p["items"][0].update(intent=" "), "intent must be a non-empty string"),
            "in flight without owner": (lambda p: p["items"][1].update(owner=""), "needs an owner"),
            "unknown dependency": (lambda p: p["items"][1].update(depends_on=["nope"]), "not an item in the plan"),
            "cycle": (lambda p: p["items"][0].update(depends_on=["bd-2"]), "Dependencies form a cycle: bd-1 -> bd-2 -> bd-1"),
            "duplicate key": (lambda p: p["items"][1].update(key="bd-1"), "key is used more than once"),
            "issue url": (lambda p: p["items"][1].update(github_issue="https://x/issues/7"), "digits only"),
            "no source": (lambda p: p.pop("source"), "source must be"),
        }
        for name, (mutate, message) in cases.items():
            plan = self.hand_plan()
            mutate(plan)
            result = self.cli("migrate", "apply", self.write_plan(plan), ok=False)
            self.assertIn(message, result.stderr, name)
            self.assertFalse((self.root / "docs").exists(), name)
        self.assertIn("Cannot read plan", self.cli("migrate", "apply", str(self.scratch / "missing.json"), ok=False).stderr)

    # ---- session start nudges an old board toward migration

    def test_session_start_points_a_0x_board_at_init(self):
        self.repo("pm-0x")
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)}
        out = subprocess.run(["bash", str(START_HOOK)], cwd=self.root, env=env, input="{}", text=True,
                             capture_output=True, check=True).stdout
        self.assertIn("pm 0.x board", out)
        self.assertIn("/pm:init", out)
        self.cli("init")
        out = subprocess.run(["bash", str(START_HOOK)], cwd=self.root, env=env, input="{}", text=True,
                             capture_output=True, check=True).stdout
        self.assertNotIn("0.x", out)


if __name__ == "__main__":
    unittest.main()
