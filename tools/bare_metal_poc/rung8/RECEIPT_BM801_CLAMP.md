# RECEIPT_BM801_CLAMP — B5: the frame edge as a measured behaviour

**Date:** four gate runs, 2026-09-22T03:03Z to 03:45Z, from `date -u` at each end of each run.
**Files:** `rung8/bm801_align.py` (modified: `OffsetFrame.in_frame` at `rung8/bm801_align.py:76`,
`edge_invented` at `rung8/bm801_align.py:92`, the edge rule at `rung8/bm801_align.py:290`),
`rung8/run_bm801_clamp_gate.py` (new, 9 legs).
**Depends on:** B4's aligner and its gate (`rung8/run_bm801_align_gate.py`), which leg 7 re-runs
unchanged, and B4's boot capture path `rung8/bm801_capture.py`.
**One qemu boot, `-snapshot`, host-side pixels after that. No hardware, no substrate, no ruling.**

## Why this exists

B4's own receipt said the quiet part: `OffsetFrame` samples `mod h` / `mod w`, so a displaced frame
*reuses the opposite edge*, and the aligner admitted it "wraps and so invents edge pixels". A
screendump has every pixel, so that is harmless here. A photograph of a monitor does not, and a
phase that wins by reading the top of the screen off the bottom is not a receipt — it is the reader
agreeing with itself. B5 adds `mode='clamp'`, which samples only in-frame pixels, and measures what
that costs instead of asserting it.

Clamping does one thing: it **shortens the usable-cell set, never fills it**.
`OriginFrame.physical` (`rung8/bm801_align.py:114`) still maps through `% ROWS` / `% COLS` because
the calibration block really is where the header says it is; `in_frame` asks whether the carve of a
cell lies inside the capture, and `plane` returns a flat plane when it does not. Wrap returns the
opposite edge for the same cell. Same geometry, two different claims about what the camera saw.

## What was predicted before measuring, and the three predictions that were wrong

The item asked for: (i) a y-shift bigger than one cell pitch where the two modes must disagree,
(ii) a bad capture still refused, (iii) the report carrying the number of wrapped samples a chosen
phase leaned on. Each got a leg, and each leg states its prediction before it measures.
`rung8/run_bm801_clamp_gate.py` exits 0 only at 9/9.

**Run 1 (03:03:14Z–03:07:59Z): 7/9, legs 3 and 4 FAILED.**

- Leg 3 predicted *"clamp still finds the true phase, just with a lower score"*. Measured: at
  `roll(0,34)` wrap chose phase `(0,14)` and scored 1692/1744 leaning on 80 invented cells; clamp
  chose phase `(0,0)` and scored 1629/1744 with 0 invented. Same at `roll(9,34)` (1674 vs 1613).
  **Refuted: clamping does not lower confidence in the answer, it changes the answer** — it moves the
  winning phase away from the edge, because at the edge there is nothing left to match. v2 wrote
  that up and passes.
- Leg 4 predicted a decline-on-edge at `roll(0,4)` read on row 24. Measured `msg_inv=0`:
  registration put the block at ko=24, which moved row 24 onto a physical row the capture *does*
  have. The construction never reached the phenomenon. v2 tried `roll(0,2)`, measured `msg_inv=0`
  again for the same reason.

**Run 2 (03:13:32Z–03:18:21Z): 7/9, legs 4 and 8 FAILED.** Leg 6 predicted *"the two modes do not
report the same score"* on a lost-strip capture. Measured 1504/1744 for **both** modes at the same
phase — the strip wrap reaches for is the blacked-out region, which matches no glyph either way.
v2 keeps the agreement and draws the actual conclusion: **identical scores with a nonzero invented
count are precisely why the count has to be in the report.** "Aligned" and "aligned on pixels this
capture does not contain" score the same and are not the same claim. Leg 8 failed because leg 4 had
not produced its case, which is the correct way for it to fail.

**Run 3 (03:29:11Z–03:34:33Z): 7/9, legs 4 and 8 FAILED — but leg 4 finally hit the thing.**
`roll(0,2)` read at row 0 gave both modes `msg_cells_edge_invented=33`: wrap applied it
(distance-0 16 → 32) and clamp refused. That is the whole point of the item, on real pixels. What
broke is the *reason field*: clamp's decline read `increase-only: ...`, because the score guard ran
first and the edge never got named. Two more measurements from that run: `roll(8,34)` at row 20 gave
`msg_inv=1` for wrap and 0 for clamp, and a row is **all-in or all-out** — `in_frame` depends on the
row only, so an invented count strictly between 0 and 33 is impossible for a bottom-edge loss.

