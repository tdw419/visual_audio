# RECEIPT — BK-24 falsifier rounds 7-8: ROOT CAUSE — the write() wrapper pushes 70 pointer-table entries past the 8-bit packed-PC row field

**Tick:** 2026-09-25 ~00:5x-01:1x CDT, builder af3e62239ce2 (Glyph OS Event
Chain cron). Extends DEFECT_BK24_GH23_comparator_return_20260924.md and
falsifier rounds 1-6. Tree: HEAD 976b1c50 + the parallel lane's uncommitted
BK-24 files (untouched; measurement-only tick).
**Probes:** probe_bk24_seed_diff.py (round 7), probe_bk24_packed_cells.py
(round 7b), probe_bk24_deltastep.py (round 8).

## Measured chain (GREEN trivial vs RED new, same fixture, same bake path)

1. Round 7: the RED unit has **44 MORE `:pc_` pointer-table entries** than
   GREEN (443 vs 319; the extra 44 are contiguous RV32 addresses
   0x4fc..0x5a8 — exactly the wrapper's write() tail region). qsort moves
   0x400 → 0x4b0.
2. Round 7b: every packed seed equals packed(cell) — the LOADER's seeding
   is self-consistent; the per-entry cell deltas vary (row quantization),
   as expected for different-assemble layouts. Not the defect.
3. Round 8: **GREEN max entry = spliced cell 3883 = row 242 (< 256);
   RED max = cell 4344 = row 271 (> 256), with 70 entries at row > 255.**
   The packed-PC format is (row<<16)|col in a 24-bit pixel word with an
   **8-bit row field** — the exact truncation documented as DEFECT-7 in
   the GH-23 record ("rows 0..255"; bake moved to cols_instrs=16 to keep
   the TASK under 256 rows). The wrapper's 111 extra glyph instructions
   push 70 :pc_ entries past row 255, where their packed row field
   TRUNCATES.

## Why the symptom is the measured one (consistent, not load-bearing)

The truncated entries live in the wrapper's OWN auipc/jalr call sites —
but jalr-through-ra lowers to CALLR, and EVERY indirect call resolves
through table[wi] = packed PC. With rows > 255 the stored row wraps
(271→15 etc.), so the first use of an affected entry CALLRs into the
wrong row — matching the ticket's step trace: comparator calls work,
then a RET/call pair lands at a bogus cell (206 / SUPER pad) and the run
wandered to fault 32820. (Mechanism attribution beyond the measured
truncation is fenced speculation; the truncation itself is measured.)

## Why old libc was green: its unit ended at row 242 — under the limit.
The wrapper adds ~111 instructions (its own body + 44 :pc_ entries at
4-byte stride ≈ 176 bytes ≈ 11 cells per row band), pushing the unit
past the 256-row packed-PC ceiling. This is the SAME defect class as
DEFECT-7 (row truncation), resurfacing at a new threshold via unit TEXT
GROWTH, not via the tile, BSS, codegen, size-shift, frame shape, call
sites, or auipc (all eliminated rounds 1-6).

## Fix direction (NOT attempted — worktree-isolated, engine file)

The 24-bit pixel word cannot hold row 271; options, cheapest first:
(a) cols_instrs=32 for the libc bake + loader (halves rows; both must
    move together — the loader pins cols_instrs=16 to match the bake);
(b) re-base the :pc_ packed format to store a FLAT CELL (12 bits fits
    4095 cells) instead of (row,col) — engine JMPR decode change, larger
    blast radius;
(c) cap unit size with an assert at splice time ("spliced rows must be
    < 256") so the failure is loud instead of silent truncation.
This is a skeleton-sign-off-adjacent change to the LOCKED loader/bake
constant pair (libc_runtime.py asserts the same arithmetic the loader
pins) — filing options here per the contract, not landing.

## What this does NOT prove

- The exact runtime step where a truncated entry is consumed is inferred
  from the ticket's trace, not re-traced in this round (fenced).
- No fix landed; rv64i_to_glyph.py / libc_runtime.py / baker.py are
  LOCKED-surface files and the tree carries the parallel lane's work.
- WGSL twin: none for this path; floors: no rate claims; single host.
