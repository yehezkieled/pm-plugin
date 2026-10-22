import html
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "pm.py"
START_HOOK = ROOT / "hooks" / "session-start.sh"
TEMPLATES = ROOT / "icm" / "templates"
MAP = "docs/pm/map"
FILL = {"cluster": "core", "card": "link", "Name": "Link", "path": "src/app.py", "line": "1", "path to the owning file": "src/app.py",
        "process-name": "shorten", "NN": "01", "stage-name": "research", "name": "research", "run": "demo",
        "rules-file": "rules", "guide": "guide", "skill-name": "brief", "previous stage folder": "00_input"}

CARD = """---
type: object
cluster: core
universe: live
status: verified
verified: 2026-10-22
commit: abc1234
entity: src/app.py
---

# Link

A short code that maps to a long URL.

## Why this shape

Codes are prefixes, so a lookup is one slice.

## Shape

- `shorten` keeps the first 8 characters: `src/app.py:1-2`

## Connected to

- **owns:** nothing

## If you change this

- **Hits:** expand
- **Does not hit:** README

## Surfaces

| Surface | Role |
| --- | --- |
| CLI | reads |

## See

- Source: `src/app.py`
"""


def fill(text):
    return re.sub(r"\{([^{}\n]+)\}", lambda m: FILL.get(m.group(1), "filled"), text)


class IcmTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.root, check=True)
        self.write("src/app.py", "def shorten(url):\n    return url[:8]\n\ndef expand(code):\n    return code\n")
        self.write("README.md", "# shortlink\n\nA tiny URL shortener.\n")
        self.cli("init")

    def tearDown(self):
        self.temp.cleanup()

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def cli(self, *args, ok=True, input_text=None):
        result = subprocess.run(["python3", str(CLI), *args], cwd=self.root, text=True, input=input_text, capture_output=True)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        return result

    def walk(self, ok=True):
        return self.cli("walk", ok=ok).stdout

    def build_map(self):
        """An ordinary project with a System map, its catalog and contract filled in from the templates."""
        self.write("AGENTS.md", fill((TEMPLATES / "root-AGENTS.md").read_text())
                   + "| understanding the code | [docs/pm/map/AGENTS.md](docs/pm/map/AGENTS.md) |\n")
        self.write("CLAUDE.md", "@AGENTS.md\n")
        self.write(f"{MAP}/AGENTS.md", fill((TEMPLATES / "map-AGENTS.md").read_text()))
        self.write(f"{MAP}/CLAUDE.md", "@AGENTS.md\n")
        self.write(f"{MAP}/CONTEXT.md", fill((TEMPLATES / "map-CONTEXT.md").read_text()))
        self.write(f"{MAP}/effects/CONTEXT.md", fill((TEMPLATES / "effects-CONTEXT.md").read_text()))
        for name in ("object.md", "process.md"):
            self.write(f"{MAP}/_templates/{name}", (TEMPLATES / name).read_text())
        self.write(f"{MAP}/objects/core/link.md", CARD)
        self.write(f"{MAP}/processes/link.md", fill((TEMPLATES / "process.md").read_text()))
        self.cli("index")

    def build_workflow(self):
        skill = ".claude/skills/brief"
        self.write("AGENTS.md", "# Brief\n\nThe workflow: [SKILL.md](.claude/skills/brief/SKILL.md)\n")
        self.write("CLAUDE.md", "@AGENTS.md\n")
        self.write(f"{skill}/SKILL.md", fill((TEMPLATES / "workflow-SKILL.md").read_text()))
        for stage in ("01_research", "02_research"):
            self.write(f"{skill}/stages/{stage}/CONTEXT.md", fill((TEMPLATES / "stage-CONTEXT.md").read_text()))
            self.write(f"{skill}/stages/{stage}/references/guide.md", "# Guide\n")
        self.write(f"{skill}/_shared/rules.md", "# Rules\n")
        return skill

    # ---- the walk test

    def test_templates_filled_in_pass_the_walk_test(self):
        self.build_map()
        out = self.walk()
        self.assertIn("Walk test: passed", out)
        self.assertIn("2 cards have their frontmatter", out)
        self.assertRegex(out, r"entry \+ map catalog \+ largest card or contract: about [\d,]+ tokens")

    def test_a_workflow_skill_from_the_templates_passes_and_packages(self):
        self.build_workflow()
        out = self.walk()
        self.assertIn("Workflow .claude/skills/brief/ has 2 numbered stages and is packageable", out)
        self.assertIn("workflow SKILL.md", out)

    def test_a_workflow_that_would_not_package_fails(self):
        skill = self.build_workflow()
        text = (self.root / skill / "SKILL.md").read_text()
        self.write(f"{skill}/SKILL.md", text.replace("name: brief", "name: other").replace("Use when", "Run if")
                   + "\nSee [the readme](../../../README.md) and [stage 9](stages/09_ship/CONTEXT.md).\n")
        self.write(f"{skill}/stages/notes/x.md", "loose\n")
        self.write(f"{skill}/stages/03_ship/references/r.md", "# r\n")
        self.write(f"{skill}/stages/01_research/output/draft.md", "a run\n")
        out = self.walk(ok=False)
        for expected in ("needs `name: brief`", "'Use when'", "stages/notes/ is not numbered", "stages/03_ship/ has no CONTEXT.md",
                         "links outside the skill (../../../README.md)", "links to stages/09_ship/CONTEXT.md, which does not exist", "run output inside the skill (stages/01_research/output)"):
            self.assertIn(expected, out)

    def test_entry_file_must_stay_a_small_catalog_with_one_hand_edited_copy(self):
        self.write("AGENTS.md", "# Project\n" + "".join(f"- rule {n}\n" for n in range(70)))
        self.write("CLAUDE.md", "# Project\nDifferent content\n")
        out = self.walk(ok=False)
        self.assertIn("AGENTS.md has 71 lines; the entry file is a catalog and stays under 60", out)
        self.assertIn("CLAUDE.md and AGENTS.md are two hand-maintained entry files", out)
        self.write("CLAUDE.md", "@AGENTS.md\n")
        self.write("AGENTS.md", "# Project\n\nOverview: [README.md](README.md)\n")
        self.assertIn("Walk test: passed", self.walk())
        self.write("CLAUDE.md", "@AGENTS.md\n@~/.claude/my-instructions.md\n@/etc/team/rules.md\n")
        self.assertIn("Walk test: passed", self.walk())
        self.write("CLAUDE.md", "@AGENTS.md\n@docs/missing.md\n")
        self.assertIn("CLAUDE.md:2 -> docs/missing.md", self.walk(ok=False))
        self.write("CLAUDE.md", "@AGENTS.md\nExtra rule\n")
        self.assertIn("two hand-maintained entry files", self.walk(ok=False))

    def test_missing_entry_file_fails(self):
        self.assertIn("No entry file", self.walk(ok=False))

    def test_broken_links_after_a_move_fail(self):
        self.build_map()
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True)
        (self.root / "README.md").rename(self.root / "OVERVIEW.md")
        out = self.walk(ok=False)
        self.assertIn("Links that do not resolve", out)
        self.assertIn("AGENTS.md:3 -> README.md", out)

    def test_working_folder_contracts_need_all_five_sections(self):
        self.build_map()
        contract = (self.root / MAP / "CONTEXT.md").read_text()
        self.write(f"{MAP}/CONTEXT.md", contract.replace("## Verify", "## Checks"))
        self.write("stages/01_draft/CONTEXT.md", "# 01\n\n## Inputs\n- x\n\n## Process\n1. x\n")
        out = self.walk(ok=False)
        self.assertIn(f"{MAP}/CONTEXT.md is a working folder's contract but lacks: ## Verify.", out)
        self.assertIn("stages/01_draft/CONTEXT.md is a working folder's contract but lacks: ## Outputs, ## Verify, ## Human check.", out)

    def test_a_glossary_in_context_md_is_flagged_and_oversized_contracts_fail(self):
        self.write("AGENTS.md", "# P\n\n[README.md](README.md)\n")
        self.write("CONTEXT.md", "# Glossary\n\n- **Board**: the list of items\n")
        self.assertIn("WARN  CONTEXT.md points at nothing", self.walk())
        self.write("CONTEXT.md", "# Router\n\n[README.md](README.md)\n" + "line\n" * 90)
        self.assertIn("CONTEXT.md has 93 lines; a CONTEXT.md routes and stays under 80", self.walk(ok=False))

    def test_cards_must_carry_frontmatter_citations_and_both_sides_of_impact(self):
        self.build_map()
        card = self.root / MAP / "objects/core/link.md"
        self.write(f"{MAP}/objects/core/link.md", CARD.replace("commit: abc1234\n", "").replace("- **Does not hit:** README\n", "")
                   .replace("`src/app.py:1-2`", "`src/app.py:1-40`").replace("universe: live", "universe: maybe"))
        self.cli("index")
        out = self.walk(ok=False)
        for expected in ("universe is maybe", "needs both Hits and Does not hit", "`verified: YYYY-MM-DD` and `commit:`",
                         "src/app.py:40 is past the end of the file"):
            self.assertIn(expected, out)
        self.write(f"{MAP}/objects/core/link.md", CARD.replace("`src/app.py:1-2`", "nothing cited"))
        self.assertIn("verified card cites no source", self.walk(ok=False))
        self.write(f"{MAP}/objects/core/link.md", (TEMPLATES / "object.md").read_text())
        self.cli("index")
        self.assertIn("template line not filled in: cluster: {cluster}", self.walk(ok=False))
        self.assertTrue(card.exists())

    def test_a_map_with_several_cards_needs_its_change_impact_index(self):
        self.build_map()
        (self.root / MAP / "effects/CONTEXT.md").unlink()
        (self.root / MAP / "effects").rmdir()
        self.assertIn(f"{MAP}/ has 2 cards but no effects/CONTEXT.md", self.walk(ok=False))
        (self.root / MAP / "processes/link.md").unlink()
        (self.root / MAP / "processes").rmdir()
        catalog = self.root / MAP / "AGENTS.md"
        catalog.write_text("".join(line for line in catalog.read_text().splitlines(keepends=True) if "effects/" not in line))
        self.cli("index")
        self.assertIn("Walk test: passed", self.walk())

    def test_stub_cards_only_warn_about_missing_source(self):
        self.build_map()
        self.write(f"{MAP}/objects/core/code.md", "---\ntype: object\ncluster: core\nuniverse: ghost\nstatus: stub\n---\n\n"
                                                  "# Code\n\nThe short code; see `src/codes.py:3`.\n")
        self.cli("index")
        out = self.walk()
        self.assertIn("WARN  objects/core/code.md (stub) cites missing source: src/codes.py does not exist", out)

    def test_index_is_generated_from_cards_and_a_hand_edit_is_caught(self):
        self.build_map()
        index = (self.root / MAP / "_index.md").read_text()
        self.assertIn("2 cards: 1 stub, 1 verified, 0 stale.", index)
        self.assertIn("### core\n\n- [Link](objects/core/link.md) — verified · live — A short code that maps to a long URL.", index)
        self.assertIn("## Processes\n\n- [shorten](processes/link.md) — stub", index)
        self.write(f"{MAP}/_index.md", index + "- hand-added line\n")
        self.assertIn("_index.md is missing or out of date. Run pm.py index", self.walk(ok=False))
        self.cli("index")
        self.assertIn("Walk test: passed", self.walk())

    def test_map_needs_a_route_from_the_entry_file_and_no_empty_shelves(self):
        self.build_map()
        self.write("AGENTS.md", "# shortlink\n\n[README.md](README.md)\n")
        (self.root / MAP / "processes" / "link.md").unlink()
        self.cli("index")
        out = self.walk(ok=False)
        self.assertIn("does not route to the System map", out)
        self.assertIn(f"{MAP}/processes/ is empty", out)

    def test_old_codebase_file_is_flagged_until_retired(self):
        self.write("AGENTS.md", "# P\n\n[README.md](README.md)\n")
        self.write("docs/pm/CODEBASE.md", "# Architecture\n")
        self.assertIn("docs/pm/CODEBASE.md is not a System map yet", self.walk())
        self.build_map()
        self.assertIn("a second home for architecture", self.walk())

    def test_token_budget_for_one_walk(self):
        self.build_map()
        self.write(f"{MAP}/objects/core/link.md", CARD + "\nNotes: " + "word " * 7000 + "\n")
        self.assertIn("one walk should stay under 8,000", self.walk(ok=False))

    def test_index_needs_a_map(self):
        result = self.cli("index", ok=False)
        self.assertIn("No System map", result.stderr)

    # ---- reference integrity before a move

    def test_refs_lists_referrers_and_refuses_a_case_folded_collision(self):
        self.write("docs/notes.md", "# notes\n")
        self.write("docs/guide/intro.md", "Read [the notes](../notes.md) first.\n")
        self.write("AGENTS.md", "- Notes live in docs/notes.md\n- see notes.md\n")
        self.write("docs/Context.md", "# taken\n")
        os.symlink("notes.md", self.root / "docs" / "latest.md")
        result = self.cli("refs", "docs/notes.md=docs/context.md", ok=False)
        self.assertIn("docs/guide/intro.md:1 (link)", result.stdout)
        self.assertIn("AGENTS.md:1 (path)", result.stdout)
        self.assertIn("docs/latest.md (symlink)", result.stdout)
        self.assertIn("names it without a path (check by hand): AGENTS.md:2", result.stdout)
        self.assertIn("destination is taken: docs/Context.md", result.stdout)
        self.assertIn("destination is already taken", result.stderr)
        free = self.cli("refs", "docs/notes.md=docs/pm/notes.md").stdout
        self.assertIn("destination is free (compared case-folded)", free)
        self.assertIn("ask the owner", free)
        self.assertIn("does not exist", self.cli("refs", "nope.md", ok=False).stderr)

    # ---- items name what they touch

    def item_file(self, item_id):
        return next((self.root / "docs/pm/items").glob(f"{item_id}-*.md"))

    def add(self, *args):
        out = self.cli("add", *args, input_text="Shorter links\nmake links shorter").stdout
        return out.split(":", 1)[0].split()[-1]

    def test_touches_are_saved_checked_and_cleared(self):
        self.build_map()
        card = f"{MAP}/objects/core/link.md"
        item_id = self.add("--touches", f"{card}, ./{MAP}/processes/link.md")
        meta = self.item_file(item_id).read_text().split("---\n", 2)[1]
        self.assertIn(f'touches: ["{card}", "{MAP}/processes/link.md"]', meta)
        self.assertIn("does not exist in this checkout", self.cli("add", "--touches", "missing.md", ok=False,
                                                                  input_text="t\ni").stderr)
        self.assertIn("inside this repository", self.cli("set", item_id, "--touches", "../x", ok=False).stderr)
        self.cli("set", item_id, "--touches", "")
        self.assertNotIn("touches:", self.item_file(item_id).read_text())
        self.cli("set", item_id, "--touches", card)
        self.assertIn("Walk test: passed", self.walk())
        moved = self.root / MAP / "objects/core/link.md"
        moved.rename(moved.with_name("url.md"))
        self.cli("index")
        self.assertIn(f"Item {item_id} touches paths that do not exist: {card}", self.walk(ok=False))
        self.assertIn("Give --depends, --touches, or both", self.cli("set", item_id, ok=False).stderr)
        self.cli("claim", item_id, input_text="Ari")
        self.assertIn(f"Item {item_id} touches paths that do not exist", self.walk(ok=False))
        self.cli("finish", item_id, input_text="")
        self.assertNotIn("touches paths that do not exist", self.walk(ok=False))

    def test_items_without_new_fields_keep_their_exact_format(self):
        item_id = self.add()
        before = self.item_file(item_id).read_text()
        self.assertNotIn("touches", before)
        self.assertNotIn("corrections", before)
        self.cli("claim", item_id, input_text="Ari")
        after = self.item_file(item_id).read_text()
        self.assertEqual(before.replace('"queued"', '"in-flight"').replace('owner: ""', 'owner: "Ari"'), after)

    # ---- fix the source when a correction repeats

    def test_third_correction_of_a_kind_suggests_fixing_the_source_until_it_is_fixed(self):
        self.build_map()
        item_id = self.add()
        card = f"{MAP}/objects/core/link.md"
        first = self.cli("correct", item_id, "--kind", "Opening too long", "--where", card, input_text="cut the intro").stdout
        self.assertIn(f"Recorded correction opening-too-long on `{card}` for {item_id}: 1 of this kind there so far.", first)
        self.cli("correct", item_id, "--kind", "tone", "--where", card, input_text="too formal")
        second = self.cli("correct", item_id, "--kind", "opening-too-long", "--where", card, input_text="again").stdout
        self.assertIn("Other kinds recorded here: tone (1).", second)
        third = self.cli("correct", item_id, "--kind", "opening-too-long", "--where", card, input_text="third time").stdout
        self.assertIn("Same correction 3 times: fix the source, not the output.", third)
        self.assertIn(f"pm.py correct {item_id} --kind opening-too-long --where {card} --fixed", third)
        board = self.cli("board").stdout
        self.assertIn(f"Fix the source: opening-too-long was corrected 3 times on {card}.", board)
        self.cli("correct", item_id, "--kind", "opening-too-long", "--where", card, "--fixed",
                 input_text="The card now says to keep openings under three sentences.")
        self.assertNotIn("Fix the source", self.cli("board").stdout)
        again = self.cli("correct", item_id, "--kind", "opening-too-long", "--where", card, input_text="once more").stdout
        self.assertIn("1 of this kind there since the source was last fixed for it.", again)
        meta = self.item_file(item_id).read_text().split("---\n", 2)[1]
        corrections = json.loads(next(line.partition(": ")[2] for line in meta.splitlines() if line.startswith("corrections:")))
        self.assertEqual([c["kind"] for c in corrections], ["opening-too-long", "tone", "opening-too-long", "opening-too-long",
                                                             "opening-too-long", "opening-too-long"])
        self.assertTrue(corrections[4]["fixed"])
        self.assertEqual(corrections[0]["note"], "cut the intro")

    def test_corrections_count_across_items_and_project_wide(self):
        first, second, third = self.add(), self.add(), self.add()
        for item_id in (first, second):
            self.cli("correct", item_id, "--kind", "missing-tests", input_text="no tests")
        out = self.cli("correct", third, "--kind", "missing-tests", input_text="no tests again").stdout
        self.assertIn("on the whole project", out)
        self.assertIn("Same correction 3 times", out)
        self.assertIn("1 of this kind in the project so far", self.cli("correct", first, "--kind", "tone", input_text="formal").stdout)
        self.assertIn("the source behind it: AGENTS.md if it applies to every session", out)
        self.assertIn("corrected 3 times on the whole project", self.cli("board").stdout)

    def test_correct_needs_a_kind_a_note_and_a_real_place(self):
        item_id = self.add()
        self.assertIn("Describe the correction", self.cli("correct", item_id, "--kind", "x", ok=False, input_text=" ").stderr)
        self.assertIn("--kind needs", self.cli("correct", item_id, "--kind", "!!", ok=False, input_text="n").stderr)
        self.assertIn("does not exist", self.cli("correct", item_id, "--kind", "x", "--where", "nope.md", ok=False,
                                                 input_text="n").stderr)

    # ---- session start points an old architecture file at the System map

    def test_session_start_points_codebase_md_at_the_system_map(self):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.root))
        hook = lambda: subprocess.run(["bash", str(START_HOOK)], cwd=self.root, env=env, input="{}", text=True,
                                      capture_output=True, check=True).stdout
        self.assertNotIn("CODEBASE.md", hook())
        self.write("docs/pm/CODEBASE.md", "# Architecture\n")
        self.assertIn("Run /pm:map to convert it", hook())
        self.assertIn("pm:work skill to claim it first", hook().strip().splitlines()[-1])
        self.build_map()
        self.assertNotIn("CODEBASE.md", hook())


