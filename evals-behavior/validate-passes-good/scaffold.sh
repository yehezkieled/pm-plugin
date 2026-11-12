#!/usr/bin/env bash
# textkit with item word-count-3f9a1c claimed and its work committed on pm/word-count-3f9a1c, ready for validation.
# The work is right: word_count splits on any whitespace, its tests pass, and every file is in its place.
set -euo pipefail
mkdir -p docs/pm/items src/textkit tests
cat > README.md <<'EOF_FIXTURE'
# textkit

Small text helpers in plain Python.

Run the tests with `python3 -m unittest discover -s tests`.
EOF_FIXTURE
cat > AGENTS.md <<'EOF_FIXTURE'
# textkit

Small text helpers in plain Python. Shape: app. Product overview: [README.md](README.md).

This file routes; the facts live in the files it points at. Where each kind of knowledge goes: `/pm:help`.

## Where things go

Before creating any file, find its kind here and put it in that place. No row fits: ask once, recommend a place, and add the row in the same change. Nothing else goes at the root. A place that exists is a link, to its folder's `README.md` when it has one; a place with no file yet stays a plain path until its first file lands. `out/` is never a link: it is gitignored.

| Kind of thing | Place | Rule |
| --- | --- | --- |
| Tasks: what is being done and what is next | `docs/pm/items/` | `/pm:plan` adds them and `/pm:work` hands them to workers; never made by hand |
| How it works, decisions, gotchas | [`docs/`](docs/) | one file per topic; update it, don't duplicate it |
| Deliverables for people: memos, reports, findings | `reports/` | `YYYY-MM-DD-<topic>.md` |
| Generated outputs | `out/` | written only by code; gitignored |
| Project files at the root | `README.md`, `AGENTS.md`, `CLAUDE.md`, `.gitignore` | nothing else at the root |
| Library code | [`src/textkit/`](src/textkit/) | one function per concern, exported from `__init__.py` |
| Tests | [`tests/`](tests/) | `test_<module>.py`, run with `python3 -m unittest discover -s tests` |

## When you finish a task

Before you finish, update what this table names for your change, and keep every link working: the pm plugin's walk test (`pm.py walk`) fails on a broken or missing link.

| If your change | Update |
| --- | --- |
| adds a folder or a new kind of file | a row above whose place links to the folder's new `README.md`; that `README.md` says what the folder holds, links each file it describes, and links back to [AGENTS.md](AGENTS.md) |
| puts the first file in a place above that is still a plain path | that row: make the place a link |
| changes what a folder holds or how it is used | that folder's `README.md` or `CONTEXT.md`, linked from its row |
| changes how to install, run, or use the project | [README.md](README.md), and Every session below for build and test commands |
| changes a part that has a card in the System map | that card, its date and commit, or `status: stale` |

## Route by task

| If you are | Go to |
| --- | --- |
| adding or tracking work | `/pm:plan` |
| doing any project work | `/pm:work` |
| running the tests | `python3 -m unittest discover -s tests` |

## Every session

- Test: `python3 -m unittest discover -s tests`.
EOF_FIXTURE
cat > CLAUDE.md <<'EOF_FIXTURE'
@AGENTS.md
EOF_FIXTURE
cat > .gitignore <<'EOF_FIXTURE'
out/
__pycache__/
EOF_FIXTURE
cat > docs/pm/config.json <<'EOF_FIXTURE'
{}
EOF_FIXTURE
cat > src/textkit/__init__.py <<'EOF_FIXTURE'
"""Small text helpers."""


def slugify(text):
    """Lower-case words joined by hyphens: "Hello World" -> "hello-world"."""
    return "-".join(text.lower().split())
EOF_FIXTURE
cat > tests/test_textkit.py <<'EOF_FIXTURE'
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from textkit import slugify  # noqa: E402


class SlugifyTests(unittest.TestCase):
    def test_joins_lower_case_words(self):
        self.assertEqual(slugify("Hello  World"), "hello-world")


if __name__ == "__main__":
    unittest.main()
EOF_FIXTURE
cat > docs/pm/items/word-count-3f9a1c.md <<'EOF_FIXTURE'
---
id: "word-count-3f9a1c"
status: "queued"
owner: ""
depends_on: []
hold: ""
hold_until: ""
done_at: ""
intent_length: 97
---
# Word count

## Requester intent
Add a word_count(text) function to textkit that returns how many words a string has, with a test.

## Current notes

EOF_FIXTURE
git init -q -b main
git add -A
git -c user.name=eval -c user.email=eval@example.com commit -qm "initial"
sed -i 's/^status: "queued"$/status: "in-flight"/; s/^owner: ""$/owner: "eval"/' docs/pm/items/word-count-3f9a1c.md
git -c user.name=eval -c user.email=eval@example.com commit -qam "pm: Claimed word-count-3f9a1c for eval. Claim is saved before work starts."
git switch -q -c pm/word-count-3f9a1c
cat >> src/textkit/__init__.py <<'EOF_FIXTURE'


def word_count(text):
    """How many words the text has; any run of whitespace separates words."""
    return len(text.split())
EOF_FIXTURE
cat > tests/test_word_count.py <<'EOF_FIXTURE'
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from textkit import word_count  # noqa: E402


class WordCountTests(unittest.TestCase):
    def test_counts_words(self):
        self.assertEqual(word_count("one two three"), 3)

    def test_runs_of_spaces_separate_one_word(self):
        self.assertEqual(word_count("two  words"), 2)

    def test_empty_text_has_no_words(self):
        self.assertEqual(word_count(""), 0)


if __name__ == "__main__":
    unittest.main()
EOF_FIXTURE
git add -A
git -c user.name=eval -c user.email=eval@example.com commit -qm "word-count-3f9a1c: add word_count with tests"
