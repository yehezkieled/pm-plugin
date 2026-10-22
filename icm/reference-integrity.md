# Reference integrity: the move-safety gate

Adapted from icm-architect's `references/reference-integrity.md` (MIT, © 2026 Jake Van Clief; see [LICENSE](LICENSE)).

The walk test proves the result is navigable; it does not prove the move was safe. Before proposing a move, find what points at the file. Apparent disuse is not proof.

## What to search

`pm.py refs OLD=NEW [OLD=NEW ...]` searches the repository's tracked and untracked files and prints, for each path:

1. **In-repo referrers**: lines that name the path, and Markdown links or `@` imports that resolve to it, including relative `../` links, which break when folders regroup even if nothing outside is involved.
2. **Symlinks** into the path: moving the target orphans the link.
3. **Mentions by name only** (the file name without its folder), to check by hand.
4. **The destination**, compared case-folded (below).

It cannot see **external consumers**: other repositories, deploy scripts, CI, cron, issue trackers, agent configs that hardcode a path. Ask the owner and record what they name on the migration map. A file with a live referrer is held, or moved only if every referrer is updated in the same change. It is not Dead until this comes back clean.

## Destination collision

Before any copy or rename, check whether the destination exists when compared case-folded. macOS and Windows file systems ignore case, so a rename to `CONTEXT.md` silently overwrites an existing `context.md`, and a parity check after the copy cannot catch it: by then the destination is the source. `pm.py refs` exits with an error when a destination is taken.

## Move, verify, then remove

1. Tracked file: `git mv OLD NEW`, then `git diff --cached -M100% --name-status` must list it as `R100` (identical content). Untracked file: copy it, compare `sha256sum` of both, and only then delete the original.
2. Update every referrer in the same change; leave a link where the old copy lived if anything outside still points there.
3. Edit the moved file's content only after the parity check.

## Durability

Confirm the files are tracked by git, or backed up, before reorganizing them. Rearranging files that live only in a temporary or ignored folder protects nothing.
