"""Guard: the plugin must never push dates, deadlines or effort guesses.

A line is allowed to mention one of these words only when it forbids it
(never, no, not, without, don't, do not).
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN = ["skills", "templates", "scripts", "hooks", "docs", "README.md", ".claude-plugin"]
BANNED = [
    r"\bdeadlines?\b", r"\bdue dates?\b", r"\bdue by\b", r"\btarget dates?\b", r"\beta\b",
    r"\bestimat(e|es|ed|ion|ions)\b", r"\bvelocity\b", r"\bstory points?\b", r"\bon track\b",
    r"\bbehind schedule\b", r"\bsprints?\b", r"\bhours?\b", r"\bdays? left\b", r"\bburndown\b",
    r"\btime[- ]?box(ed|ing)?\b", r"\bweeks?\b", r"\bmonths?\b", r"\bschedule[ds]?\b",
    r"\bcountdown\b", r"\bhow long\b",
]
NEGATION = re.compile(r"\b(never|no|not|without|don't|do not|nor|instead of)\b", re.I)


def files():
    for name in SCAN:
        path = ROOT / name
        if path.is_file():
            yield path
        elif path.is_dir():
            for p in path.rglob("*"):
                if p.is_file() and p.suffix in (".md", ".py", ".sh", ".json", ".txt", ".html"):
                    yield p


class NoTimeTrackingTest(unittest.TestCase):
    def test_plugin_text_never_asks_for_dates_or_effort(self):
        hits = []
        for path in files():
            for n, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
                for pattern in BANNED:
                    m = re.search(pattern, line, re.I)
                    if m and not NEGATION.search(line[: m.start()]):
                        hits.append(f"{path.relative_to(ROOT)}:{n}: '{m.group(0)}' in: {line.strip()[:80]}")
        self.assertEqual(hits, [], "\n" + "\n".join(hits))


if __name__ == "__main__":
    unittest.main()
