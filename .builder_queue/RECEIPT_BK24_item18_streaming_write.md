# RECEIPT — BK-24 item 18 LANDED: streaming sys_write (worktree
# bk24-rowfix commit 1aef3eab) + gate-authoring defect fixed in L2

**Landed:** 2026-09-25 ~01:5x CDT, builder af3e62239ce2 (Glyph OS Event
Chain cron), in worktree `~/zion/worktrees/bk24-rowfix` (branch
bk24/rowfix-32col), commit **1aef3eab** — on top of this lane's own
BK-24 commits 976b1c50 (ticket) and 78a8c6a5 (root cause). Main-tree
HEAD at landing: 741cb1cd. Supply: CLAIM QUEUE ROUND 9 item 18 ("THIS
UNBLOCKS EVERYTHING ELSE").

## What landed (5 files, +457/−63)

1. `tools/glyph_gpt/libc_runtime.py` — the streaming write tile
   (`_gh23_sys_write_tile`): branch-free append. Loads cursor mem[724],
   stores the 4 buf words through it (ring [768, 832)), stores
   cursor+4 back, mirrors 718..721 as last-flush window (the BK-11-era
   guard stays live, never weakened). ABI 0x0002001A -> 0x0002001B;
   bake fixed at cols_instrs=32 (root-cause receipt
   RECEIPT_BK24_ROOT_CAUSE_row_truncation.md — 70 :pc_ entries past the
   8-bit row ceiling at 16 cols).
2. `tests/test_gh23_libc_runtime.py` — the C libc's `write()` becomes a
   chunking wrapper (16-byte frames, `_write_frame` ECALL shim, one
   ECALL per frame — POSIX length semantics restored in C, the only
   place the length exists, since the engine marshals only a7/a0/a1);
   loader assembles at the same cols_instrs=32.
3. `tools/glyph_gpt/baker.py` — libc prologue seeds cursor 724 = 768;
   status tail id 26 -> 27.
4. `tools/glyph_gpt/autoatlas.py` — cols_instrs plumbing for the wider
   bake.
5. `tests/test_bk24_streaming_write.py` — the gate (5 legs, force-added
   past .gitignore:101): L1 structural pins (toolchain-free), L2
   two-flush survival, L3 write(1,buf,64) byte-exact (the item's GREEN
   line), L4 GH-23 C-suite regression, L5 ABI word bump.

## Gate-authoring defect found and fixed IN this landing (not a guard
## weakened — a leg that could never pass as written)

The original L2 asserted `ring[8:16] == b"BBBBBBBB"` — ring **BYTES**
8..16, which are words 770..771: the zero-pad tail of frame 1. The
leg's own docstring said "flush 2 at ring words 768..771, 772..775".
Measured machine truth (two independent processes, probe_flush2.py +
probe_flush2_b.py, identical): flush 1 frame = `AAAAAAAA` + 8 zero
bytes at words 768..771; flush 2 frame = `BBBBBBBB` + 8 zero bytes at
words 772..775; cursor = 0x308 = 768+8. That IS the landed frame ABI
(the wrapper flushes the whole 16-byte window per flush; the tile has
no length). The amended L2 pins the frame ABI explicitly (data + pad
for both frames) and still discriminates — RED below.

## Evidence

RED (amended L2 core assertion against the OLD fixed-window tile —
probe_bk24_red_leg.py, old tile monkeypatched at its definition module
`glyph_gpt.libc_runtime`, full 300k-instruction run):
```
old tile: halted True faulted False exit = 0 cursor = 0x300
ring[0:32] = b'\x00'*32
window 718..721 = b'BBBBBBBB\x00\x00\x00\x00\x00\x00\x00\x00'
RED CONFIRMED: amended L2 core assertion (ring[16:24] == b'BBBBBBBB')
FAILS under the old fixed-window tile — the gate discriminates.
```
(That ring dump is also the original item-18 defect reproduced: flush 1
LOST entirely under the fixed-window tile.)

GREEN (this tree, streaming tile):
```
tests/test_bk24_streaming_write.py  5 passed in 4.67s
tests/test_gh23_libc_runtime.py     5 passed in 5.16s
```

## What the PASS does NOT prove

- Ring saturation past 64 words (256 stream bytes): documented non-goal;
  every landed fixture flushes ≤ 4 frames. A wrap/clip tile needs a
  stamped branch — the defect class this tile deliberately avoids.
- WGSL twin: nothing spatial in this change (host-bake ABI only).
- Main-tree landing: this commit lives in the worktree. The main tree
  holds a STALE 16-col partial copy of the same idea (dirty files,
  mtimes 01:32:28, 6 min before this tick's start) whose gh23 suite is
  measurably RED (3 failed, ABI word still 0x1A, stdout empty on the
  C-suite). Do NOT merge that copy over this one; the next tick should
  re-verify and land THIS branch's tree into main.

## Discipline notes

- Parallel-session rule exercised: main-tree dirty BK-24 files were
  detected mid-tick; diffed against the worktree (16-col vs 32-col,
  ABI 0x1A vs 0x1B) before any landing decision; main tree untouched.
- Pre-commit parity gate: no engine/WGSL files touched (host-bake
  toolchain + tests only) — Pillar 2.3 skip is correct, not evaded.
