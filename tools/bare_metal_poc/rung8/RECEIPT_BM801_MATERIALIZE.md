# RECEIPT_BM801_MATERIALIZE — B6: the written file obeys the mode that authorized it

**Date:** three full gate runs, 2026-09-24T00:59Z (pre-fix, RED) to 01:47:50Z (final), from
`date -u` and the run-dir timestamps; a legs-only pass at 01:36:35Z–01:37:53Z.
**Files:** `rung8/bm801_align.py` (modified: `SENTINEL` at `rung8/bm801_align.py:46`,
`OffsetFrame.drops` at `rung8/bm801_align.py:85`, `OffsetFrame.rgb` at
`rung8/bm801_align.py:94`, `OffsetFrame.raw_cell` at `rung8/bm801_align.py:99`,
`OriginFrame.raw_cell` at `rung8/bm801_align.py:151`, `materialize()` at
`rung8/bm801_align.py:267`), `rung8/run_bm801_materialize_gate.py` (new, 9 legs).
**Depends on:** B4's aligner and its gate (`rung8/run_bm801_align_gate.py`), B5's clamp mode and its
gate (`rung8/run_bm801_clamp_gate.py`) — both re-run unchanged by leg 8 — and B4's boot capture
path `rung8/bm801_capture.py`.
**One qemu boot of the beacon image, `-snapshot`, host-side pixels after that. No hardware, no
substrate, no ruling.** `ubuntu_desktop_pxc1_v3_selfhost/` was not opened; `pristine_reverify.sh`
was not run.

## Why this exists

B5 named the hole itself, as a non-goal: "`materialize()` still writes a **wrapped** view … anyone
who writes a corrected view out and reads it with `rung8/bm801_vga.py` is still reading invented
edge pixels." The code fact behind that sentence is narrower and is what makes this builder work
rather than documentation: `materialize()` did not call `plane()` at all. It hand-rolled its own
indices with `% view.h` and `% view.w` on the pixel buffer, so it was **wrap-only no matter which
mode decided the view**, while every reader, scorer and atlas in the tree goes through
`OffsetFrame.plane` — the one place the clamp rule lives. The aligner's decision and the aligner's
output were produced by two different sampling rules, and a clamp report carrying
`cells_edge_invented=0` could authorize a file full of opposite-edge pixels.

Leg 1 measured exactly that before anything was fixed: at one phase, the clamp view's file and the
wrap view's file were **byte-identical** (0 differing bytes), while the independent rebuild
disagreed with the clamp file by 9,771 bytes over 80 out-of-frame cells. That is the defect stated
as a number.

## What changed

One accessor, used by both the mask and the bytes.

- `OffsetFrame.drops(r, c)` (`rung8/bm801_align.py:85`) is now the single statement of "this mode
  refuses to sample this cell". `plane()` branches on it (`rung8/bm801_align.py:89`), exactly as it
  did before, and so does `raw_cell()`.
- `raw_cell()` (`rung8/bm801_align.py:99`) returns the cell's RGB row-major: `SENTINEL`
  (`rung8/bm801_align.py:46`, `(0, 0, 0)`) for a dropped cell — the same all-zero content
  `plane()` already returns for a dropped cell, so file and mask agree — and otherwise the bytes
  from `rgb()`, which is the offset walk `lum()` always used.
- `materialize()` (`rung8/bm801_align.py:267`) samples **only** through `view.raw_cell()` and
  `view.drops()`. It no longer touches `% h` / `% w` itself, and it no longer reads `view.ko` /
  `view.jo`: registration is `OriginFrame.raw_cell()`'s job
  (`rung8/bm801_align.py:151`), which is the same delegation `plane()` already used.
- It **reports** rather than refusing, in two places: the return value is now
  `{'dst', 'mode', 'cells', 'sentinelled'}`, and when anything was sentinelled the PPM header
  carries `# bm801 materialize: mode=clamp sentinelled=80 of 2000 cells`, so the artifact cannot be
  separated from the claim that produced it. `rung8/bm801_vga.py` is unmodified and parses the
  commented file (leg 2 re-parses it at 720x400). Both callers that existed before
  (`rung8/run_bm801_align_gate.py`, two sites) ignore the return value.
- `mode` still defaults to `wrap` (`rung8/bm801_align.py:70`), and a wrap view writes the same bytes
  it always wrote — leg 1 asserts that against the rebuild, not against itself.

## What the gate measured

9 legs, one boot, `rc=0` (`RESULT 9/9 legs pass`, 9 m 40 s at 2026-09-24T01:47:50Z). Frame 720x400,
cell 9x16, so one cell is 144 bytes and `sample_cells()` is 1,744 cells of 2,000.

