# {Project name}

{One sentence: what this repository is and what leaves it.} Shape: {shape or shapes}. Product overview: [README.md](README.md).

This file routes; the facts live in the files it points at. Where each kind of knowledge goes: `/pm:help`.

## Where things go

Before creating any file, find its kind here and put it in that place. No row fits: ask once, recommend a place, and add the row in the same change. Nothing else goes at the root.

| Kind of thing | Place | Rule |
| --- | --- | --- |
| Tasks: what is being done and what is next | `docs/pm/items/` | `/pm:plan` adds them and `/pm:work` claims them; never made by hand |
| {kind, from icm/shapes.md: the spine rows, then the shape's rows} | `{path}` | {rule} |

## Route by task

| If you are | Go to |
| --- | --- |
| adding or tracking work | `/pm:plan` |
| doing any project work (code, data, a deliverable) | `/pm:work`: it adds the item with `/pm:plan` if it is not on the board and hands it to a worker that claims it first |
| asking what is in flight or next | `/pm:status` |
| {another common task} | `{the file or folder that answers it}` |

## Every session

- Run: `{command}`. Test: `{command}`.
- Claim an item before changing code or data; keep the requester's words verbatim in the item.