class IcmDocsTests(unittest.TestCase):
    """The vendored method keeps its license and credit, and the docs describe one flow."""

    def test_license_and_credit_are_kept(self):
        license_text = (ROOT / "icm" / "LICENSE").read_text()
        self.assertIn("Copyright (c) 2026 Jake Van Clief", license_text)
        self.assertIn("Copyright (c) 2026 Model Workspace Protocol Contributors", license_text)
        self.assertEqual(license_text.count("Permission is hereby granted"), 2)
        for path in ("THIRD_PARTY_NOTICES.md", "README.md", "icm/README.md"):
            text = (ROOT / path).read_text()
            self.assertTrue("Jake Van Clief" in text and "arXiv" in text, f"{path} must credit the ICM authors and paper")
        for path in sorted((ROOT / "icm").glob("*.md")):
            if path.name != "README.md":
                self.assertIn("LICENSE", path.read_text(), f"{path.name} must point at the license")

    def test_contract_templates_carry_verify_before_the_human_check(self):
        for name in ("stage-CONTEXT.md", "map-CONTEXT.md"):
            headings = [line for line in (TEMPLATES / name).read_text().splitlines() if line.startswith("## ")]
            self.assertEqual(headings, ["## Inputs", "## Process", "## Outputs", "## Verify", "## Human check"], name)

    def test_guide_shows_the_current_help_and_placement_guide(self):
        guide = (ROOT / "docs" / "guide.html").read_text()
        block = re.search(r"```text\n(.*?)```", (ROOT / "skills/help/SKILL.md").read_text(), re.S).group(1).rstrip()
        self.assertTrue(html.escape(block, quote=True) in guide, "docs/guide.html: /pm:help command list is out of date")
        placement = (ROOT / "docs" / "placement.md").read_text().rstrip()
        self.assertTrue(html.escape(placement, quote=True) in guide, "docs/guide.html: printed placement guide is out of date")

    def test_docs_cover_the_new_commands(self):
        texts = {name: (ROOT / name).read_text() for name in ("skills/help/SKILL.md", "README.md", "docs/manual.md", "docs/guide.html")}
        for command in ("walk", "index", "refs", "correct"):
            for name, text in texts.items():
                self.assertTrue(f"pm.py {command}" in text, f"{name} should mention pm.py {command}")
        for name in ("README.md", "docs/manual.md", "docs/guide.html"):
            self.assertTrue("docs/pm/map" in texts[name], f"{name} should describe docs/pm/map")


if __name__ == "__main__":
    unittest.main()
