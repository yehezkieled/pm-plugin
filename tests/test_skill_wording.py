"""Guards for rules that live in skill text, agent files and templates, so a rewrite cannot drop them quietly."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel):
    return (ROOT / rel).read_text()


def frontmatter(text):
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    assert m, "no frontmatter"
    return dict(line.split(":", 1) for line in m.group(1).splitlines() if ":" in line)


class ReviewAgentsTest(unittest.TestCase):
    def test_verifier_and_reviewer_ship_read_only_on_sonnet(self):
        for name in ("verifier", "reviewer"):
            fm = frontmatter(read(f"agents/{name}.md"))
            self.assertEqual(fm["name"].strip(), name)
            self.assertTrue(fm["description"].strip())
            self.assertEqual(fm["model"].strip(), "sonnet")
            for tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
                self.assertIn(tool, fm["disallowedTools"], f"{name} must not have {tool}")

    def test_work_skill_runs_both_agents_at_the_review_gate(self):
        work = read("skills/work/SKILL.md")
        for needle in ("pm:verifier", "pm:reviewer", "review_model", "Agent tool"):
            self.assertIn(needle, work)
        self.assertIn("which model runs the review agents", work)  # asked once per ticket in an interactive session
        self.assertIn("review_model", read("templates/context-pm-block.md"))
        self.assertIn("review_model", read("skills/help/SKILL.md"))


class RoutingWordingTest(unittest.TestCase):
    """'Fix the bug ticket' must route to pm:work, both from the skill picker and from a status hand-off."""

    def test_work_description_claims_fixing_a_bug_ticket(self):
        desc = frontmatter(read("skills/work/SKILL.md"))["description"].lower()
        self.assertIn("fix", desc)
        self.assertIn("bug ticket", desc)

    def test_status_hands_off_fix_requests_to_work(self):
        handoff = read("skills/status/SKILL.md").split("## Hand-off")[1]
        self.assertRegex(handoff, r"do, pick up, or fix a ticket.*`pm:work`")


class InteractiveQuestionsWordingTest(unittest.TestCase):
    """A plan: none ticket still gets the interactive questions; no line may tell the model to skip them."""

    def test_plan_none_case_does_not_say_continue_straight_away(self):
        work = read("skills/work/SKILL.md")
        self.assertNotIn("continue straight away", work)
        self.assertRegex(work, r"\*\*Every other case\*\*.*through the questions below first")

    def test_interactive_paragraph_names_plan_none(self):
        para = [l for l in read("skills/work/SKILL.md").splitlines() if l.startswith("**Interactive session, any ticket that did not go through plan mode**")]
        self.assertEqual(len(para), 1)
        self.assertIn("includes `plan: none` tickets", para[0])
        self.assertIn("(go / change / stop)", para[0])


class TestFreezeWordingTest(unittest.TestCase):
    def test_work_skill_freezes_tests_on_bug_tickets_and_routes_wrong_tests(self):
        work = read("skills/work/SKILL.md")
        for needle in ("pm.py freeze", "pm.py unfreeze", "--reason", "same ticket", "new ticket", "never lift"):
            self.assertIn(needle, work)


class PlanDriftWordingTest(unittest.TestCase):
    def test_docs_gate_updates_the_plan_when_the_build_departed(self):
        self.assertIn("departed from the `## Plan`", read("skills/work/SKILL.md"))


class RetroWordingTest(unittest.TestCase):
    def test_retro_proposes_claude_md_lines_and_skips_dismissed(self):
        retro = read("skills/retro/SKILL.md")
        self.assertIn("CLAUDE.md", retro)
        self.assertIn("dismissed", retro)


class AuditWordingTest(unittest.TestCase):
    def test_audit_files_with_confidence_and_dismisses_with_a_reason(self):
        audit = read("skills/audit/SKILL.md")
        self.assertIn("--confidence", audit)
        self.assertIn("pm.py dismiss", audit)


class RoutineRecipeTest(unittest.TestCase):
    def test_cron_and_ci_recipes_ship_as_templates(self):
        cron = read("templates/routine-cron.txt")
        ci = read("templates/routine-github-actions.yml")
        for text in (cron, ci):
            self.assertIn("/pm:audit --routine", text)
            self.assertIn("/pm:work --routine", text)
        self.assertIn("CLAUDE_CODE_OAUTH_TOKEN", ci)
        self.assertIn("routine-cron.txt", read("README.md"))
        self.assertIn("routine-github-actions.yml", read("README.md"))
        self.assertIn("routine-cron.txt", read("skills/help/SKILL.md"))


class HelpSheetTest(unittest.TestCase):
    def test_cheat_sheet_knows_the_new_status_and_commands(self):
        text = read("skills/help/SKILL.md")
        self.assertIn("dismissed", text)
        self.assertIn("freeze", text)
        readme = read("README.md")
        self.assertIn("freeze | unfreeze | dismiss", readme)
        self.assertIn("agents/", readme)


if __name__ == "__main__":
    unittest.main()


class GrillWordingTest(unittest.TestCase):
    """The grill interview lives in its own skill; tickets are born thin and worked only once grilled."""

    def test_grill_skill_exists_and_routes_on_the_right_words(self):
        fm = frontmatter(read("skills/grill/SKILL.md"))
        self.assertEqual(fm["name"].strip(), "grill")
        desc = fm["description"].lower()
        for word in ("grill", "refine", "flesh out", "ready", "not for creating tickets"):
            self.assertIn(word, desc)
        body = read("skills/grill/SKILL.md")
        for needle in ("pm.py ready", "--early", "One question at a time", "recommended answer", "Intent versus fact", "No acceptance, no ticket", "grilled early", "Do not widen"):
            self.assertIn(needle, body)

    def test_plan_creates_thin_tickets_and_hands_them_to_grill(self):
        plan = read("skills/plan/SKILL.md")
        self.assertIn("ready: no", plan)
        self.assertIn("pm:grill", plan)
        self.assertNotIn("grill me", plan.lower())
        self.assertIn("--ready", plan)  # a bug with known reproduce steps is grilled by its shape

    def test_work_refuses_an_ungrilled_ticket_without_forcing(self):
        work = read("skills/work/SKILL.md")
        self.assertIn("not grilled", work)
        self.assertIn("pm:grill", work)
        self.assertRegex(work, r"ready: no.*never add `--force`|never add `--force`.*ready: no")

    def test_init_status_audit_and_help_know_about_grilling(self):
        self.assertIn("/pm:grill", read("skills/init/SKILL.md"))
        self.assertIn("pm:grill", read("skills/status/SKILL.md").split("## Hand-off")[1])
        self.assertIn("ready: no", read("skills/audit/SKILL.md"))
        help_text = read("skills/help/SKILL.md")
        self.assertIn("/pm:grill", help_text.split("```")[1])  # the cheat sheet block
        self.assertIn("## grill", help_text)
        self.assertIn("/pm:grill", read("README.md"))
        self.assertIn("ready: {{ready}}", read("templates/ticket.md"))
        self.assertIn("/pm:grill", read("docs/blueprint.html"))
