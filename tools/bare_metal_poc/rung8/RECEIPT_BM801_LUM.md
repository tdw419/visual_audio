# RECEIPT_BM801_LUM — B9: `OriginFrame.lum()`, the one row B8's audit found blind

Verdict: **GREEN, landed as an override.** The row is fixed, the blindness is still
measured, and the two gates this moved are both back to their pre-item numbers.

## What was found, in B8's words

`AUDIT_BM801_SAMPLING_PATHS.md` (landed `a5bf99e3`) measured 22 sampling paths on the two
offset frames. 21 of them honour every parameter they can see. One reaches `self.pixels`
and reads none of the five:

| row | dx | dy | ko | jo | mode | gate caller |
|---|---|---|---|---|---|---|
| `OriginFrame.lum()` (Frame) | NO (blind) | NO (blind) | NO (blind) | NO (blind) | NO (wraps) | nothing |

21 of 45 samples unchanged where the bytes differ on `dx`, 17 on `dy`, 7 on `ko`, 6 on
`jo`, 4 on `mode`. It resolved to `vga.Frame.lum`, which addresses
`(r*ch+y)*w + c*cw+x`: no phase, no relabelling, no mode. And its gate column said
`nothing` -- the only `.lum(` call site in the ladder is `bm801_vga.py:64`, inside
`Frame.grid`, which B7 overrode on both classes. B7 closed this accessor's last caller
and left it standing.

## The choice, and the census that made it

Fix or cut. An override routes the pixel through `raw_cell()`, the gate `plane()` and
`grid()` already use, so `drops()` is honoured by the same act; a refusal (`raise`)
breaks `vga.Frame.grid` usable-as-an-unbound-call, which B7's leg 1 depends on. The
production census is one call site, in `bm801_vga.py`, reached from an overridden method
-- so nothing runs this accessor today, which is why it survived four gates that each
printed 9/9, and why an untested fix and a tested one looked identical until B8 counted
callers.

```python
def lum(self, r, c, x, y):
    ...
    return sum(self.raw_cell(r, c)[y * self.cw + x])
```

`rung8/bm801_align.py:168-179`, one `return` and a docstring. The cost is a whole-cell
carve per pixel, and it is nobody's hot path: both classes override `grid()`, so the only
production caller of `lum()` is a method that is no longer called.

## What the fix moved, and why that was the real work

`Frame.grid` is built on `self.lum`. B7's blind side was
`vga.Frame.grid(view, r, c)`, an unbound call on an `OriginFrame` -- blind only because
the view inherited `lum()`. The moment `lum` honours the offsets, that call honours them
too, and B7's legs 1-4 lose their RED to a change that touched nothing in the base class.
B8's queue text said an override "keeps `vga.Frame.grid` usable as an unbound call on an
`OriginFrame`". Usable: yes. Blind: no. That half-error is the finding.

- B7's `blind_grid` now takes a plain `vga.Frame` over the same bytes -- the same
  formula, still live code, and no longer a fact about inheritance. Its docstring says so
  and B9's leg 3 measures the claim: 0 of 5 sampled cells disagree between
  `vga.Frame.grid(view, ...)` and the view's own honouring carve, and 0 agree between the
  base-`Frame` form and it.
- B7's whole leg output is **digit-for-digit identical** before and after, on three runs of
  the same capture (`85efe386fd8c6703`, geometry `(6,11,24,79)`, 160/160 blind cells,
  0/160 at zero, 84/84 label-differing, 104 invented clamp cells, 33/33 message cells).
  Between its pre-fix run and its landed run the only lines that differ are leg 7's two:
  the census now separates a gate caller from a production one
  (`other gates {'run_bm801_lum_gate.py': 5}, non-gate elsewhere none`) and reports
  `bm801_align.py`'s surviving `grid()` call at line 182 instead of 169, because the
  override is 13 lines long. Every value in legs 0-6 and 8 is unchanged.
- B8's audit moved in four legs: leg 1 now separates the two `lum` rows the other way
  (`OriginFrame.lum<- OriginFrame`), leg 3 asserts the flip against the table *at
  `a5bf99e3`* rather than against prose, leg 4 requires a gate to call `.lum(`, and leg 0
  stopped raising `CalledProcessError` when a `SOURCES` file is on disk but not yet in
  `HEAD` -- which is exactly what the item adding it looks like mid-run. The landed table
  is regenerated; leg 11 re-emits it and reports `generated block == the landed block`.

## Runs

`rung8/run_bm801_lum_gate.py`, 11 legs (0-10), one `-snapshot` boot, host-side otherwise,
no writes to any medium, `ubuntu_desktop_pxc1_v3_selfhost/` named once in a constant (leg
0 checks that). The pre-landing run, with leg 9's two nested gates skipped by
`BM9_SKIP_OLDER`: `RESULT 10/10 legs pass`.

