---
name: retro
description: Close a milestone and run a short retrospective - confirm every ticket is done, record what to keep and what to change, and make the next milestone current. Use when the user says a version shipped, wants to close or finish a milestone, asks for a retro, lessons learned, or what we should change about how we work.
argument-hint: "[Mx]"
---

# /pm:retro

Milestone: `$ARGUMENTS` or the `milestone` value of the pm block (`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm.py" config`).

1. `pm.py board`. List every ticket of the milestone that is not done and not dismissed (dismissed tickets are closed; leave them). For each, ask one question: finish it first, move it to the next milestone, or move it to Backlog. Apply the answer (`pm.py set Txxx milestone=My`, or delete the ticket file and add a Backlog line).
2. Read `docs/pm/decisions.md` entries and the `## Notes` of the milestone's tickets. Pull out the recurring themes.
3. Ask three questions with the AskUserQuestion tool, one call per question, each with a suggested answer taken from what you read: what worked and should stay, what hurt, what to change in the pm block (gates, flow, merge, auto_cap) or in how tickets are written. Do not answer them yourself while a person can be asked; only a run that cannot ask (headless) takes the suggested answers.
4. Write a `Retro:` block of three to six lines under the milestone in `docs/pm/roadmap.md`: kept, changed, and any decision recorded. Add real decisions to `docs/pm/decisions.md`.
5. From what hurt, draft at most three one-line rules for CLAUDE.md: a mistake the agent repeated, a command it must always run, a convention it missed. Show them and ask (one AskUserQuestion call). On a yes append them under a `## Lessons from retros` heading in CLAUDE.md, creating the file when it is missing. A headless run writes them into the Retro block as `Proposed CLAUDE.md lines:` and leaves CLAUDE.md alone.
6. Apply the agreed changes to the pm block in CONTEXT.md.
7. Set `milestone:` in the pm block to the next milestone. If there is none, ask for the next one and create it with `pm.py new milestone`.
8. Mirror on: close the host milestone (`gh api -X PATCH repos/{owner}/{repo}/milestones/<number> -f state=closed`) and run `pm.py sync`.
9. Ask whether to commit (`pm: close Mx`).

No time words: the retro says what happened and what changes, never how long anything took or whether it was late.
