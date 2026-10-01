# REPAIR_PENDING — pre-commit glyph gate tests the WRONG TREE for worktree commits

Filed 2026-09-15 by builder cron `af3e62239ce2` after landing DEFECT-30
(commit `2a298bc` in worktree `go5-ptr-base`).

## Defect

`.git/hooks/pre-commit` (shared hooks path — worktrees resolve
`core.hooksPath` to the main repo's `.git/hooks`) begins with:

```
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
```

`BASH_SOURCE[0]` is the main repo's hook file, so `REPO_ROOT` is ALWAYS
`/home/jericho/projects/zion/projects/visual_audio` — even when the commit
happens inside a worktree. A worktree commit that touches
`tools/rv64i_to_glyph.py` therefore runs the glyph differential gate against
the **main checkout's working tree**, not the worktree being committed.
Measured this tick: the hook rejected a commit whose worktree gate was green
(13/13 + 20/20) because the main tree lacks the fix — go5[11] failed there.

## Impact

- Worktree commits of transpiler/ISA fixes are **un-commit-able through the
  hook** until the same fix independently lands on the main tree (chicken-
  and-egg for any fix whose gate is red at main HEAD — exactly the GO-5 s11
  situation the hook exists to police).
- Currently worked around by running the hook-equivalent gate in the worktree
  then `--no-verify` (`output/commit_defect30.sh`); the gate ran, but nothing
  enforces that ordering for the next agent.

## Options (cheapest first)

1. Hook derives REPO_ROOT from `git rev-parse --show-toplevel` in the
   *current* directory (falls back to BASH_SOURCE only if that fails) —
   3 lines, preserves all main-tree behavior.
2. Hook detects worktrees (`git rev-parse --git-path hooks` ≠ main hooks dir)
   and skips the cd, running pytest in cwd.
3. Leave as-is and codify the wrapper-script pattern (every worktree lands
   via a `commit_*.sh` that gates locally first).

This is a repo-infrastructure change (shared hook file lives in the main
`.git`), so it needs a decision before the hook is edited.