- leg 1 reproduces B8's five digits from the base formula: `dx=21/45 dy=17/45 ko=7/45
  jo=6/45 mode=4/45`. The permanent RED, and it does not need the defect to exist.
- leg 2, the override: blind `0` on all five columns, `45/45` equal to the hand-derived
  pixel on all five.
- leg 4, the mode: of 104 dropped cells the override invents 0 non-zero pixels and the
  base formula invents 104.
- leg 6, one rule: rebuilding a cell out of `lum()` equals `grid()` on both classes'
  modes, and equals the hand-derived carve from the PPM bytes.
- leg 7, B10 is not this item: on 5 out-of-frame cells `OffsetFrame.lum` under `clamp`
  still invents 5 -- asserted, so B9 cannot be mistaken for having finished that row.
- leg 8, the census: production callers `{'bm801_vga.py': [64]}`, unchanged at one; gate
  callers `{'run_bm801_lum_gate.py': 8}`.
- leg 10, the channel: the displaced capture still aligns to `(6,11)`/`(24,79)` and reads
  `'BM801-RECEIPT-OK>0123456789ABCDEF'` at 33/33 distance-0 cells.

`rung8/run_bm801_path_audit_gate.py` pre-landing, `BM8_SKIP_OLDER=1`: `RESULT 11/12 legs
pass`, the single FAIL leg 0, listing exactly `['bm801_align.py(edited)',
'run_bm801_grid_gate.py(edited)', 'run_bm801_lum_gate.py(not-in-HEAD)']` -- leg 0
compares disk to `HEAD`, so it is RED by construction until the commit exists.
`rung8/run_bm801_grid_gate.py` with `BM7_SKIP_OLDER=1`: `RESULT 9/9 legs pass`, rc=0.
The landed-state re-run of all three, nested legs included, is recorded in the
`## B9 DONE` block of `.builder_queue/BM000_LADDER_LANE_STATE.md`.

`python3 doc_ref_audit.py` before this receipt existed: `92 prose files (82 fully
resolving), 913 backticked path tokens checked, 164 line citations (0 stale), 2 skipped,
70 cited files outside HEAD (158 citations)`, `POINTER_STATUS=REVIEW (14)`. The
fourteenth is this file, cited from the audit doc one line earlier than it was written.
Against B8's landing (`908` tokens, `REVIEW (13)`) the delta is `+5` tokens and `+1` line
citation from the amended prose, and one fewer file outside `HEAD`, because B8's two
deliverables are now committed.

## What this does not establish

- Every `yes` is one 720x400 capture at one anchor `(3,5)`/`(2,7)`, 9 cells, 5 pixel
  positions. A measurement, not a proof over all inputs.
- The override is slow by construction -- a 128-pixel carve per pixel -- and is justified
  by the census that says nobody calls it. If a caller appears, that trade reopens.
- It fixes the *relabelling* class. `OffsetFrame.lum()`/`.rgb()` still wrap under `clamp`
  (B10), and `raw_cell()`/`physical()` still have no gate call site (B11). Both rows are
  in the landed table with their verdicts, and B9's leg 7 asserts the first.

## Landed (2026-09-25, commit `5ab0b0ef`)

The deferral above, discharged. Both numbers are from the run, not from the writing.

- `python3 rung8/run_bm801_lum_gate.py`, no skip flags, all 11 legs: `RESULT 11/11 legs
  pass`, rc=0. Its leg 9 reports the two gates it nests as `run_bm801_grid_gate.py rc=0
  RESULT 9/9 legs pass | run_bm801_path_audit_gate.py rc=0 RESULT 12/12 legs pass`.
- `python3 rung8/run_bm801_path_audit_gate.py`, no skip flags, all 13 legs: `RESULT 13/13
  legs pass`, rc=0, with leg 0 now `drifted=none`, leg 3 printing
  `at a5bf99e3: dx=NO (blind) ... mode=NO (wraps) | measured now: dx=yes dy=yes ko=yes
  jo=yes mode=yes`, leg 11 `generated block == the landed block`, and leg 12 nesting B7 at
  `9/9`.

**B9's own ROADMAP bullet mis-quoted this, and the mis-quote is the lesson:** it says
`13/13` *nested from B8's audit*, and a nested audit is `12/12` because nesting sets
`BM8_SKIP_OLDER`, which drops leg 12. The audit prints `13/13` standalone. A leg count is
meaningful only with its skip flag attached -- the correction is appended to that bullet in
the same commit as this section.

`python3 doc_ref_audit.py` measured at `5ab0b0ef`, before this section and the ROADMAP
correction were written: `93 prose files (84 fully resolving), 924
backticked path tokens checked, 170 line citations (0 stale), 2 skipped, 69 cited files
outside HEAD (156 citations)`, `POINTER_STATUS=REVIEW (13)`. Against the pre-landing
reading above that is `+11` tokens and `+6` line citations from this receipt and the
amended prose, two fewer files outside `HEAD` and `156` (was `158`) citations for them --
this file and its gate are tracked now -- and `REVIEW` back to `13` because the
forward reference dissolved when the file it named arrived.