- **Leg 1 — the mode binds the file.** After the fix the clamp file is byte-identical to a rebuild
  made cell-by-cell from the PPM header arithmetic alone (0 cells, 0 bytes), the wrap file is
  byte-identical to the same rebuild under wrap, and the two files differ on 79 of the 80
  out-of-frame cells — **not 80**, and 9,771 bytes — **not 11,520** (see the refuted predictions).
- **Leg 2 — the count is real and travels with the file.** `sentinelled=80` in the report, 80 from
  the header arithmetic, 80 from the rebuild, 0 under wrap, and the clamp file's own header names it.
- **Leg 3 — the in-frame path costs nothing.** An identity clamp view writes the source bytes back
  exactly and reads `BM801-RECEIPT-OK>0123456789ABCDEF` at distance 0 on all 33 cells. And
  `roll(0,2)` re-bound to clamp at the geometry WRAP was accepted at — 80 cells sentinelled,
  including 16 calibration-block cells — **still reads the receipt exact, 33/33, 0 blank**.
  Sentinelling a row the message is not on does not damage the reader.
- **Leg 4 — an off-edge row no longer decodes.** On B5's 33-invented-cell case the clamp file yields
  **33 blank cells and distance 0 of 0**; the wrap file from the same phase hands the reader
  **32 plausible glyphs**. Those glyphs are the calibration row's own codes
  (`\x01\x02…\x0f?????…`), which is the whole defect in one line: wrap produced confident evidence
  from pixels the capture never had. clamp may destroy a false read; it never invents one.
- **Leg 5 — bound to the mode, not to a new default.** One phase (0,14), one origin (24,0), two
  modes: every dropped cell is all-zero in the clamp file, and **no in-frame cell differs at all**
  (0 of 1,920), so the fix cannot reach outside the region the capture genuinely lacks.
- **Leg 6 — no caller changed behaviour.** Default mode still `wrap`; the identity write is
  byte-identical; the wrap output equals what the header-arithmetic rebuild says wrap always was.
- **Leg 7 — the price, and the item's number reproduced.** In the report, on B5's `roll(0,34)`:
  clamp **1629/1744** at phase (0,0) with 0 invented cells, wrap **1692/1744** at phase (0,14) with
  80 — the pair the item predicted, exactly. In the file, at one fixed geometry:
  clamp-materialized **1676/1744** against wrap-materialized **1744/1744**, a price of **68 cells**
  out of 80 sentinelled (12 of them matched no glyph either way). There is still no mode that gets a
  high score and the truth; B5 said so and this makes it true of the bytes too.
- **Leg 8 — the older gates.** `rung8/run_bm801_align_gate.py` `RESULT 9/9 legs pass` rc=0 and
  `rung8/run_bm801_clamp_gate.py` `RESULT 9/9 legs pass` rc=0, both as subprocesses over one boot of
  their own. The census that leg prints: B4's gate has **2** `materialize(` call sites, B5's clamp
  gate has **0** — so on the clamp gate specifically, legs 1-7 of this file are the only thing
  holding the new rule, exactly the fact the item asked to be recorded if it turned out so.

## Predictions this gate refuted, kept rather than deleted

Five. All five were this item's own reasoning, not the code's.

1. **"The two files differ on exactly the N invented cells, N x 144 bytes."** Run 1 measured 9,771
   bytes, not 11,520, and 79 cells, not 80 — a cell the capture paints black already *is* the
   sentinel, so it cannot differ. Counts are taken cell-wise now, with the already-black cells
   named and each verified all-zero in the wrap file, instead of asserting an equality that black
   pixels break.
