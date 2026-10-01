# RECEIPT_BM801_ALIGN — B4: grid alignment for the receipt reader

**Date:** measurements 2026-09-21T21:41–21:53Z, from `date -u` at each end; the receipt names the
window rather than a guess at the commit's clock.
**Files:** `rung8/bm801_align.py` (the aligner; `find_block_origin` at
`rung8/bm801_align.py:110`), `rung8/run_bm801_align_gate.py`.
**Depends on:** B1's reader (`rung8/bm801_vga.py`, `rung8/bm801_beacon.asm`) and B3's decay
measurement (`rung8/bm801_reader_decay.py`), which is what named this work.
**One qemu boot, `-snapshot`, host-side pixels after that. No hardware, no substrate.**

## Why this exists

B3 measured that a **one-pixel shift of the whole frame misreads the receipt and
`pitch_is_exact()` cannot see it** — a shifted 720x400 frame still divides evenly into 80x25.
That is the normal case for a photograph of a monitor and an impossible case for a screendump,
so the whole receipt channel is unusable off-hardware until the grid can be recovered.

## What was predicted before measuring, and what was wrong

The queue item said: *"cross-correlate the frame against the atlas block's own expected
row/column structure, or equivalently search dx,dy over one cell pitch and pick the offset that
maximises exact-match cells in the calibration block."*

**The literal instruction is vacuous, and the first implementation of my own idea was too.** Two
measurements, both before anything worked:

1. Scoring *inside* the block is meaningless: an atlas is built from the same offset it scores,
   so every cell matches itself at every phase. Any offset "maximises" it.
2. My first scorer used the sector's other redundancy — the 33-cell message painted twice, on
   rows 20 and 21, with half its characters repeated. Measured agreement on a clean frame: 1.000.
   On a frame rolled by one pixel: **1.000 at the wrong phase too**, because both copies slide
   together and their neighbour contamination is identical. A duplicated message cannot see a
   global translation. 144 phases scored, all tied. That scorer is gone.

What works is the block as reference and **everything outside it as query**: a cell off the block
at the true phase carves to a plane some block entry has; one pixel off, it picks up a column of
its neighbour's glyph and the block's neighbour is a *different* glyph from its own, so the two
planes stop agreeing. That is the same asymmetry B3 found, turned into a search.

## The second thing the item did not anticipate

A sub-pixel displacement is not only a sub-pixel displacement. Rolling the frame by 1 px is
equivalent to a phase of 8 (mod 9) **plus a whole-cell slide of one column** — so fixing the
phase relabels the block, and the reader then prints a consistent wrong string at distance 0
(`roll(1,0)` at phase-only: `'L7B0,QDBDHES,NJ=B012345678@ABCDE\x0f'`, 30 of 33 cells exact, i.e.
*high-confidence garbage*). So the aligner does two searches: sub-cell phase by exact-match count,
then the block's true origin as the 16x16 window containing the least fill. Both are reported.

## Measured facts

- Cell is 9x16 on this capture; 144 phases searched per frame; ~10.5 s per `align()` call.
- Off-block query set is 1,744 cells. On a clean frame all 1,744 match at phase (0,0) and the
  fill window finds the block at origin (0,0) with 1 fill cell inside it out of 1,679 total.
- Every one-pixel-class displacement tested recovered to **33 of 33 cells exact and the exact
  string**: rolls of (1,0) (2,0) (0,1) (0,3) (1,2) (2,7) and (4,5) from naive counts of
  16, 16, 32, 5, 16, 0 and 0 respectively.
- `roll(0,1)` — a vertical one-pixel shift — leaves **32 of 33 cells exact**. Under B3's accept
  rule that is a decline, not a read; but it is also the frame closest to lying, one wrong glyph
  in a receipt that looks otherwise perfect to anyone eyeballing it.
- A clean frame is left alone: `applied=False`, and the decline names the rule.
- Noise alone (6/16/32 per channel) never makes the search prefer a different phase — B3's
  contrast-invariance result again, from the other direction.
- **Leg 6 went RED on its first run and found a real bug**: `materialize()` wrote corrected pixels
  at a *pixel* index into a *byte* array (missing `* 3`). The in-memory view read the message
  perfectly; the file written from that same view read `' !"_!"_!%?!"...'` with 28 of 33 exact.
  A gate that only ever checks the view would have certified a correction that exists nowhere.
  Fixed, and leg 6 now also requires an identity view to write the source bytes back unchanged.

## Gate log (`rung8/run_bm801_align_gate.py`, run dir `/tmp/bm801_aligegate._cui27z7`, rc=0, 9/9)

PASS lines and numbers are copied; the `predicts:` prose is wrapped, not reworded.

