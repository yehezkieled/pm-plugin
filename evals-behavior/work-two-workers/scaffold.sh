#!/usr/bin/env bash
# textkit, a tiny Python library set up by /pm:init (app shape), with two independent ready items on the board.
# No remote, so board writes stay local; parallel workers share the main checkout's board. The person already
# chose the worker and validator model and effort and this clone's permission setting.
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

Before creating any file, find its kind here and put it in that place. No row fits: ask once, recommend a place, and add the row in the same change. Nothing else goes at the root.

| Kind of thing | Place | Rule |
| --- | --- | --- |
| Tasks: what is being done and what is next | `docs/pm/items/` | `/pm:plan` adds them and `/pm:work` hands them to workers; never made by hand |
| How it works, decisions, gotchas | `docs/` | one file per topic; update it, don't duplicate it |
| Deliverables for people: memos, reports, findings | `reports/` | `YYYY-MM-DD-<topic>.md` |
| Generated outputs | `out/` | written only by code; gitignored |
| Project files at the root | `README.md`, `AGENTS.md`, `CLAUDE.md`, `.gitignore` | nothing else at the root |
| Library code | `src/textkit/` | one function per concern, exported from `__init__.py` |
| Tests | `tests/` | `test_<module>.py`, run with `python3 -m unittest discover -s tests` |

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
{"mirror": "off", "workers": {"model": "claude-sonnet-5-5", "effort": "medium"}, "validators": {"model": "claude-sonnet-5-5", "effort": "medium"}}
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
github_issue: ""
---
# Word count

## Requester intent
Add a word_count(text) function to textkit that returns how many words a string has, with a test.

## Current notes

EOF_FIXTURE
cat > docs/pm/items/title-case-7d2e4b.md <<'EOF_FIXTURE'
---
id: "title-case-7d2e4b"
status: "queued"
owner: ""
depends_on: []
hold: ""
hold_until: ""
done_at: ""
intent_length: 103
github_issue: ""
---
# Title case

## Requester intent
Add a title_case(text) function to textkit that capitalises the first letter of each word, with a test.

## Current notes

EOF_FIXTURE
git init -q -b main
git add -A
git -c user.name=eval -c user.email=eval@example.com commit -qm "initial"
# The person's earlier choice for this clone: worker sessions run in auto mode.
mkdir -p .git/pm-workers && printf '%s\n' '{"permission_mode": "auto"}' > .git/pm-workers/settings.json