2. **"A clamp view whose message row is in-frame still reads the receipt."** Assumed of the phase
   CLAMP chose; measured 30/33 and garbled. Clamp costs evidence and its winner moves
   (B5's own finding, inherited here), so legs 3, 4, 5 and 7 take the geometry WRAP was accepted at
   and re-bind only the mode — which is also what makes leg 5 a mode test rather than a score test.
3. **"No displaced frame the aligner accepts keeps the 16x16 atlas intact."** The leg originally
   required `atlas_drop == 0` and found no candidate in eight tries; the best available is
   `msg_drop=0` with `atlas_drop=16`, measured and now reported rather than required away. A clamp
   file that drops the block's edge row is honest about never having had it, and the message still
   reads (leg 3b), but a plain `Frame` over such a file has 16 fewer atlas codes.
4. **"The wrap-materialized edge row returns the message."** Run 1 measured 32 distance-0 cells
   reading the block's own control glyphs. Refuted, and the refutation IS the defect: 32
   confident, wrong cells from invented pixels. Leg 4's assertion was rewritten to the measured
   contrast (0 plausible under clamp, 32 under wrap), not to the guess.
5. **"1629 vs 1692 is what the materialized files score."** Run 2's leg 7 scored each mode at its own
   chosen phase: clamp wins `roll(0,34)` at phase (0,0) where nothing falls off the edge, so
   `sentinelled=0` and both files scored 65/1744 — a vacuous pair that would have passed an
   inequality-free leg. 1629/1692 is the *report's* `exact_offblock` pair (it reproduced exactly);
   the *file's* price at a fixed geometry is 1676 vs 1744. Leg 7 now measures both, separately.

## Line-citation drift this change caused, and does not repair

Inserting lines into `rung8/bm801_align.py` moved every existing citation into it. Nine point at
different text now, all in `rung8/RECEIPT_BM801_ALIGN.md` and `rung8/RECEIPT_BM801_CLAMP.md`. Per
this lane's rule 6 the old records stay as written; the mapping is here instead:

| cited as | pointed at | now lives at |
|---|---|---|
| `rung8/bm801_align.py:76` | `def in_frame` | :80 |
| `rung8/bm801_align.py:92` | `def edge_invented` | :117 |
| `rung8/bm801_align.py:110` | `self.dx, self.dy, self.ko, self.jo =` | :135 |
| `rung8/bm801_align.py:114` | `def physical` | :139 |
| `rung8/bm801_align.py:225` | `'cells_scored': reg['cells'],` | :256 |
| `rung8/bm801_align.py:236` | `def materialize` | :267 |
| `rung8/bm801_align.py:290` | `rep['declined_by_edge'] =` | :328 |
| `rung8/bm801_align.py:312` | `REPORT_KEYS =` | :350 |

Worth recording as a fact about the checker, not only about this commit: `rung8/doc_ref_audit.py`
check 2 range-checks citations and printed **0 stale** for all nine, because the lines they name
still exist — a range check cannot see that the text moved. Prose that cites this file by line
number should name the function as well as the number, which B5's receipts mostly already do.

Audit totals, measured before this file was written and again after (the counts move because the
records cite each other): 89 prose files (81 fully resolving), 849 backticked path tokens, 134 line
citations, 0 stale, 2 skipped, 68 cited files outside HEAD (154 citations),
`POINTER_STATUS=REVIEW (11)` before. After: see the `## Land` section below.

## What this does not fix

- `align()`'s decision is unchanged: clamp still **declines** rather than confirming a phase whose
  message row was invented, and `mode` is still `wrap` by default. What changed is that a file
  written from a clamped view now agrees with the report above it.
- `OriginFrame.grid()` remains inherited from `vga.Frame` and so ignores `dx`/`dy`/`ko`/`jo`. No
  reader path reaches it — `plane()` delegates to the offset frame — but `ink_profile()` on an
  `OriginFrame` would carve unshifted cells. Named, not fixed: no leg of any gate exercises it, so
  a fix here would be untested by construction.
- B5's open question stays open, and this item does not answer it: *which mode a real photograph
  should be read under* needs a capture that is not a screendump. What B6 removes is the ability to
  write a clamp result that lies about its own pixels.
- Leg 8's census is a standing warning: B5's gate never calls `materialize()`, so if someone reads
  "9/9" there as cover for the writer, they are wrong. This gate is the cover.
- Physical hardware, and anything on the substrate: not touched, not claimed.

## Reproduce

    cd tools/bare_metal_poc && python3 rung8/run_bm801_materialize_gate.py
    # 9/9, exit 0, ~9.5 min, one boot. Set BM6_SKIP_OLDER=1 for legs 0-7 only (~80 s, no nested gates).

## Land

Landed by the lane tick that ran it, 2026-09-24, one commit, paths enumerated:
`tools/bare_metal_poc/ROADMAP.md`, `tools/bare_metal_poc/rung8/bm801_align.py`,
`tools/bare_metal_poc/rung8/run_bm801_materialize_gate.py`,
`tools/bare_metal_poc/rung8/RECEIPT_BM801_MATERIALIZE.md`.

The after-totals line above this paragraph was deliberately left for here, because the measurement
has to be taken after the last prose edit and the last prose edit is the sentence that carries them.
Taken after the ROADMAP append and after this file was last written, digits only excluded:
**90 prose files (81 fully resolving), 870 backticked path tokens, 155 line citations with 0 stale,
2 skipped, 70 cited files outside HEAD (158 citations), `POINTER_STATUS=REVIEW (13)`.** Two readings
three minutes apart disagreed by one token (869 then 870) before settling; the delta is exactly the
one path this run appended to ROADMAP, verified by re-running the checker's own tokenizer over HEAD's
text and the working text (283 vs 284) — so a totals line is only as good as the instant it was read,
and this one was re-read after the append rather than inherited from the earlier sweep.
