# {Project name}

{One sentence: what this repository is and what leaves it.} Shape: {shape or shapes}. Product overview: [README.md](README.md).

This file routes; the facts live in the files it links to. Where each kind of knowledge goes: `/pm:help`.

## Where things go

Before creating any file, find its kind here and put it in that place. No row fits: ask once, recommend a place, and add the row in the same change. Nothing else goes at the root. A place that exists is a link, to its folder's `README.md` when it has one; a place with no file yet stays a plain path until its first file lands. `out/` is never a link: it is gitignored.

| Kind of thing | Place | Rule |
| --- | --- | --- |
| Tasks: what is being done and what is next | `docs/pm/items/` | `/pm:plan` adds them and `/pm:work` claims them; never made by hand |
| {kind, from icm/shapes.md: the spine rows, then the shape's rows} | [`{path}`]({path}) | {rule} |

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
| doing any project work (code, data, a deliverable) | `/pm:work`: it adds the item with `/pm:plan` if it is not on the board and hands it to a worker that claims it first |
| asking what is in flight or next | `/pm:status` |
| {another common task} | [`{the file or folder that answers it}`]({the file or folder that answers it}) |

## Every session

- Run: `{command}`. Test: `{command}`.
- Claim an item before changing code or data; keep the requester's words verbatim in the item.
