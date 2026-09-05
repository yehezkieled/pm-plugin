"""The eval runners ship with the plugin and find it by their own location."""
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"evals/{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_harness():
    return load_module("harness")


class EvalRunnersTest(unittest.TestCase):
    def test_harness_points_at_this_plugin_and_lists_the_scenarios(self):
        h = load_harness()
        self.assertEqual(h.PLUGIN, ROOT)
        self.assertGreaterEqual(len(h.SCENARIOS), 23)
        for name, spec in h.SCENARIOS.items():
            for key in ("prompt", "setup", "max_turns"):
                self.assertIn(key, spec, f"{name} lacks {key}")
        self.assertIn("work_bug_implicit", h.SCENARIOS)

    def test_bug_scenario_repo_is_valid_and_next_picks_the_bug(self):
        h = load_harness()
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            h.calc_repo(repo, True, "bug")
            self.assertTrue(h.validate_ok(repo))
            self.assertTrue(h.pm(repo, "next").stdout.startswith("T004 "))
            self.assertIn("Bug: average crashes on an empty list", (repo / "docs/pm/tickets/T004-average-empty.md").read_text())

    def test_livepr_refuses_to_run_without_a_throwaway_repo(self):
        env = {k: v for k, v in os.environ.items() if k != "PM_EVAL_REPO"}
        proc = subprocess.run([sys.executable, str(ROOT / "evals/livepr.py"), "setup"], capture_output=True, text=True, env=env)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("PM_EVAL_REPO", proc.stdout + proc.stderr)

    def test_matrix_runs_on_an_empty_results_folder(self):
        proc = subprocess.run([sys.executable, str(ROOT / "evals/matrix.py")], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("cells passing:", proc.stdout)


class InteractiveReviewModelTest(unittest.TestCase):
    """The interactive runner answers Opus to the review-model question and checks the agents got that model."""
    QUESTION = "Which model runs the review agents at the review gate?"

    def test_runner_picks_opus_for_the_review_model_question(self):
        it = load_module("interactive")
        idx = it.choose_option(self.QUESTION, ["Sonnet (Recommended)", "Opus"], it.ASK_POLICY)
        self.assertEqual(idx, 1)

    def test_work_checks_cover_the_question_and_the_chosen_model(self):
        it = load_module("interactive")
        ask = ("AskUserQuestion", {"questions": [{"question": self.QUESTION}]})
        answered = [{"kind": "ask_answered", "detail": f"{self.QUESTION} -> Opus"}]

        def agents(model):
            return [("Agent", {"subagent_type": "pm:verifier", "model": model}),
                    ("Agent", {"subagent_type": "pm:reviewer", "model": model})]

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            it.h.calc_repo(repo, True)
            good = it.evaluate("work_merge_ask", repo, [ask, *agents("opus")], [], answered)
            self.assertTrue(good["asked_review_model"])
            self.assertTrue(good["review_agents_ran"])
            self.assertTrue(good["review_agents_used_chosen_model"])
            wrong_model = it.evaluate("work_merge_ask", repo, [ask, *agents("sonnet")], [], answered)
            self.assertFalse(wrong_model["review_agents_used_chosen_model"])
            never_asked = it.evaluate("work_merge_ask", repo, agents("opus"), [], [])
            self.assertFalse(never_asked["asked_review_model"])
            self.assertFalse(never_asked["review_agents_used_chosen_model"])
            no_agents = it.evaluate("work_plan_mode", repo, [ask], [], answered)
            self.assertFalse(no_agents["review_agents_ran"])
            self.assertFalse(no_agents["review_agents_used_chosen_model"])


class InteractiveRunnerTest(unittest.TestCase):
    def test_runner_picks_go_for_the_go_ahead_question(self):
        it = load_module("interactive")
        idx = it.choose_option("Here is the plan for T002. Go ahead?", ["Change the plan", "Go (Recommended)", "Stop"], it.ASK_POLICY)
        self.assertEqual(idx, 1)

    def test_work_checks_cover_the_go_ahead_question(self):
        it = load_module("interactive")
        go = ("AskUserQuestion", {"questions": [{"question": "Plan shown above. Go ahead with T002?", "options": [{"label": "Go (Recommended)"}, {"label": "Change"}, {"label": "Stop"}]}]})
        other = ("AskUserQuestion", {"questions": [{"question": "Merge branch t002-subtract into main now?", "options": [{"label": "Merge now"}, {"label": "Leave for later"}]}]})
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            it.h.calc_repo(repo, True)
            self.assertTrue(it.evaluate("work_merge_ask", repo, [go, other], [], [])["asked_go_ahead"])
            self.assertFalse(it.evaluate("work_merge_ask", repo, [other], [], [])["asked_go_ahead"])
            self.assertNotIn("asked_go_ahead", it.evaluate("work_plan_mode", repo, [other], [], []))

    def test_prompt_row_is_free_when_empty_or_holding_a_suggestion(self):
        it = load_module("interactive")
        typed = "Pick up the next ticket in our project tracking and do it."
        self.assertTrue(it.prompt_row_free(["● done.", "❯"], typed))
        self.assertTrue(it.prompt_row_free(["● done.", "❯ do the next ticket"], typed))
        self.assertFalse(it.prompt_row_free(["● done.", f"❯ {typed}"], typed))
        self.assertFalse(it.prompt_row_free(["● done.", "  Thinking…"], typed))


class SilentTestEditCheckTest(unittest.TestCase):
    """Only real test sources count as an edit after a freeze; compiled caches swept in by `git add -A` do not."""

    def test_cache_files_are_not_test_edits(self):
        h = load_harness()
        self.assertEqual(h.test_source_edits("tests/__pycache__/test_calc.cpython-312.pyc"), [])
        self.assertEqual(h.test_source_edits("tests/__pycache__/x.pyc\ntests/.pytest_cache/v/cache/nodeids"), [])
        self.assertEqual(h.test_source_edits(""), [])

    def test_real_test_sources_are_edits(self):
        h = load_harness()
        self.assertEqual(h.test_source_edits("tests/test_calc.py"), ["tests/test_calc.py"])
        self.assertEqual(h.test_source_edits("tests/__pycache__/x.pyc\ntests/test_calc.py\ntests/conftest.py"),
                         ["tests/test_calc.py", "tests/conftest.py"])


if __name__ == "__main__":
    unittest.main()
