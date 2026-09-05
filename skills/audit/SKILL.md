---
name: audit
description: Hunt through the codebase for bugs, inconsistencies, missing tests, sloppy error handling, dead code, and structure problems, and file each finding as a ticket with evidence. Never edits code. Use when the user asks to audit or scan the code, look for bugs or problems, check codebase health, find tech debt, or wants a routine that keeps filing issues. Not for showing status (pm:status) or fixing things (pm:work).
argument-hint: "[path or area] [--cap N] [--routine]"
---

# /pm:audit

Reads code, files tickets. It changes nothing outside `docs/pm/`.

Scripts: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm.py" ...`. If docs/pm is missing, say so and offer /pm:init.

## Scope and cap

- Scope: the path or area in `$ARGUMENTS`, else the whole repo minus vendored and generated folders.
- Cap: `--cap N`, else the pm block's `auto_cap`, else 3. File at most that many tickets per run; list the rest in the report as "not filed".

## What to look for

Read the pm block `check` command and run it. Then look, in this order:
1. Failing or flaky tests, and tests that assert nothing.
2. Public functions and endpoints with no test.
3. Error handling gaps: swallowed exceptions, unchecked return values, missing input validation at boundaries.
4. Security smells: secrets in code, shell commands built from user input, unsafe deserialisation, permissive defaults.
5. Duplicated logic and dead code (grep for unused functions and TODO / FIXME notes).
6. Inconsistent naming, structure that fights the repo's own conventions, docs that no longer match the code.

## Evidence

Every finding carries evidence: `file:line`, what you saw, and how to reproduce or confirm it (a command or a failing input). A finding without evidence is not filed.

Before filing, grep `docs/pm/tickets/` for the same file or topic. Add evidence to an existing ticket's `## Notes` instead of creating a duplicate.

## Filing

- Epic: the epic that owns the area when one fits; otherwise a single `Maintenance` epic in the current milestone (`pm.py new epic --title Maintenance --milestone <current> --goal "Keep the codebase healthy"`), created once.
- `pm.py new ticket --title "Bug: <short>" --epic Exx --priority <P1 for bugs and security, P2 for missing tests, P3 for tidy-ups> --confidence <high | medium | low>`, then fill What (evidence), Why, Acceptance ("a test reproduces it and passes" for bugs). Confidence: high = reproduced with a command or a failing test, medium = read in the code and understood, low = a smell worth a look. Never `--auto`: a person decides what a routine may take.
- A finding a person rejects: `pm.py dismiss Txxx --reason "..."`, never delete the file. Dismissed tickets leave the counts and the ready list; the reason stays under Notes.
- `pm.py flow Exx`, `pm.py validate`, `pm.py sync` when mirror is on.

## Report

One line per finding: ticket id or "not filed", severity, confidence, file:line, one-sentence summary. Then the board line (`pm.py line`).

## Routine mode (`--routine`)

No questions. Same cap, same evidence rule, same epic rule. End with the report only. Do not commit unless the pm block flow is `direct`; otherwise leave the new ticket files for the next person to commit.
