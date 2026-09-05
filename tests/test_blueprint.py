"""The design page ships with the plugin as docs/blueprint.html and opens on its own in a browser."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs/blueprint.html"


class BlueprintPageTest(unittest.TestCase):
    def test_page_is_a_complete_html_document(self):
        self.assertTrue(PAGE.is_file(), "docs/blueprint.html is missing")
        text = PAGE.read_text()
        self.assertTrue(text.lstrip().lower().startswith("<!doctype html>"))
        for tag in ("<html", "<head>", "<meta charset", "<title>", "</head>", "<body>", "</body>", "</html>"):
            self.assertIn(tag, text)
        self.assertTrue(text.rstrip().endswith("</html>"))

    def test_diagrams_render_outside_the_artifact_viewer(self):
        text = PAGE.read_text()
        self.assertIn('<pre class="mermaid">', text)
        pinned = re.search(r'<script src="https://cdnjs\.cloudflare\.com/ajax/libs/mermaid/\d+\.\d+\.\d+/mermaid\.min\.js"></script>', text)
        self.assertIsNotNone(pinned, "mermaid must load from cdnjs with an exact version")
        self.assertIn("mermaid.initialize(", text)

    def test_page_carries_no_plugin_version_number(self):
        # the page would go stale on every version bump otherwise
        self.assertIsNone(re.search(r"version \d+\.\d+\.\d+", PAGE.read_text()))

    def test_readme_and_help_point_at_the_page(self):
        self.assertIn("docs/blueprint.html", (ROOT / "README.md").read_text())
        self.assertIn("docs/blueprint.html", (ROOT / "skills/help/SKILL.md").read_text())


if __name__ == "__main__":
    unittest.main()
