# RECEIPT_BM801_DECAY — where the receipt reader stops being trustworthy

**Date:** 2026-09-21T21:13Z. Third and last host-side piece of `TASK_BM801`:
`RECEIPT_BM801_CHANNEL.md` built the reader, `RECEIPT_BM801_WRITE_VERIFY.md`
guards the medium it will be read from, and this measures the one thing neither
covers — **what happens to the reader when the capture is not a clean
screendump**, which is the case on any real box.

`rung8/bm801_reader_decay.py` — one boot, one clean frame, then five
degradation sweeps on the pixels: per-channel noise, contrast collapse,
resolution loss (bilinear down and back up, so the grid survives), a whole-frame
sub-cell shift, and an off-grid crop. ~2 min, `python3
rung8/bm801_reader_decay.py`.

## Headline: the reader has no graceful-degradation zone, and that is the finding

**Accept a beacon only when every cell matches its own atlas entry exactly.**
Under that rule, across 25 degraded levels: **13 accepted, 0 of them wrong**,
**8 levels misread**, **1 level right-but-declined** (noise ±96, which read the
message correctly at worst-cell distance 10). A receipt that declines costs a
re-look. A receipt that lies costs the run.

The two statistics people reach for **do not separate right from wrong here**:

```
separation by raw distance : wrong reads 8..39, correct reads 0..10
separation by runner-up gap: wrong reads 0..2, correct reads 0..1
```

Both ranges overlap, so "small distance but not zero" is not a doubt signal — a
correct read can sit at 10 while a wrong one sits at 8, and a correct one can
carry the same zero runner-up margin as a wrong one. What *is* clean is the
zero-vs-nonzero cut: **no level misread with all cells at distance 0**. That is
the criterion the five per-sweep legs score, and it is the reason the tool
reports `worst_dist` per level rather than collapsing it to a verdict.

Per-mode, what actually failed and how:

| knob | where it broke | failure direction |
|---|---|---|
| noise | correct with distance 0 to ±64; ±96 correct at distance 10 → declined | false rejection only |
| contrast | CONFIRMED at distance 0 all the way to 0.05 of original levels | nothing: per-cell adaptive thresholding is contrast-invariant |
| scale (resolution) | first misread at 0.5 (19/33 cells), worst distance 39, 5 tied cells | loud |
| shift (grid misalignment) | first misread at **1 pixel** (2 cells, distance 8, no ties) | the quietest failure, and the one a real capture will hit |
| crop (off-grid size) | refused at parse, `cell 8x15 too small` | refusal |

**Shift is the live risk**: a one-pixel horizontal offset misreads, and
`pitch_is_exact()` cannot see it because a shifted 720x400 frame still divides
evenly. On a photograph the grid will never be aligned by luck. So the hardware
step is not "get a better camera", it is **align the grid before reading** — and
the beacon sector already paints the 16x16 calibration block that makes
alignment a solvable problem rather than a hope.

## One prediction was wrong, and one leg was restructured after the data

Named so nobody reads this as a gate that was tuned until it went green.

- Predicted: contrast collapse would trip the flat-cell rule, producing
  unresolved cells. Measured: it never does, because the threshold is taken
  per cell — collapsing levels preserves each cell's own min/max. `0.05` still
  reads at distance 0. The prediction was wrong in the *safe* direction and is
  recorded rather than edited out.
- The leg that is now `accept-rule` was written as `alarm-floor`, asserting that
  any wrong answer would arrive with nonzero distance **and** that any correct
  answer would arrive at distance 0. It went RED on the second clause
  (`correct reads 10..10`), which is the discovery above. The clause that was
  falsified was the false-rejection clause, and it was moved from *assertion* to
  *reported cost* — the scored assertions (`0 wrong among accepted`, `>=1 level
  breaks the reader`, `>=1 level accepted`) are the ones the data supports. A
  restructure after a RED is only honest if the RED is kept in the record; it is,
  in the table above and in this paragraph.
- Two vacuous-pass bugs surfaced while building it, both of the class this lane
  audits: `write_ppm` raised on every level so all five sweeps degraded-failed
  yet the script printed `5/5 PASS` and rc=0 — a sweep in which nothing ran
  counted as a pass; and the first `sed` fix introduced a `NameError`. Now an
  empty sweep FAILs by construction, and the `accept-rule` leg requires at least
  one accepted *and* at least one broken level, so a script that reads nothing
  and a script that stresses nothing can both no longer pass.

## Verbatim tail

```
    separation by raw distance : wrong reads 8..39, correct reads 0..10
    separation by runner-up gap: wrong reads 0..2, correct reads 0..1
--> accept-rule    predicts: the exact-match rule accepts 13 levels and 0 of them wrong; it declines 1 levels that were in fact read right, and the number that matters is the first one
    PASS accept-rule    accepted=13 (wrong among them: 0), declined-though-right=1, levels that broke the reader=8
    declined-though-right levels: [('noise', 96, 10)]
RESULT 6/6 sweeps show no silent misread
```

rc=0, six scored sweeps. Built and verified in an exported `git archive` tree
outside every repository, then copied in, so it depends on no untracked
artifact; the only files it needs are the beacon sector and the reader from
`80030f63`.
