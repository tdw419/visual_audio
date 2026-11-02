# RECEIPT_BM801_RGB — B10: the two single-pixel rows that honoured the phase but not the mode

Verdict: **GREEN, landed as a route.** `OffsetFrame.rgb()` and `OffsetFrame.lum()` now sit
behind the same `drops()` gate the cell accessor has always had, both rows read `yes` on
B8's `mode` column, and no receipt in the ladder moved.

## What was found, in B8's words

`AUDIT_BM801_SAMPLING_PATHS.md` (landed `a5bf99e3`) measured 22 sampling paths on the two
offset frames. After B9 closed the blind `OriginFrame.lum()` row, two rows still carried a
NO cell:

| row | dx | dy | ko | jo | mode | gate caller |
|---|---|---|---|---|---|---|
| `OffsetFrame.lum()` (OffsetFrame) | yes | yes | n/a | n/a | NO (wraps) | nothing |
| `OffsetFrame.rgb()` (OffsetFrame) | yes | yes | n/a | n/a | NO (wraps) | nothing |

`NO (wraps)` on 6 of 45 samples each: the body was its own
`(r*ch+y+dy) % h * w + (c*cw+x+dx) % w` arithmetic and a `self.pixels` slice, so on a
`clamp` view a single-pixel read returned the **opposite edge of the capture** -- a byte the
camera never showed -- where `raw_cell()`, which tests `drops()` first, returned the
sentinel for the same cell. B8's finding 2 named the shape: "the B6 defect at single-pixel
scale. B6 fixed the whole-file writer, not the two accessors the writer was written in terms
of." Inside `bm801_align.py` the two rules never met, which is why B6 and B7 came out clean
and why these rows survived every gate that ran before the audit; outside it, any caller
that takes one pixel rather than one cell got an invented edge.

## The choice, and the equality that made it

The item allowed a route or a declared sentinel. `SENTINEL` was chosen, not by taste, but
because B9's leg 6 established an equality this class has to keep:

```python
def rgb(self, r, c, x, y):
    if self.drops(r, c):
        return SENTINEL
    y0, x0 = (r * self.ch + y + self.dy) % self.h, (c * self.cw + x + self.dx) % self.w
    px = (y0 * self.w + x0) * 3
    return self.pixels[px:px + 3]

def lum(self, r, c, x, y):
    return sum(self.rgb(r, c, x, y))
```

`sum(SENTINEL)` is the zero that `raw_cell()`, `grid()` and `plane()` already return for a
dropped cell. A `raise` or a second, different sentinel would have made `rgb()` and
`raw_cell()` disagree about one pixel of a dropped cell and broken that equality on the
class this item touches. Net of docstrings: `bm801_align.py` +24/-5, two functions, and
`raw_cell()` untouched -- it already sampled through `rgb()` behind its own `drops()` test,
so the fix put the single-pixel path under the gate the cell path always had rather than
adding a third rule.

## What the fix moved, and why that was the real work

Three legs had to be re-pointed, not one, and each was a prediction the item's own bullet
did not make:

- **B9's leg 7** existed specifically to keep this row open (`OffsetFrame.lum` invents on 5
  of 5 out-of-frame cells under `clamp`). It flipped sign on the same five cells and gained
  two hand-derived controls so it cannot pass vacuously: `0` inventing, `rgb == SENTINEL` on
  5, plus 0 wrap samples and 0 clamp in-frame samples off-model.
- **B8's leg 2** could not keep asserting a `NO (wraps)` against live code that no longer
  produces it. It now reads the verdict out of the landed table at `a5bf99e3` via `git show`
  -- so the before-side is a fact in git, not a number in prose -- and requires the fresh
  probe to answer `yes` on `dx`, `dy` and `mode`. Leg 10 needed the same treatment for both
  rows at once, and gained a two-way cross-check: the `nothing` column is compared against
  probe results computed by a different walk, so a gate column cannot be quietly edited into
  a name.
- **B8's leg 9** forbade `self.pixels[...]` outside the two modules. A gate that keeps a
  superseded formula in evidence has to index the bytes itself, so the leg now permits
  exactly one such helper per gate file, requires its name to start with `old_`, and prints
  it. Deleting the evidence or dropping the invariant were both available and both wrong;
  the exemption is narrower than what it exempts.

**The line numbers of `bm801_align.py` moved and every citation to them is now short.**
B10 inserts 12 lines at `OffsetFrame.rgb()` and 7 more at `OffsetFrame.lum()`, so
`raw_cell` 99->111, `OffsetFrame.grid` 111->123, `OffsetFrame.lum` 125->137, `OriginFrame`
136->155, and every def from `OriginFrame.plane` on by +19 (`OriginFrame.raw_cell`
165->184, `OriginFrame.lum` 168->187, `materialize` 297->316).
`RECEIPT_BM801_MATERIALIZE.md:5-9`, `RECEIPT_BM801_CLAMP.md`,
`RECEIPT_BM801_GRID.md:6` and `RECEIPT_BM801_LUM.md:39` all cite pre-B10 lines, and
`doc_ref_audit.py` still prints `170 line citations (0 stale)`, because its line check
is range-only -- it can tell a citation that runs off the end of the file from one that
points at the right neighbourhood, and nothing more. Those receipts are point-in-time
records and are left as written; this paragraph is the correction.

