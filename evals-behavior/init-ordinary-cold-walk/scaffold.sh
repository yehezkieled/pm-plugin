#!/usr/bin/env bash
# An ordinary Python library with no board and no remote, so /pm:init runs to the walk test without a push.
set -euo pipefail
mkdir -p src/tinyslug tests
cat > README.md <<'MD'
# tinyslug

Turns titles into URL slugs. Install with `pip install -e .`; test with `python -m unittest discover -s tests`.
MD
cat > pyproject.toml <<'TOML'
[project]
name = "tinyslug"
version = "0.1.0"
TOML
cat > src/tinyslug/__init__.py <<'PY'
import re


def slugify(title):
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
PY
cat > tests/test_slug.py <<'PY'
import unittest

from tinyslug import slugify


class SlugTest(unittest.TestCase):
    def test_spaces(self):
        self.assertEqual(slugify("Hello World"), "hello-world")
PY
git init -q
git add -A
git -c user.name=eval -c user.email=eval@example.com commit -qm "initial"
