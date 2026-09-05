import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pm_lib  # noqa: E402
from fixtures import make_repo  # noqa: E402


class FrontmatterTest(unittest.TestCase):
    def test_parses_scalars_lists_and_body(self):
        text = "---\nid: T001\ntitle: Hello world\ndepends_on: [T000, T009]\nowner:\n---\n## What\nbody\n"
        meta, body = pm_lib.parse_frontmatter(text)
        self.assertEqual(meta["id"], "T001")
        self.assertEqual(meta["title"], "Hello world")
        self.assertEqual(meta["depends_on"], ["T000", "T009"])
        self.assertEqual(meta["owner"], "")
        self.assertEqual(body, "## What\nbody\n")

    def test_no_frontmatter_gives_empty_meta(self):
        meta, body = pm_lib.parse_frontmatter("just text\n")
        self.assertEqual(meta, {})
        self.assertEqual(body, "just text\n")

    def test_dump_round_trips(self):
        meta = {"id": "T001", "depends_on": ["T000"], "owner": "", "issue": "31"}
        text = pm_lib.dump_frontmatter(meta, "## What\n")
        self.assertEqual(text, "---\nid: T001\ndepends_on: [T000]\nowner:\nissue: 31\n---\n## What\n")
        meta2, body2 = pm_lib.parse_frontmatter(text)
        self.assertEqual(meta2, meta)
        self.assertEqual(body2, "## What\n")


class LoadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_repo(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_loads_tickets_sorted_by_id(self):
        tickets = pm_lib.load_tickets(self.root)
        self.assertEqual([t.id for t in tickets], ["T001", "T002", "T003", "T004", "T005", "T006", "T007"])
        t2 = tickets[1]
        self.assertEqual(t2.depends_on, ["T001"])
        self.assertEqual(t2.status, "todo")
        self.assertEqual(t2.priority, "P1")
        self.assertFalse(t2.auto)
        self.assertEqual(tickets[3].auto, True)
        self.assertEqual(tickets[4].owner, "agent-a")

    def test_loads_epics_and_milestones(self):
        epics = pm_lib.load_epics(self.root)
        self.assertEqual([e.id for e in epics], ["E01", "E02"])
        self.assertEqual(epics[0].milestone, "M1")
        ms = pm_lib.load_milestones(self.root)
        self.assertEqual([(m.id, m.title) for m in ms], [("M1", "First usable version"), ("M2", "Sharing")])

    def test_reads_pm_block_from_context(self):
        cfg = pm_lib.read_config(self.root)
        self.assertEqual(cfg["flow"], "branch-pr")
        self.assertEqual(cfg["check"], "make test")
        self.assertEqual(cfg["auto_cap"], "2")
        self.assertEqual(pm_lib.config_list(cfg, "gates"), ["tdd", "checks", "review", "docs"])
        self.assertNotIn("Not pm.", cfg.values())

    def test_missing_config_gives_defaults(self):
        (self.root / "CONTEXT.md").unlink()
        cfg = pm_lib.read_config(self.root)
        self.assertEqual(cfg["flow"], "branch-local")
        self.assertEqual(cfg["merge"], "ask")
        self.assertEqual(cfg["auto_cap"], "1")


class PickerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_repo(Path(self.tmp.name))
        self.tickets = pm_lib.load_tickets(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_ready_means_todo_deps_done_no_owner(self):
        ready = [t.id for t in pm_lib.ready_tickets(self.tickets)]
        self.assertEqual(ready, ["T002", "T004", "T006"])

    def test_pick_next_prefers_priority_then_milestone_order(self):
        # T003 is P0 but blocked; T002 and T006 are both P1; T002 is in the earlier milestone.
        picked = pm_lib.pick_next(self.tickets, self.root)
        self.assertEqual(picked.id, "T002")

    def test_routine_pick_needs_auto_yes_and_plan_ok(self):
        # T002 is auto: no; T006 is plan: required without approval; T004 remains.
        picked = pm_lib.pick_next(self.tickets, self.root, routine=True)
        self.assertEqual(picked.id, "T004")

    def test_routine_accepts_required_plan_once_approved(self):
        path = self.root / "docs/pm/tickets/T006-share-link.md"
        path.write_text(path.read_text().replace("## Plan\n", "## Plan\napproved: yes\n"))
        tickets = pm_lib.load_tickets(self.root)
        t6 = next(t for t in tickets if t.id == "T006")
        self.assertTrue(t6.plan_approved)
        for t in tickets:
            if t.id == "T004":
                t.auto = False
        picked = pm_lib.pick_next(tickets, self.root, routine=True)
        self.assertEqual(picked.id, "T006")

    def test_pick_next_returns_none_when_nothing_ready(self):
        for t in self.tickets:
            t.status = "done"
        self.assertIsNone(pm_lib.pick_next(self.tickets, self.root))


class GrillReadyTest(unittest.TestCase):
    """`ready: yes` marks a grilled ticket: What, Why and a testable Acceptance line are settled."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_repo(Path(self.tmp.name))
        self.t4 = self.root / "docs/pm/tickets/T004-log-format.md"
        self.t4.write_text(self.t4.read_text().replace("ready: yes", "ready: no"))

    def tearDown(self):
        self.tmp.cleanup()

    def by_id(self):
        return {t.id: t for t in pm_lib.load_tickets(self.root)}

    def test_ready_is_parsed_and_a_missing_key_counts_as_ready(self):
        tickets = self.by_id()
        self.assertFalse(tickets["T004"].ready)
        self.assertTrue(tickets["T002"].ready)
        legacy = self.root / "docs/pm/tickets/T002-rate-limit.md"
        legacy.write_text(legacy.read_text().replace("ready: yes\n", ""))
        self.assertTrue(self.by_id()["T002"].ready, "tickets written before the ready flag existed count as grilled")

    def test_ungrilled_tickets_are_not_ready_but_listed_to_grill(self):
        tickets = pm_lib.load_tickets(self.root)
        self.assertEqual([t.id for t in pm_lib.ready_tickets(tickets)], ["T002", "T006"])
        self.assertEqual([t.id for t in pm_lib.to_grill(tickets)], ["T004"])

    def test_blocked_ungrilled_ticket_waits_for_its_dependency_first(self):
        t3 = self.root / "docs/pm/tickets/T003-lockout.md"
        t3.write_text(t3.read_text().replace("ready: yes", "ready: no"))
        self.assertEqual([t.id for t in pm_lib.to_grill(pm_lib.load_tickets(self.root))], ["T004"])

    def test_flow_and_board_and_line_show_what_to_grill(self):
        tickets = pm_lib.load_tickets(self.root)
        flow = pm_lib.render_flow([t for t in tickets if t.epic == "E01"])
        self.assertIn("Ready now: T002", flow)
        self.assertNotIn("T004", flow.split("Ready now:")[1].split("\n")[0])
        self.assertIn("To grill: T004", flow)
        board = pm_lib.render_board(self.root)
        self.assertIn("To grill: T004", board)
        self.assertRegex(board, r"T004 todo P2 Tidy login log format.*not grilled")
        self.assertIn("to grill: T004", pm_lib.board_line(self.root))

    def test_grilled_ticket_that_is_blocked_is_flagged_on_the_board(self):
        board = pm_lib.render_board(self.root)
        self.assertRegex(board, r"T003 todo P0 Lock account after limit.*blocked by T002.*grilled early")
        self.assertNotRegex(board, r"T002 todo P1 Rate-limit login attempts.*grilled early")

    def test_ready_must_be_yes_or_no(self):
        with self.assertRaises(ValueError):
            pm_lib.set_fields(self.root, "T004", ready="maybe")
        self.t4.write_text(self.t4.read_text().replace("ready: no", "ready: maybe"))
        self.assertTrue(any("T004: ready must be yes or no" in p for p in pm_lib.validate(self.root)))


if __name__ == "__main__":
    unittest.main()


class FlowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_repo(Path(self.tmp.name))
        self.tickets = pm_lib.load_tickets(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_flow_order_is_topological_with_id_ties(self):
        e01 = [t for t in self.tickets if t.epic == "E01"]
        self.assertEqual([t.id for t in pm_lib.flow_order(e01)], ["T001", "T002", "T003", "T004", "T005"])

    def test_flow_order_raises_on_cycle(self):
        a = pm_lib.Ticket(id="T900", depends_on=["T901"])
        b = pm_lib.Ticket(id="T901", depends_on=["T900"])
        with self.assertRaises(ValueError):
            pm_lib.flow_order([a, b])

    def test_render_flow_draws_chains_and_state_lines(self):
        e01 = [t for t in self.tickets if t.epic == "E01"]
        text = pm_lib.render_flow(e01)
        self.assertIn("T001 -> T002 -> T003", text)
        self.assertIn("Standalone: T004, T005", text)
        self.assertIn("Ready now: T002, T004", text)
        self.assertIn("In progress: T005 (agent-a)", text)
        self.assertIn("Blocked: T003 (waits on T002)", text)
        self.assertIn("Done: T001", text)

    def test_update_epic_rewrites_tickets_and_flow_sections_only(self):
        pm_lib.update_epic(self.root, "E01")
        text = (self.root / "docs/pm/epics/E01-login.md").read_text()
        self.assertIn("## Goal\nLogin so the milestone can ship.", text)
        self.assertIn("- T002 todo P1 Rate-limit login attempts", text)
        self.assertIn("- T005 in progress P1 Session cookie flags (agent-a, PR #34)", text)
        self.assertIn("<!-- drawn by pm flow, do not edit by hand -->", text)
        self.assertIn("T001 -> T002 -> T003", text)
        self.assertNotIn("(will be redrawn)", text)
        # running twice gives the same file
        before = text
        pm_lib.update_epic(self.root, "E01")
        self.assertEqual(before, (self.root / "docs/pm/epics/E01-login.md").read_text())


class BoardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_repo(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_board_shows_milestones_epics_tickets_and_ready(self):
        board = pm_lib.render_board(self.root)
        self.assertIn("M1: First usable version (current) 1/5 done", board)
        self.assertIn("E01 Login", board)
        self.assertIn("T005 in progress P1 Session cookie flags  owner: agent-a  PR #34", board)
        self.assertIn("T003 todo P0 Lock account after limit  blocked by T002", board)
        self.assertIn("M2: Sharing 0/2 done", board)
        self.assertIn("Ready now: T002, T004, T006", board)
        self.assertIn("Backlog: 2 items", board)
        for word in ("deadline", "due", "estimate", "days left"):
            self.assertNotIn(word, board.lower())

    def test_board_line_is_one_line(self):
        line = pm_lib.board_line(self.root)
        self.assertEqual(line.count("\n"), 0)
        self.assertIn("M1 1/5 done", line)
        self.assertIn("in progress: T005 (agent-a)", line)
        self.assertIn("ready: T002, T004, T006", line)

    def test_board_line_when_no_pm(self):
        self.assertEqual(pm_lib.board_line(Path(self.tmp.name) / "nowhere"), "")


class EditTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_repo(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_set_fields_updates_frontmatter_and_keeps_body(self):
        pm_lib.set_fields(self.root, "T002", owner="api-work", status="in progress")
        t = next(t for t in pm_lib.load_tickets(self.root) if t.id == "T002")
        self.assertEqual(t.owner, "api-work")
        self.assertEqual(t.status, "in progress")
        self.assertIn("## Acceptance\n- [ ] Something testable happens.", t.body)

    def test_set_fields_rejects_bad_status_and_unknown_ticket(self):
        with self.assertRaises(ValueError):
            pm_lib.set_fields(self.root, "T002", status="finished")
        with self.assertRaises(KeyError):
            pm_lib.set_fields(self.root, "T999", status="done")

    def test_next_id_for_each_kind(self):
        self.assertEqual(pm_lib.next_id(self.root, "ticket"), "T008")
        self.assertEqual(pm_lib.next_id(self.root, "epic"), "E03")
        self.assertEqual(pm_lib.next_id(self.root, "milestone"), "M3")

    def test_slug_and_paths(self):
        self.assertEqual(pm_lib.slug("Rate-limit login attempts!"), "rate-limit-login-attempts")
        self.assertEqual(pm_lib.ticket_path(self.root, "T008", "Rate-limit login"),
                         self.root / "docs/pm/tickets/T008-rate-limit-login.md")


class ValidateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_repo(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_fixture_reports_only_the_claimed_todo_ticket(self):
        problems = pm_lib.validate(self.root)
        self.assertEqual(problems, ["T007: owner set but status is todo"])

    def test_reports_bad_references_and_missing_acceptance(self):
        path = self.root / "docs/pm/tickets/T004-log-format.md"
        text = path.read_text().replace("epic: E01", "epic: E09").replace("depends_on: []", "depends_on: [T999]")
        text = text.replace("- [ ] Something testable happens.\n", "")
        path.write_text(text)
        problems = pm_lib.validate(self.root)
        self.assertIn("T004: unknown epic E09", problems)
        self.assertIn("T004: depends on unknown ticket T999", problems)
        self.assertIn("T004: Acceptance section is empty", problems)

    def test_reports_cycle(self):
        p2 = self.root / "docs/pm/tickets/T002-rate-limit.md"
        p2.write_text(p2.read_text().replace("depends_on: [T001]", "depends_on: [T003]"))
        problems = pm_lib.validate(self.root)
        self.assertTrue(any("cycle" in p for p in problems), problems)


class ValidateStrictnessTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_repo(Path(self.tmp.name))
        p7 = self.root / "docs/pm/tickets/T007-share-revoke.md"
        p7.write_text(p7.read_text().replace("owner: agent-b", "owner:"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_placeholders_count_as_unfilled(self):
        path = self.root / "docs/pm/tickets/T004-log-format.md"
        text = path.read_text().replace("- [ ] Something testable happens.", "- [ ] (one testable line per item)")
        text = text.replace("## What\nTidy login log format.", "## What\n(fill in)")
        path.write_text(text)
        problems = pm_lib.validate(self.root)
        self.assertIn("T004: Acceptance section is empty", problems)
        self.assertIn("T004: What section is empty", problems)

    def test_pm_block_must_be_key_value_lines(self):
        ctx = self.root / "CONTEXT.md"
        ctx.write_text("# x\n\n## pm\n\n**Flow:** branch-local\n**Gates:** tdd\n")
        problems = pm_lib.validate(self.root)
        self.assertTrue(any("pm block" in p and "flow:" in p for p in problems), problems)
        ctx.write_text("# x\n\n## pm\nflow: branch-local\ngates: tdd\ncheck: make test\n")
        self.assertEqual(pm_lib.validate(self.root), [])

    def test_missing_context_is_reported_once(self):
        (self.root / "CONTEXT.md").unlink()
        problems = pm_lib.validate(self.root)
        self.assertEqual(problems, ["CONTEXT.md: missing, so the pm block is missing (run /pm:init)"])

    def test_milestone_goal_without_label_is_still_found(self):
        roadmap = self.root / "docs/pm/roadmap.md"
        roadmap.write_text(roadmap.read_text().replace("Goal: a person can log in and see their list.", "A person can log in and see their list."))
        self.assertEqual(pm_lib.milestone_goal(self.root, "M1"), "A person can log in and see their list.")


class ConfigNormalisationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_repo(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_mirror_and_merge_values_are_normalised(self):
        ctx = self.root / "CONTEXT.md"
        ctx.write_text(ctx.read_text().replace("mirror: off", "mirror: yes").replace("merge: ask", "merge: Auto"))
        cfg = pm_lib.read_config(self.root)
        self.assertEqual(cfg["mirror"], "on")
        self.assertEqual(cfg["merge"], "auto")
        ctx.write_text(ctx.read_text().replace("mirror: yes", "mirror: no"))
        self.assertEqual(pm_lib.read_config(self.root)["mirror"], "off")


class PlaceholderAnywhereTest(unittest.TestCase):
    def test_a_fill_in_placeholder_in_any_section_is_a_problem(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp))
            p = root / "docs/pm/tickets/T002-rate-limit.md"
            p.write_text(p.read_text().replace("Because the fixture says so.", "(fill in)"))
            problems = pm_lib.validate(root)
            self.assertTrue(any("T002: placeholder left in Why" in x for x in problems), problems)