## The one code decision the measurements forced

`align()` judges the edge rule **before** the score, not as a veto on an otherwise accepted phase
(`rung8/bm801_align.py:290`). Run 3 is the evidence: both rules applied to the same report and the
operator saw only the weaker one. A clamped read whose message row needs pixels the capture does not
have is inadmissible whatever its score, and the report says so:

    roll_0_2_row0  wrap : phase=(0, 14) origin=(24, 0) row= 0 msg_inv=33 d0n=16 d0c=32 applied=True
                 clamp: phase=(0, 14) origin=(24, 0) msg_inv=33 d0n=16 d0c= 0 applied=False
                        declined=<clamp: 33 of the 33 message-row cells fall where this capture has
                        no pixels, so the (0,14) phase is not confirmable>

**Run 4 (03:39:51Z–03:45:10Z): 9/9, rc=0.** `RESULT 9/9 legs pass`, and leg 7 re-ran B4's 9-leg
gate as a subprocess: `rc=0 RESULT 9/9 legs pass` — wrap is still the default and B3/B4's rules are
untouched.

## What each leg measured (run 4)

| leg | claim | measured |
| --- | --- | --- |
| 0 both-modes-inert | neither mode writes | frame sha256 `85efe386fd8c6703` before and after both `align()` calls |
| 1 edge-arithmetic | a 32-px y-shift is bigger than the 16-px pitch | 2 rows out, 160 of 1744 cells not `in_frame`; clamp flat there; identical in-frame planes; wrap instead found 159 glyphs in pixels that are not in the picture |
| 2 shortens-never-fills | `exact_clamp <= exact_wrap`, and usable = total − invented | 7 phases, incl. `(0,32)`: wrap 1712, clamp 1584, invented 160, usable 1584 of 1744. Clamp never exceeded wrap and never counted an out-of-frame cell |
| 3 large-shift-disagreement | v2 | 2 rolls: clamp lower AND differently-phased on each; wrap leaned on 80 invented cells, clamp on 0 |
| 4 decline-not-confirm | v4 | 1 candidate reached invented message cells (`roll_0_2_row0`, 33 of 33); clamp declined naming the edge; wrap applied the same read clamp refused |
| 5 bad-capture-still-refused | item leg (ii) | 4 bad captures (`713x400`, `720x390`, `40x32`, a junk PPM) refused identically in both modes, `applied=False`, no exception raised |
| 6 report-count-is-real | item leg (iii), v2 | both modes 1504/1744 at phase `(0,2)` while reporting 80 invented cells — and 80 is what the header arithmetic gives independently (`rung8/run_bm801_clamp_gate.py:69`, which never calls the aligner) |
| 7 b4-regression | B4 unchanged | `rc=0 RESULT 9/9 legs pass` from a subprocess |
| 8 hard-rules-hold | both B3/B4 rules + the new one | 9 reports; 0 increase-only violations; 0 clamp reports applied on invented message cells; declined-on-edge seen on `['roll_0_2_row0']`, so the leg is not vacuous |

## Report contract

`corrected()` now emits `mode`, `cells_scored`, `cells_edge_invented` and
`msg_cells_edge_invented` (`rung8/bm801_align.py:225`); `REPORT_KEYS`
(`rung8/bm801_align.py:312`) leads with `mode` so a printout cannot be read without saying which
sampling rule produced it. `align()` sets `declined_by_edge` on every clamp report, not just the ones
it flipped.

## What this does not fix

- `materialize()` (`rung8/bm801_align.py:236`) still writes a **wrapped** view. Clamp is a decision
  rule, not a pixel pipeline; the materialised frame is B4's and unchanged. Anyone who writes a
  corrected view out and reads it with `rung8/bm801_vga.py` is still reading invented edge pixels, and
  should read `cells_edge_invented` first.
- Clamp costs evidence: on `roll(0,34)` the honest score is 1629, not 1692. There is no mode that
  gets a high score and the truth.
- `mode` defaults to `wrap`, so nothing downstream changed behaviour. B6+ has to decide which one a
  real photograph is read under, and that decision needs a capture that is not a screendump —
  i.e. the nested-writer probe, not this lane.
- The 33-invented-cell case at run 3 came from a **cyclic roll**, where wrap's answer was in fact
  right (the content really is at the other edge). On a lost-strip capture both modes score the same
  and only the invented count separates them (leg 6). clamp's value here is that it *declines and
  says why*; it is not, on these synthetic frames, more accurate.

## Reproduce

    cd tools/bare_metal_poc && python3 rung8/run_bm801_clamp_gate.py   # 9/9, exit 0, ~5.5 min, one boot