```
--> 0 input-untouched      predicts: align() reads pixels only: the frame sha256 is identical after
    PASS 0 input-untouched      before=85efe386fd8c6703 after=85efe386fd8c6703
--> 1 clean-frame-decline  predicts: a correct frame must be LEFT ALONE: applied=False, phase (0,0),
                             and the uncorrected read already exact on all 33 cells
    PASS 1 clean-frame-decline  applied=False phase=(0, 0) origin=(0, 0) distance0_naive=33
--> 2 sub-pixel-recovery   predicts: each of six rolls finds phase = (-s) mod cell, registers the
                             block, and reads the message exactly (distance0 = 33)
      roll(1,0) phase=(8, 0) want_phase=(8, 0) origin=(0, 79) naive=16 corrected=33 applied=True
      roll(2,0) phase=(7, 0) want_phase=(7, 0) origin=(0, 79) naive=16 corrected=33 applied=True
      roll(0,1) phase=(0, 15) want_phase=(0, 15) origin=(24, 0) naive=32 corrected=33 applied=True
      roll(0,3) phase=(0, 13) want_phase=(0, 13) origin=(24, 0) naive=5 corrected=33 applied=True
      roll(1,2) phase=(8, 14) want_phase=(8, 14) origin=(24, 79) naive=16 corrected=33 applied=True
      roll(2,7) phase=(7, 9) want_phase=(7, 9) origin=(24, 79) naive=0 corrected=33 applied=True
    PASS 2 sub-pixel-recovery   all six rolls read exactly
--> 3 whole-cell-slide     predicts: a 9-px slide is pitch-aligned so the phase search finds (0,0);
                             only the block registration can fix it
    PASS 3 whole-cell-slide     phase=(0, 0) origin=(0, 79) fill_in_window=1 of 1679 naive=30
                             corrected=33 read='BM801-RECEIPT-OK>0123456789ABCDEF'
--> 4 increase-only        predicts: applied=True implies corrected > naive, always
    PASS 4 increase-only        no correction ever lowered the exact-cell count
--> 5 never-worse          predicts: across the 12 frames measured so far, corrected is never
                             below naive
    PASS 5 never-worse          12 frames, none made worse; 5 declined
--> 6 materialised-frame   predicts: the corrected view written out and read with the UNMODIFIED
                             bm801_vga.Frame gives the exact string too, and an identity view
                             writes the source bytes back unchanged
    PASS 6 materialised-frame   phase=(5, 11) origin=(24, 79) read='BM801-RECEIPT-OK>0123456789ABCDEF'
                             exact_cells=33/33 identity-write-byte-identical=True
--> 7 refusal              predicts: a frame whose pitch does not divide is refused outright
    PASS 7 refusal              pitch=<pitch: 713x400 is not divisible by 80x25>
                             parse=<parse: invalid literal for int() with base 10: b'not'>
--> 8 guard-fires          predicts: a frame whose two halves disagree must make the search PROPOSE
                             a nonzero phase and the guard decline it, and the report must still
                             name the phase
    PASS 8 guard-fires          phase=(7, 0) origin=(20, 79) exact_offblock=1329 (at zero 0)
                             naive=0 corrected=0 applied=False
RESULT 9/9 legs pass
```

The run before it was `RESULT 7/8` with leg 6 FAIL — the byte-stride bug, described above — and had
no leg 8. Leg 8 was added after that first run, because the eight-leg version passed leg 4 without
ever making the aligner face its own increase-only rule: all four of leg 4's frames declined at
phase (0,0), which is the guard agreeing with itself.

## What the two hard rules look like in the data

*Increase-only* is leg 8, not leg 4. On a frame whose top half is rolled and whose bottom half is
not, the search proposes phase (7,0) with a score of 1,329 against 0 at zero — the phase search is
confidently, wrongly confident — and the guard declines because the message row gains nothing. The
first version of leg 4 passed with all four frames declining at (0,0), i.e. it never made the
aligner face its own rule, so it proved nothing; leg 8 exists to face it.

*Report the offset* is every leg: the phase and the block origin are printed whether or not they
are applied, so an operator looking at a real capture sees the misalignment even when the reader
happened to survive it.

## What this does NOT establish

- Nothing about a real monitor. Every frame here is a cyclic roll of a screendump. A photograph
  has perspective, scale error and non-integer pitch — none of which this search models, and
  `materialize()` wraps, which invents edge pixels a camera would simply not have.
- The fill-window registration assumes the beacon's known layout (block 16x16 at the logical
  origin, one repeated glyph everywhere else). A sector that paints something else needs a
  different registration, though the phase search is layout-independent.
- 33 of 33 exact is still not "the machine booted as intended"; it is the same claim B1's receipt
  scoped, reached through a corrected grid rather than a clean one.
- One boot, one sector, one font. `0xDB`-style surprises (B1 found that code blank in QEMU's font)
  are not re-litigated here.
