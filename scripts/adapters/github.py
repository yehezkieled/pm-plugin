"""GitHub adapter for pm_sync, built on the `gh` command line tool."""
from __future__ import annotations

import re
import subprocess


def issue_number(url: str) -> int:
    m = re.search(r"/(?:issues|pull)/(\d+)", url)
    if not m:
        raise ValueError(f"no issue number in: {url.strip()}")
    return int(m.group(1))


def _run(args: list[str]) -> str:
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"{' '.join(args[:3])} failed: {proc.stderr.strip()}")
    return proc.stdout


class GithubAdapter:
    def __init__(self, runner=None):
        self.run = runner or _run

    def list_milestones(self) -> dict[str, int]:
        out = self.run(["gh", "api", "repos/{owner}/{repo}/milestones?state=all&per_page=100",
                        "--jq", '.[] | "\\(.number)\\t\\(.title)"'])
        result = {}
        for line in out.splitlines():
            number, sep, title = line.partition("\t")
            if sep:
                result[title] = int(number)
        return result

    def create_milestone(self, title: str, description: str) -> int:
        out = self.run(["gh", "api", "-X", "POST", "repos/{owner}/{repo}/milestones",
                        "-f", f"title={title}", "-f", f"description={description}", "--jq", ".number"])
        return int(out.strip())

    def ensure_label(self, name: str) -> None:
        self.run(["gh", "label", "create", name, "--force"])

    def create_issue(self, title, body, labels, milestone) -> int:
        args = ["gh", "issue", "create", "--title", title, "--body", body]
        for label in labels:
            args += ["--label", label]
        if milestone:
            args += ["--milestone", milestone]
        return issue_number(self.run(args))

    def update_issue(self, number, title, body, labels, milestone) -> None:
        args = ["gh", "issue", "edit", str(number), "--title", title, "--body", body]
        for label in labels:
            args += ["--add-label", label]
        if milestone:
            args += ["--milestone", milestone]
        self.run(args)

    def close_issue(self, number, reason=None) -> None:
        args = ["gh", "issue", "close", str(number)]
        if reason:
            args += ["--reason", reason]
        self.run(args)
