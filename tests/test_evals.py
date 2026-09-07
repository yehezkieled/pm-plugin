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


class GrillScenarioFixturesTest(unittest.TestCase):
    """The grill scenarios start from a thin ticket, a blocked thin ticket, and a repo where the next ticket was never grilled."""

    def test_grill_repo_has_one_thin_ticket_to_grill_and_one_blocked_behind_it(self):
        h = load_harness()
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            h.grill_repo(repo)
            self.assertTrue(h.validate_ok(repo, h.LOGIN_ALLOW))
            t8 = (repo / "docs/pm/tickets/T008-remember-me.md").read_text()
            t9 = (repo / "docs/pm/tickets/T009-remember-me-expiry.md").read_text()
            self.assertIn("ready: no", t8)
            self.assertIn("ready: no", t9)
            self.assertIn("depends_on: [T008]", t9)
            board = h.pm(repo, "board").stdout
            self.assertIn("To grill: T008", board)
            self.assertNotIn("T009", board.split("To grill:")[1].split("\n")[0])

    def test_ungrilled_calc_variant_refuses_the_claim_of_T002(self):
        h = load_harness()
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            h.calc_repo(repo, True, "ungrilled")
            self.assertTrue(h.validate_ok(repo))
            self.assertIn("to grill: T002", h.pm(repo, "next").stdout)
            self.assertIn("not grilled", h.pm(repo, "claim", "T002", "x").stderr)

    def test_grill_scenarios_are_registered_in_both_runners(self):
        h = load_harness()
        for name in ("grill_implicit", "grill_blocked", "work_not_grilled", "plan_ticket_thin"):
            self.assertIn(name, h.SCENARIOS)
        it = load_module("interactive")
        self.assertIn("grill_interview", it.SCENARIOS)


class LimitDetectionTest(unittest.TestCase):
    def test_session_limit_wording_counts_as_a_limit(self):
        h = load_harness()
        for text in ("You've hit your session limit · resets 7am (UTC)", "Usage limit reached", "resets at 3pm", "rate limit"):
            self.assertRegex(text, h.LIMIT_RE)
        self.assertNotRegex("T008 is ready to work on; the limit is one PR per ticket", h.LIMIT_RE)


class BrainstormScenarioTest(unittest.TestCase):
    """Brainstorm evals: a proposal-only run writes nothing, a delegated run writes thin items, an interactive run asks then applies."""

    def test_brainstorm_scenarios_are_registered_in_both_runners(self):
        h = load_harness()
        for name in ("brainstorm_proposal_only", "brainstorm_delegated"):
            self.assertIn(name, h.SCENARIOS)
            self.assertEqual(h.SCENARIOS[name]["expect_skill"], "pm:brainstorm")
        it = load_module("interactive")
        self.assertIn("brainstorm_session", it.SCENARIOS)
        self.assertTrue(any(k == "grill" and "later" in want for k, want in it.ASK_POLICY))
        self.assertTrue(any(k == "apply" for k, want in it.ASK_POLICY))

    def test_new_pm_items_helper_sees_only_what_a_run_added(self):
        h = load_harness()
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            h.login_repo(repo)
            self.assertEqual(h.new_pm_items(repo), {"tickets": [], "epics": [], "backlog_changed": False, "decisions_changed": False, "roadmap_changed": False})
            h.pm(repo, "new", "ticket", "--title", "Remember me", "--epic", "E01", "--what", "A box.", "--why", "Asked for.", "--acceptance", "- [ ] the box exists")
            road = repo / "docs/pm/roadmap.md"
            road.write_text(road.read_text() + "- dark mode\n")
            dec = repo / "docs/pm/decisions.md"
            dec.write_text(dec.read_text() + "\n## 2026-09-07: sessions\nContext: x\nDecision: y\nConsequences: z\n")
            items = h.new_pm_items(repo)
            self.assertEqual([t[:4] for t in items["tickets"]], ["T008"])
            self.assertTrue(items["backlog_changed"])
            self.assertTrue(items["decisions_changed"])