## Runs

`rung8/run_bm801_rgb_gate.py`, 11 legs (0-10), one `-snapshot` beacon boot, host-side
otherwise, no writes to any medium; the keep-out disk is named once, in a constant, and leg 0
checks that. Capture `85efe386fd8c6703`, 720x400, cell 9x16, anchor phase `(3,5)`, the clamp
view dropping 104 of 2000 cells.

Pre-landing, with leg 9's nested gates skipped by `BM10_SKIP_OLDER`: `RESULT 10/10 legs
pass`.

- leg 1, the row: the pre-fix pair invents a non-sentinel byte on 5 of 5 sampled
  out-of-frame cells (both `rgb` and `lum`); post-fix, 0.
- leg 2, all 104 dropped cells: `rgb` invents 0, `lum` invents 0, `raw_cell` differs from the
  all-sentinel list on 0, while the untouched base formula `vga.Frame.lum` still invents on
  104 of them.
- leg 3, one rule: a cell rebuilt from `rgb()` equals `raw_cell()` (12 comparisons), a `lum()`
  rebuild equals `grid()` (12), `plane()` equals the carve it is built under (12), and each
  equals the hand-derived pixel (60 + 60 samples) -- 0 disagreements.
- leg 4, `wrap` cannot move: 0 of 2000 cells x 5 sampled pixels differ from the pre-fix
  formula, on either accessor.
- leg 5, the sentinel does not leak: 1896 in-frame clamp cells still equal the pre-fix bytes,
  and 29 read all-zero on the sampled pixels -- a leaked sentinel would have shown as far
  more.
- leg 6, the blindness stays a measurement: the pre-fix arithmetic, kept live in this file,
  invents on **102 of 104** dropped cells where the fixed accessor invents on 0. Run 1 of
  this gate asked pixel `(0,0)` alone and found 0 differences, which was not the fix working
  but this capture being black along its bottom row and right column where the wrapped read
  lands; the honest count is per cell over the whole pixel set, and the two cells that still
  do not invent are inside `pre_inv`'s complement, unprint and unnamed.
- leg 7, the acceptance test: the audit's own probe, run from this gate on the fixed pair,
  reads `yes` on `dx`, `dy` and `mode` for both rows, `45/45` samples with 23 / 17 / 6 of
  them moved.
- leg 8, B10 is not B9: an `OriginFrame` under clamp still invents 0 on its own 104 dropped
  cells, and the two `lum` definitions remain distinct.
- leg 10, the channel: the displaced capture still aligns to `(6,11)`/`(24,79)` and reads
  `'BM801-RECEIPT-OK>0123456789ABCDEF'` at 33/33 distance-0 cells; the uncorrected frame
  reads garbage at 0/33.

The item's price clause -- no existing receipt may move -- was measured, not assumed:

- `rung8/run_bm801_grid_gate.py` (B7), `BM7_SKIP_OLDER=1`: `RESULT 9/9 legs pass`, rc=0.
- `rung8/run_bm801_lum_gate.py` (B9), no skip flags: `RESULT 10/11 legs pass`, the single
  FAIL being its leg 9, which nests B8's audit and reads `run_bm801_path_audit_gate.py rc=1
  RESULT 11/12` -- the audit's own leg 0 compares ten sources against their `HEAD` blobs, so
  it is RED by construction until this item's commit exists. Every other leg passed, and
  legs 7/8 carry the flipped assertions above.
- `rung8/run_bm801_path_audit_gate.py` (B8), no skip flags: `RESULT 12/13 legs pass`, again
  only leg 0, printing
  `drifted=['bm801_align.py(edited)', 'run_bm801_lum_gate.py(edited)', 'run_bm801_rgb_gate.py(not-in-HEAD)']`.
  Legs 2, 9, 10, 11 and 12 all passed pre-commit: `NO rows at a5bf99e3=OffsetFrame.lum()
  OffsetFrame.rgb() OriginFrame.lum() | fresh rows with a NO/MIXED cell=0`,
  `pixel rows with no gate caller=4`, `table says nothing for=4`, `generated block == the
  landed block`, indexers `[('bm801_align.py', 1), ('bm801_vga.py', 1),
  ('run_bm801_rgb_gate.py', 1)]` with owners `['rgb']`.
- B4's clamp gate and B6's materialize gate, both nested from this gate's leg 9, and the
  atlas/resolve path: unchanged.

`python3 doc_ref_audit.py` after the code and prose landed on disk but before this receipt
existed: `93 prose files (83 fully resolving), 930 backticked path tokens checked, 170 line
citations (0 stale), 2 skipped, 70 cited files outside HEAD (159 citations)`,
`POINTER_STATUS=REVIEW (14)`. Against B9's landed reading (`924` tokens, `69` outside `HEAD`,
`REVIEW (13)`) that is `+6` tokens, one more file outside `HEAD` -- this gate, on disk and
not yet committed -- and the fourteenth `REVIEW` pointer is this file, cited from the audit
doc one line before it was written. Measured again with this file on disk: `94 prose files
(85 fully resolving), 940 tokens, 173 line citations (0 stale), 71 cited files outside HEAD
(161 citations)`, `POINTER_STATUS=REVIEW (13)` -- the forward reference dissolved when the
file it named arrived, and the `+3` citations are this receipt's own line-number paragraph.
With the ROADMAP bullet in place too: `94 prose files (85 fully resolving), 944 tokens, 174
line citations (0 stale), 71 cited files outside HEAD (163 citations)`, still `REVIEW (13)`.
`0 stale` in every one of those readings is the range-only check and does not mean the
citations are true; see that paragraph.

## What this does not establish

- Every `yes` is one 720x400 beacon capture at one anchor `(3,5)`/`(2,7)`, 6-9 cells and 5
  pixel positions. A measurement, not a proof over all inputs.
- Both offset frames still expose a public single-pixel read that is slow by construction
  (`lum()` is now a full `rgb()` call, and `raw_cell()` builds a 144-element list per cell);
  the census that says nobody production-calls them is what makes that acceptable, and it is
  B8's column, not this receipt's assertion.
- The `mode` column now reads `yes` on both classes. The remaining `nothing` cells belong to
  the `vga.Frame` base rows -- nothing calls `Frame.lum`/`grid`/`plane`/`ink_profile`
  unbound -- and to `physical()`, which is B11 and is still open.
- `wrap` is proven unmoved on the sampled pixel set, not over the frame.

## Landed (2026-09-26, commit `f74acfb4`)

Every number below is from the run against the committed tree, and carries its skip flag.

- `python3 rung8/run_bm801_rgb_gate.py`, no skip flags, all 11 legs: `RESULT 11/11 legs
  pass`, rc=0. Its leg 9 reports the four gates it nests as `run_bm801_clamp_gate.py rc=0
  RESULT 9/9 | run_bm801_grid_gate.py rc=0 RESULT 9/9 | run_bm801_lum_gate.py rc=0 RESULT
  10/10 | run_bm801_materialize_gate.py rc=0 RESULT 9/9` -- the lum figure is 10/10 because
  nesting sets `BM9_SKIP_OLDER`, which drops its leg 9. Same capture, same geometry, same
  digits as the pre-landing run above.
- `python3 rung8/run_bm801_path_audit_gate.py`, no skip flags, all 13 legs: `RESULT 13/13
  legs pass`, rc=0, with leg 0 now `drifted=none`, leg 3 `at a5bf99e3: dx=NO (blind) dy=NO
  (blind) ko=NO (blind) jo=NO (blind) mode=NO (wraps) | measured now: dx=yes dy=yes ko=yes
  jo=yes mode=yes`, leg 11 `generated block == the landed block`, and leg 12 nesting B7 at
  `9/9`.
- `python3 rung8/run_bm801_lum_gate.py`, no skip flags, all 11 legs: `RESULT 11/11 legs
  pass`, rc=0. Its pre-commit run was `10/11` and the single FAIL was its leg 9's nested
  audit at `11/12` -- that RED was this item's own uncommitted state, measured and named
  rather than explained away, and it is now gone.
- B8's leg 2 and leg 9 read the fixed pair from `HEAD`: `at a5bf99e3: lum mode=NO (wraps) rgb
  mode=NO (wraps) | measured now: lum dx=yes mode=yes (45/45 ... 6 of them moved) | rgb
  dx=yes mode=yes`, and indexers `[('bm801_align.py', 1), ('bm801_vga.py', 1),
  ('run_bm801_rgb_gate.py', 1)]` with `bm801_align.py owners: ['rgb']`.

One thing the pre-commit section above predicted and the landed run confirmed rather than
moved: `raw_cell()` is unchanged in the committed diff, so the cell accessor's type and
verdicts are B6's, and the only functions B10 touched are `OffsetFrame.rgb` and
`OffsetFrame.lum`. An earlier run of this item routed `raw_cell()`'s in-frame branch at
`rgb()`'s `bytes` slice instead of re-wrapping it in a `tuple`; that changed the per-pixel
type of an accessor this item was not asked to touch and was reverted before the commit. No
gate noticed the difference -- four legs compared the two accessors through normalization --
which is the same no-consumer shape B8's last column exists to name.

`python3 doc_ref_audit.py` against the committed tree, with this section appended: `94 prose
files (85 fully resolving), 944 backticked path tokens checked, 174 line citations (0 stale),
2 skipped, 69 cited files outside HEAD (156 citations)`, `POINTER_STATUS=REVIEW (13)`. Two of
the 71 files-outside-`HEAD` named in the pre-landing reading above are this gate and this
receipt, and they are gone now.
