# pm plugin for Claude Code

Project management for coding projects of any size: a new repo, an old one, a small script, a fork.
Work is kept as markdown the project owns, readable by people and agents alike.

```
milestone -> epic -> ticket -> subtask

docs/pm/roadmap.md            milestones in order, plus Backlog
docs/pm/epics/Exx-slug.md     goal, ticket list, dependency Flow (drawn by the plugin)
docs/pm/tickets/Txxx-slug.md  what, why, acceptance, subtasks, plan, notes, proposed changes
docs/pm/decisions.md          decisions a future reader would otherwise have to guess
CONTEXT.md  "## pm" block     how this project works: flow, gates, check command, mirror
```

GitHub is a one-way mirror (milestone, epic issue with task list, ticket issue). The markdown is the source.

## Skills

| Skill | Does | Input | Output |
| --- | --- | --- | --- |
| `/pm:init` | interview, then create docs/pm and the pm block | `[--quick]` | files, board, next steps |
| `/pm:plan` | add a milestone, epic, ticket, bug, or idea; apply proposed changes | `kind [title or Txxx]` | thin ticket file (`ready: no`), redrawn Flow |
| `/pm:grill` | question one ticket until What, Why and Acceptance are settled | `[Txxx or Exx]` | ticket marked `ready: yes` |
| `/pm:work` | one ticket end to end: claim, plan, tests first, gates, two review agents, PR | `[Txxx] [--routine]` | branch or PR, report |
| `/pm:status` | the board, problems, what is ready | `[--validate]` | one page |
| `/pm:retro` | close a milestone, record keep and change | `[Mx]` | Retro block, next milestone |
| `/pm:audit` | find bugs and debt, file tickets with evidence | `[path] [--cap N] [--routine]` | tickets, report |
| `/pm:help` | cheat sheet, or one skill in detail | `[skill]` | text |

Hooks: at session start one board line is printed when the project has docs/pm. Before an Edit, Write or Bash call on a ticket branch (`txxx-slug`), the plan gate blocks code edits until the ticket is grilled (`ready: yes`) and its `## Plan` is written and, for `plan: required`, carries `approved: yes` (docs and markdown are always allowed), and while a Bug ticket says `tests: frozen` it blocks test files too. At stop, a warning (never a block) when code changed but no ticket file did.

## Agents

Two read-only subagents ship in `agents/` and run together at the review gate of `/pm:work`: `pm:verifier` runs the check command and tests every acceptance line against the diff; `pm:reviewer` hunts bugs, edge cases and security holes. Both fix nothing and default to Sonnet; the pm block's `review_model` line changes the default, and an interactive session asks per ticket at the plan step whether Sonnet or Opus reviews this one.

## Routines

Each project turns its routines on in the pm block (`routines: work=on audit=on`) and puts two commands on a timer of its own. Two recipes ship in `templates/`: `routine-cron.txt` for a machine where Claude Code is logged in, and `routine-github-actions.yml` for CI. The audit files tickets, the work routine opens pull requests, and neither merges.

## Design page

`docs/blueprint.html` is the design of the plugin: the system, the decisions behind it, the flow of every skill, what each skill takes and returns, scenarios, and how it was verified. Open it in a browser. The diagrams load one script from a CDN; everything else works offline.

## Install

From a local checkout:

```bash
claude plugin marketplace add /path/to/pm-plugin
claude plugin install pm@pm-plugin
```

For development, load it straight from the folder: `claude --plugin-dir /path/to/pm-plugin`.

## The pm block

```
## pm
flow: branch-pr        # branch-pr | branch-local | direct
host: github           # github | gitlab | other | none
mirror: on             # one-way mirror to the host; needs gh
merge: ask             # ask | auto
gates: tdd, checks, review, docs
check: npm run lint && npm test
milestone: M1
tools: python3=yes gh=yes
routines: work=off audit=off
auto_cap: 1
review_model: sonnet   # model for the two review agents
```

## Scripts

Standard library Python 3 and small bash. Nothing to install.

```
scripts/pm.py       board | line | next | flow | claim | release | ready | freeze | unfreeze | dismiss | set | validate | backup | next-id | config | new | sync
scripts/pm_sync.py  one-way mirror through adapters/github.py (gh command line)
scripts/pm_detect.sh  facts about a repo for /pm:init
scripts/doctor.sh   which tools are present
```

Without python3 the skills do the same work by hand from `templates/`.

## Rules the plugin keeps

- No dates, deadlines, or effort numbers anywhere. Milestones are ordered versions. `tests/test_no_time_tracking.py` fails the build if the plugin's own text breaks this.
- No ticket without a testable acceptance line, and no work on a ticket before it is grilled: `/pm:plan` writes tickets thin (`ready: no`), `/pm:grill` runs the questioning round and marks them ready, `/pm:work` and the plan gate refuse the rest. Blocked tickets are grilled once their dependency lands; one grilled early is flagged on the board. Tickets written before the flag existed count as ready.
- An agent never widens a ticket. Extra ideas go under "Proposed changes" for a person to accept, edit, or reject.
- Claims are committed before branching, so several agents can work in their own worktrees without colliding.
- A `plan: required` ticket puts an interactive session into plan mode: read-only until you approve the plan at the exit, and the approved plan is copied into the ticket.
- A Bug ticket freezes its test files once the reproducing test is committed. A wrong test is unfrozen by a person, with the reason kept in the ticket.
- A finding nobody wants is dismissed with a reason, never deleted.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

## Evals

Unit tests check the scripts. Evals check the behaviour: a throwaway repo, a plain-English prompt, a model with the plugin loaded, and a set of checks on what came out (which skill fired, which files changed, what was committed). They live in `evals/` and write to `evals/results/`, which git ignores.

```bash
python3 evals/harness.py haiku                        # every headless scenario on one model
python3 evals/harness.py sonnet plan_bug_implicit     # one scenario
python3 evals/interactive.py opus work_plan_mode      # a real interactive session, driven through tmux
PM_EVAL_REPO=you/throwaway python3 evals/livepr.py setup   # then: run <model> <ask|auto> <Txxx>
python3 evals/matrix.py                               # the table, latest result per cell
```

Run them after changing a skill, a hook, or an agent, and when a new model appears. They call models, so they take minutes, not seconds. When `claude plugin eval` is available on your account the same scenarios can move into its case format.

## Credits

The questioning style in `/pm:init` and `/pm:grill` borrows the essence of Matt Pocock's grill-me skill
(https://github.com/mattpocock/skills, MIT): one question at a time, a recommended answer with each,
look things up instead of asking, stop when understanding is shared. Nothing from it is installed as a dependency.
