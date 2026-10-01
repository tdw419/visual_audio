#!/usr/bin/env python3
"""Appends the 2026-09-13 14:2x tick's near-escalation entry (cron af3e62239ce2). Append-only."""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
TARGET = ROOT / "NEAR_ESCALATIONS.md"

ENTRY = """
## 2026-09-13 14:2x CDT — Almost asked: file the writer-named measurement and wait, or fix it?
**Decided instead:** the measurement is mechanical and bounded, so the loop ran it *and* carried it to
the point where the ticket's own classification changes — building the fix in worktree isolation and
proving it RED→GREEN with one instrument on both trees — **without landing it** on
`glyph-transpiler-autoloop`.
**Reason:** DEFECT-23 is design-gated (Jericho's seat), but its option 1 was filed as "a bake-layout
fix with no engine change and no fault-policy decision". The probe turned that conditional into a
fact: the arming loop `:__g18_ptloop` contradicts its own documented contract (`baker.py:5198-5209`)
by writing a MOV as an uninitialised `ADD`, and the "garbage PTEs" are that accumulator's tail. That
revises the *classification* (typo, not policy), which is the loop's job; the *landing* stays
Jericho's, which is why the fix sits on a branch and the main branch only carries evidence.
**Outcome:** main `1f41fe7` (probe + ticket update + 6 raw evidence artifacts, no core files);
branch `defect23-ptloop-init` @ `6d8ab81` (one-line fix + `tests/test_defect23_pt_identity.py`).
Measured: same command/file/instrument, peak RSS 2,350,292 kB → 243,204 kB (9.7×), wall 9.04 s →
3.85 s, 14/14 green on both trees. Honest residual: the engine's low-byte-only PTE validity test is
untouched (option 2 has no known live trigger now, but still guards the class).
**Discipline hazard found and recovered (no work lost):** `git stash` is **repo-global across
worktrees**. A `git stash push <file>` in a linked worktree silently no-ops when that file is already
committed, and the following `git stash pop` then applies the stack's top entry — here an unrelated
`emulator-v2-baseline` stash, leaving `UU` on three files. Recovered with `git reset --hard HEAD`
in the worktree only; the stash stack was verified intact (5 entries, top entry unchanged); the RED
was then produced by `git checkout 6d8ab81~1 -- tools/glyph_gpt/baker.py` instead of stashing.
**Rule for the loop:** never use `git stash` inside a linked worktree on this repo — check out the
pre-change file by path instead.
"""


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    if "Almost asked: file the writer-named measurement and wait" in text:
        print("entry already present; skipping")
        return 0
    with TARGET.open("a", encoding="utf-8") as fh:
        fh.write(ENTRY)
    print(f"appended {len(ENTRY)} chars to {TARGET.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
