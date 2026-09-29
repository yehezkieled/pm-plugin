import subprocess
import tempfile
import unittest
from pathlib import Path
import os
import shlex
import json


CLI = Path(__file__).resolve().parents[1] / "scripts" / "pm.py"
STOP_HOOK = Path(__file__).resolve().parents[1] / "hooks" / "stop.sh"


class ProjectBoardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.root, check=True)
        self.run_cli("init")

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, *args, ok=True, input_text=None):
        result = subprocess.run(["python3", str(CLI), *args], cwd=self.root, text=True, input=input_text, capture_output=True)
        self.assertEqual(result.returncode == 0, ok, result.stderr)
        return result

    def run_literal_cli(self, *args, input_text):
        command = " ".join(shlex.quote(str(arg)) for arg in ("python3", CLI, *args))
        script = f"{command} <<'PM_LITERAL'\n{input_text}\nPM_LITERAL\n"
        result = subprocess.run(["bash", "-c", script], cwd=self.root, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
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

    def test_user_derived_fields_pass_through_literal_heredocs(self):
        title = 'x"; touch injected-title; $(touch injected-substitution); #'
        intent = 'Preserve $HOME, "quotes", and $(touch injected-intent).'
        created = self.run_literal_cli("add", "--request-stdin", input_text=f"{title}\n{intent}")
        item_id = created.stdout.split(":", 1)[0].split()[-1]
        detail_path = next((self.root / "docs/pm/items").glob(f"{item_id}-*.md"))
        detail = detail_path.read_text()
        self.assertIn(f"# {title}", detail)
        self.assertIn(intent, detail)

        person = 'Ari"; touch injected-person; $(touch injected-person-sub); #'
        self.run_literal_cli("claim", item_id, "--person-stdin", input_text=person)
        metadata = detail_path.read_text().split("---\n", 2)[1]
        owner = next(line.partition(": ")[2] for line in metadata.splitlines() if line.startswith("owner:"))
        self.assertEqual(json.loads(owner), person)
        reason = 'Need approval for "$HOME" and $(touch injected-reason).'
        self.run_literal_cli("hold", item_id, "--reason-stdin", input_text=reason)
        metadata = detail_path.read_text().split("---\n", 2)[1]
        hold = next(line.partition(": ")[2] for line in metadata.splitlines() if line.startswith("hold:"))
        self.assertEqual(json.loads(hold), reason)
        self.run_cli("resume", item_id)
        self.run_literal_cli("claim", item_id, "--person-stdin", input_text="Ari")
        note = 'Finished with "$HOME" and $(touch injected-note).'
        self.run_literal_cli("finish", item_id, "--note-stdin", input_text=note)
        self.assertIn(f"{note}", detail_path.read_text())
        for sentinel in ("injected-title", "injected-substitution", "injected-intent", "injected-person",
                         "injected-person-sub", "injected-reason", "injected-note"):
            self.assertFalse((self.root / sentinel).exists(), sentinel)

    def test_item_ids_use_title_slugs_with_distinct_random_suffixes(self):
        first = self.add("Shared task", "First request")
        second = self.add("Shared task", "Second request")
        self.assertRegex(first, r"^shared-task-[0-9a-f]{6}$")
        self.assertRegex(second, r"^shared-task-[0-9a-f]{6}$")
        self.assertNotEqual(first, second)
        self.assertEqual(len(list((self.root / "docs/pm/items").glob("*.md"))), 2)

        with tempfile.TemporaryDirectory() as temp:
            other = Path(temp)
            subprocess.run(["git", "init", "-q"], cwd=other, check=True)
            subprocess.run(["python3", str(CLI), "init"], cwd=other, check=True, capture_output=True, text=True)
            result = subprocess.run(["python3", str(CLI), "add", "Shared task", "--intent-stdin"], cwd=other,
                                    input="Another request", check=True, capture_output=True, text=True)
            other_id = result.stdout.split(":", 1)[0].split()[-1]
            self.assertRegex(other_id, r"^shared-task-[0-9a-f]{6}$")
            self.assertNotEqual(first, other_id)

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
        self.run_cli("set", second, "--depends", first.upper())
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
        code = self.root / "app.py"
        code.write_text("original\n")
        subprocess.run(["git", "add", "app.py"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "add app"], cwd=self.root, check=True)
        ids = []
        for number in range(11):
            item_id = self.add(f"Task {number}", f"Request {number}")
            ids.append(item_id)
            self.run_cli("claim", item_id, "Ari")
            code.write_text(f"changed {number}\n")
            subprocess.run(["git", "add", "app.py"], cwd=self.root, check=True)
            self.run_cli("finish", item_id)
        board = (self.root / "docs/pm/BOARD.md").read_text()
        archive = (self.root / "docs/pm/archive.md").read_text()
        self.assertNotIn(f"[{ids[0]}]", board)
        self.assertIn(f"[{ids[0]}]", archive)
        self.assertIn(f"[{ids[-1]}]", board)
        self.run_cli("set", ids[0], "--note", "Updated archived item")
        archive = (self.root / "docs/pm/archive.md").read_text()
        self.assertEqual(archive.count(f"[{ids[0]}]"), 1)
        self.assertEqual(subprocess.check_output(["git", "log", "-1", "--format=%s"], cwd=self.root, text=True).strip(),
                         f"pm: finish {ids[-1]}")
        committed = subprocess.check_output(["git", "show", "HEAD:docs/pm/items/" +
                                               next((self.root / "docs/pm/items").glob(f"{ids[-1]}-*.md")).name],
                                            cwd=self.root, text=True)
        self.assertIn('status: "done"', committed)
        self.assertIn("app.py", subprocess.check_output(["git", "diff", "--cached", "--name-only"],
                                                        cwd=self.root, text=True))

    def test_stop_hook_recognizes_slug_id_item_updates(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            (root / "docs/pm/items").mkdir(parents=True)
            (root / "docs/pm/BOARD.md").write_text("# Board\n")
            detail = root / "docs/pm/items/shared-task-a1b2c3-shared-task.md"
            detail.write_text("item details\n")
            code = root / "app.py"
            code.write_text("original\n")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.com",
                            "commit", "-qm", "baseline"], cwd=root, check=True)
            code.write_text("changed\n")
            detail.write_text("updated notes\n")
            env = os.environ.copy()
            env["CLAUDE_PROJECT_DIR"] = str(root)
            result = subprocess.run(["bash", str(STOP_HOOK)], cwd=root, env=env, input="{}", text=True,
                                    capture_output=True, check=True)
            self.assertNotIn("Code changed without an item detail update", result.stdout)

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
            added = subprocess.run(["python3", str(CLI), "add", "Shared task", "--intent-stdin"], cwd=seed,
                                   input="Build the shared task", check=True, capture_output=True, text=True)
            item_id = added.stdout.split(":", 1)[0].split()[-1]
            subprocess.run(["git", "add", "docs/pm"], cwd=seed, check=True)
            subprocess.run(["git", "commit", "-qm", "seed board"], cwd=seed, check=True)
            subprocess.run(["git", "init", "-q", "--bare", "--initial-branch=main", str(origin)], check=True)
            subprocess.run(["git", "remote", "add", "origin", str(origin)], cwd=seed, check=True)
            subprocess.run(["git", "push", "-qu", "origin", "main"], cwd=seed, check=True)
            clone_a, clone_b = space / "clone-a", space / "clone-b"
            subprocess.run(["git", "clone", "-q", str(origin), str(clone_a)], check=True)
            subprocess.run(["git", "clone", "-q", str(origin), str(clone_b)], check=True)

            claimed = subprocess.run(["python3", str(CLI), "claim", item_id, "Ari"], cwd=clone_a,
                                     text=True, capture_output=True)
            self.assertEqual(claimed.returncode, 0, claimed.stderr)
            self.assertIn("shared origin/main", claimed.stdout)
            refused = subprocess.run(["python3", str(CLI), "claim", item_id, "Bea"], cwd=clone_b,
                                     text=True, capture_output=True)
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("already claimed by Ari on origin/main", refused.stderr)
            item_path = next((clone_b / "docs/pm/items").glob(f"{item_id}-*.md"))
            owner = subprocess.check_output(["git", "-C", str(clone_b), "show", f"HEAD:{item_path.relative_to(clone_b)}"], text=True)
            self.assertIn('owner: "Ari"', owner)


if __name__ == "__main__":
    unittest.main()
