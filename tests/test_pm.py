import subprocess
import tempfile
import unittest
from pathlib import Path


CLI = Path(__file__).resolve().parents[1] / "scripts" / "pm.py"


class ProjectBoardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        self.run_cli("init")

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, *args, ok=True, input_text=None):
        result = subprocess.run(["python3", str(CLI), *args], cwd=self.root, text=True, input=input_text, capture_output=True)
        self.assertEqual(result.returncode == 0, ok, result.stderr)
        return result

    def add(self, title, intent):
        return self.run_cli("add", title, "--intent-stdin", input_text=intent).stdout.split(":", 1)[0].split()[-1]

    def test_keeps_requester_words_and_board_points_to_detail(self):
        exact = '$HOME $(touch should-not-exist)\n## Current notes\nThis heading remains part of requester intent.'
        item_id = self.add("Shared view", exact)
        detail = next((self.root / "docs/pm/items").glob(f"{item_id}-*.md")).read_text()
        board = (self.root / "docs/pm/BOARD.md").read_text()
        self.assertIn(exact, detail)
        self.assertIn(f"[{item_id}](items/", board)
        self.assertIn("## Queued", board)
        self.assertIn("This heading remains part of requester intent", board)

    def test_claim_is_exclusive_and_happens_before_in_flight(self):
        item_id = self.add("One task", "Do one task")
        self.run_cli("claim", item_id, "Ari")
        refused = self.run_cli("claim", item_id, "Bea", ok=False)
        self.assertIn("already claimed by Ari", refused.stderr)
        board = (self.root / "docs/pm/BOARD.md").read_text()
        self.assertIn("## In flight", board)
        self.assertIn("claimed by Ari", board)

    def test_next_skips_incomplete_dependencies_and_holds(self):
        first = self.add("First", "Build first")
        second = self.add("Second", "Build second")
        self.run_cli("set", second, "--depends", first)
        ready = self.run_cli("next").stdout
        self.assertIn(first, ready)
        self.assertNotIn(second, ready)
        self.run_cli("claim", first, "Ari")
        self.run_cli("finish", first)
        self.assertEqual(self.run_cli("next").stdout.strip().split()[0], second)
        self.run_cli("hold", second, "Need a decision", "--until", "2026-10-10")
        self.assertIn("no queued items are ready", self.run_cli("next").stdout.lower())
        self.assertIn("Need a decision", (self.root / "docs/pm/BOARD.md").read_text())

    def test_same_owner_can_resume_but_another_owner_cannot_take_over(self):
        item_id = self.add("Resume task", "Keep the claim")
        self.run_cli("claim", item_id, "Ari")
        resumed = self.run_cli("claim", item_id, "ari")
        self.assertIn("resuming the existing claim", resumed.stdout)
        refused = self.run_cli("claim", item_id, "Bea", ok=False)
        self.assertIn("already claimed by Ari", refused.stderr)

    def test_done_board_is_capped_and_older_summaries_are_archived(self):
        ids = []
        for number in range(11):
            item_id = self.add(f"Task {number}", f"Request {number}")
            ids.append(item_id)
            self.run_cli("claim", item_id, "Ari")
            self.run_cli("finish", item_id)
        board = (self.root / "docs/pm/BOARD.md").read_text()
        archive = (self.root / "docs/pm/archive.md").read_text()
        self.assertNotIn(f"[{ids[0]}]", board)
        self.assertIn(f"[{ids[0]}]", archive)
        self.assertIn(f"[{ids[-1]}]", board)

    def test_github_mirror_defaults_off(self):
        self.assertIn("off", self.run_cli("mirror", "show").stdout)
        self.run_cli("sync", ok=False)
        enabled = self.run_cli("mirror", "github")
        self.assertIn("publishes item requester intent and current notes", enabled.stdout)
        self.assertIn("<!-- pm-mirror: github -->", (self.root / "docs/pm/BOARD.md").read_text())

    def test_remote_default_branch_serializes_claims_across_clones(self):
        with tempfile.TemporaryDirectory() as temp:
            space = Path(temp)
            origin = space / "origin.git"
            seed = space / "seed"
            seed.mkdir()
            subprocess.run(["git", "init", "-q", "--initial-branch=main"], cwd=seed, check=True)
            subprocess.run(["git", "config", "user.name", "Fixture"], cwd=seed, check=True)
            subprocess.run(["git", "config", "user.email", "fixture@example.com"], cwd=seed, check=True)
            subprocess.run(["python3", str(CLI), "init"], cwd=seed, check=True, capture_output=True, text=True)
            subprocess.run(["python3", str(CLI), "add", "Shared task", "--intent-stdin"], cwd=seed,
                           input="Build the shared task", check=True, capture_output=True, text=True)
            subprocess.run(["git", "add", "docs/pm"], cwd=seed, check=True)
            subprocess.run(["git", "commit", "-qm", "seed board"], cwd=seed, check=True)
            subprocess.run(["git", "init", "-q", "--bare", "--initial-branch=main", str(origin)], check=True)
            subprocess.run(["git", "remote", "add", "origin", str(origin)], cwd=seed, check=True)
            subprocess.run(["git", "push", "-qu", "origin", "main"], cwd=seed, check=True)
            clone_a, clone_b = space / "clone-a", space / "clone-b"
            subprocess.run(["git", "clone", "-q", str(origin), str(clone_a)], check=True)
            subprocess.run(["git", "clone", "-q", str(origin), str(clone_b)], check=True)

            claimed = subprocess.run(["python3", str(CLI), "claim", "PM-001", "Ari"], cwd=clone_a,
                                     text=True, capture_output=True)
            self.assertEqual(claimed.returncode, 0, claimed.stderr)
            self.assertIn("shared origin/main", claimed.stdout)
            refused = subprocess.run(["python3", str(CLI), "claim", "PM-001", "Bea"], cwd=clone_b,
                                     text=True, capture_output=True)
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("already claimed by Ari on origin/main", refused.stderr)
            owner = subprocess.check_output(["git", "-C", str(clone_b), "show", "HEAD:docs/pm/items/PM-001-shared-task.md"], text=True)
            self.assertIn('owner: "Ari"', owner)


if __name__ == "__main__":
    unittest.main()
