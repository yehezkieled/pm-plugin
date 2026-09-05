"""The matrix: latest result per (model, scenario) across evals/results/headless*, plus live PR and interactive runs.

usage: python3 evals/matrix.py
"""
import json
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"
MODELS = ["haiku", "sonnet", "opus", "fable"]


def load(dirs):
    rows = {}
    for d in dirs:  # later folders override earlier ones: a re-run replaces the cell it re-ran
        for f in sorted(d.glob("*/*/summary.json")):
            s = json.loads(f.read_text())
            rows[(s["model"], s["scenario"])] = dict(s, _dir=d.name)
    return rows


def cell(r):
    if not r:
        return "-"
    return f"{r['passed']}/{r['total']}" + ("" if r["passed"] == r["total"] else " FAIL")


def table(title, rows, scenarios, models=MODELS):
    print(f"\n### {title}")
    print("| scenario | " + " | ".join(models) + " |")
    print("|---|" + "---|" * len(models))
    for sc in scenarios:
        print(f"| {sc} | " + " | ".join(cell(rows.get((m, sc))) for m in models) + " |")
    for k, r in sorted(rows.items()):
        if k[1] in scenarios and r["passed"] != r["total"]:
            print(f"  FAIL {k[0]}/{k[1]}: {[c for c, v in r['checks'].items() if not v]}")


headless = load(sorted(p for p in RESULTS.glob("headless*") if p.is_dir()))
table("Headless, latest result per cell", headless, sorted({k[1] for k in headless}))

live = {}
for f in sorted((RESULTS / "livepr").glob("*/summary.json")):
    s = json.loads(f.read_text())
    live[(s["model"], f"{s['mode']} {s['ticket']}")] = s
print("\n### Live branch-pr on GitHub")
for (m, k), s in sorted(live.items()):
    print(f"- {m} {k}: {cell(s)} {[c for c, v in s['checks'].items() if not v]}")

interactive = load([RESULTS / "interactive"]) if (RESULTS / "interactive").is_dir() else {}
table("Interactive, tmux-driven sessions", interactive, sorted({k[1] for k in interactive}))

everything = list(headless.values()) + list(live.values()) + list(interactive.values())
print(f"\ncells passing: {sum(1 for r in everything if r['passed'] == r['total'])}/{len(everything)}")
