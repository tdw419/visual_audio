# AUDIT_BM801_SAMPLING_PATHS — every sampling path on the two offset frames, and what each one honours

B8's deliverable: the answer to "how many more paths ignore what the aligner decided?"
It is a table, not a fix. Nothing in `rung8/bm801_align.py` or `rung8/bm801_vga.py` was
changed to produce it, and leg 0 of the gate that regenerates it proves that by hashing all
eight audited sources -- the two modules, the capture/decay helpers and the four older
B4/B5/B6/B7 gates (the four that were audited when it landed) -- against their `HEAD` blobs.
B9 added a ninth entry, its own gate, and the same leg names the kind of drift it finds:
`bm801_align.py(edited)`, `run_bm801_grid_gate.py(edited)`, `run_bm801_lum_gate.py(not-in-HEAD)`
on the pre-landing run of this gate, which is what a landing looks like from inside: leg 0
compares the disk against `HEAD`, so it reads RED until the commit that carries them exists.

Produced by `python3 rung8/run_bm801_path_audit_gate.py` (`RESULT 13/13 legs pass`, rc=0,
including leg 12, which nests B7's grid gate at `9/9` rc=0 with that gate's own four older
legs skipped) and
`... --emit-table` (the block below) on 2026-09-25T03:28Z, at HEAD `64257fb6`, on one
beacon boot: a 720x400 capture, 9x16 cells, `screendump` sha256-prefix `85efe386fd8c6703`.
At the anchor used by the probes -- phase `(3,5)`, block origin `(2,7)` -- **104 of the
2000 cells are out-of-frame**, which is what gives the `mode` column something to bite on.

**Re-measured by B9 on 2026-09-25** (`run_bm801_lum_gate.py`, landed with this block
regenerated at the same anchor and the same capture sha): one row in the block below changed
verdict, and leg 3 of this gate is now the leg that says so -- it reads the
`OriginFrame.lum` row out of *this file at commit `a5bf99e3`* and requires the landed copy
to disagree with it. B8's findings are kept below as written, each with its correction
attached, because "the audit found a blind row" is a result and not a draft.

**Re-measured by B10 on 2026-09-26** (`rung8/run_bm801_rgb_gate.py`, landed with this block
regenerated at the same anchor and the same capture sha `85efe386fd8c6703`): the last two
`NO` rows are fixed, so the table now reads `yes` or `n/a` in every honour cell. That took
three of this gate's legs with it -- leg 2 asserts B8's `NO (wraps)` verdict for the pair out
of the landed table at `a5bf99e3` instead of out of the live measurement, leg 10 can no longer
ask fresh code for a defect so it asks history for the three rows and cross-checks the one
column still computable two ways, and leg 9 had to widen: keeping a superseded formula in
evidence means a gate file now indexes `self.pixels` itself, so direct indexers are permitted
inside an `old_*` helper and every one is printed. `SOURCES` grew a tenth entry.

## How to read it

- **Rows are mechanical.** `dir()` on `OffsetFrame` and `OriginFrame` minus dunders,
  restricted to the members this audit knows how to call (the ones with an entry in
  `ARITY`). A method added tomorrow appears here whether or not anyone remembers to list
  it. The class in parentheses is the one in the MRO that *defines* it -- which is how
  `OriginFrame.lum()` (defined on `vga.Frame`, never overridden, when B8 landed this) is
  separated from `OffsetFrame.lum()` (overridden at `bm801_align.py:125`). B9's override
  moved that row's parentheses from `(Frame)` to `(OriginFrame)` and nothing else about
  either row set; the row count is 22 on both sides of the change.
- **`reaches`** is an AST walk, and it is transitive: a row is charged `pixels` when its
  body -- or anything it hands work to, including `self._off.grid(...)` and the unbound
  `vga.Frame.plane(self, ...)` -- subscripts `self.pixels`. It is deliberately an
  over-approximation on the receiver: the honest error direction is charging a path with
  pixels it might not touch, not clearing one that does.
- **A `yes` is a measurement, not a code reading.** For each of `dx dy ko jo mode` the
  accessor is called on two frames that differ in that one parameter, from an anchor that
  already carries the others, and its value is compared against a hand-derived
  expectation computed straight from the PPM bytes (`want_px`, `want_cell`, `want_plane`,
  `want_profile`) -- never through `bm801_align`. `yes` means: equal to that expectation
  on every sample, and it moved when the bytes moved.
- **`NO (blind)`** = the bytes say the value should have changed and it did not: the
  accessor ignores that parameter. **`NO (wraps)`** is the same verdict for `mode`: under
  `clamp` it returned the opposite edge instead of the sentinel. **`MISMATCH`** = it moved
  but not to the honouring value. **`n/a`** = the parameter cannot change this value
  structurally (an `OffsetFrame` has no `ko`; `pitch_is_exact()` reads only `w`/`h`).
- **The last column is a call-site census** (`run_bm80*_gate.py` files only, AST-matched,
  and this audit's own gate excluded). It counts *direct* calls, so `plane()` reaching a
  gate through `build_atlas()` does not appear -- what it shows is which paths no leg
  touches at all, which is where a defect can live without contradicting anything.
- **The mode probes are anchored, on purpose.** Measuring `mode` at zero phase would ask
  a frame with nothing out-of-frame whether it clamps, and every accessor would pass.

<!-- TABLE BEGIN: generated by `rung8/run_bm801_path_audit_gate.py --emit-table`; do not hand-edit -->

| path | reaches | dx | dy | ko | jo | mode | reached by a pre-existing gate? |
|---|---|---|---|---|---|---|---|
| `OffsetFrame.drops()` (OffsetFrame) | derived | n/a | n/a | n/a | n/a | yes | grid, lum, materialize, physical, rgb |
| `OffsetFrame.grid()` (OffsetFrame) | pixels | yes | yes | n/a | n/a | yes | grid, lum, rgb |
| `OffsetFrame.in_frame()` (OffsetFrame) | derived | yes | yes | n/a | n/a | n/a | clamp, lum, rgb |
| `OffsetFrame.ink_profile()` (Frame) | pixels | yes | yes | n/a | n/a | yes | beacon, grid |
| `OffsetFrame.lum()` (OffsetFrame) | pixels | yes | yes | n/a | n/a | yes | lum, rgb |
| `OffsetFrame.pitch_is_exact()` (Frame) | derived | n/a | n/a | n/a | n/a | n/a | align, beacon |
| `OffsetFrame.plane()` (OffsetFrame) | pixels | yes | yes | n/a | n/a | yes | beacon, clamp, grid, lum, rgb |
| `OffsetFrame.raw_cell()` (OffsetFrame) | pixels | yes | yes | n/a | n/a | yes | rgb |
| `OffsetFrame.rgb()` (OffsetFrame) | pixels | yes | yes | n/a | n/a | yes | lum, rgb |
| `OriginFrame.drops()` (OriginFrame) | derived | n/a | n/a | n/a | n/a | yes | grid, lum, materialize, physical, rgb |
| `OriginFrame.grid()` (OriginFrame) | pixels | yes | yes | yes | yes | yes | grid, lum, rgb |
| `OriginFrame.in_frame()` (OriginFrame) | derived | yes | yes | yes | yes | n/a | clamp, lum, rgb |
| `OriginFrame.ink_profile()` (Frame) | pixels | yes | yes | n/a | n/a | yes | beacon, grid |
| `OriginFrame.lum()` (OriginFrame) | pixels | yes | yes | yes | yes | yes | lum, rgb |
| `OriginFrame.physical()` (OriginFrame) | coordinate | n/a | n/a | yes | yes | n/a | physical |
| `OriginFrame.pitch_is_exact()` (OriginFrame) | derived | n/a | n/a | n/a | n/a | n/a | align, beacon |
| `OriginFrame.plane()` (OriginFrame) | pixels | yes | yes | yes | yes | yes | beacon, clamp, grid, lum, rgb |
| `OriginFrame.raw_cell()` (OriginFrame) | pixels | yes | yes | yes | yes | yes | rgb |
| `vga.Frame.lum()` (Frame) | pixels | n/a | n/a | n/a | n/a | n/a | nothing |
| `vga.Frame.grid()` (Frame) | pixels | n/a | n/a | n/a | n/a | n/a | nothing |
| `vga.Frame.plane()` (Frame) | pixels | n/a | n/a | n/a | n/a | n/a | nothing |
| `vga.Frame.ink_profile()` (Frame) | pixels | n/a | n/a | n/a | n/a | n/a | nothing |

<!-- TABLE END -->

## What the table says

**1. One row reaches pixels and honours none of the five: `OriginFrame.lum()`.** It resolves
to `vga.Frame.lum`, which subscripts `self.pixels` at `(r*ch+y)*w + c*cw+x` -- no phase, no
relabel, no mode. Measured over 45 samples per column: `dx` blind on 21 (`+8` further samples
stationary *and* off-model), `dy` on 17, `ko` on 7, `jo` on 6, and `mode` on 4. The "off-model"
count is the same fact from the other side: its value is not the honouring carve even where a
perturbation happens not to move anything. No gate file calls `.lum(` at all -- the only call
site in the ladder is `bm801_vga.py:64`, inside `Frame.grid`, which both classes now override.
**So B7 closed the last path that reached this one, and left the accessor in place.** That is
not a contradiction of B7; it is B7's own receipt naming the row (`run_bm801_grid_gate.py`
docstring: "nothing reaches it now that `grid()` is overridden on both classes, and B8's audit
owns that row"). The audit owns it now, and it is the worst row in the table.

> **Corrected by B9 (2026-09-25).** The row is above with five `yes` cells and `lum` in its
> gate column, so everything in this finding is now a statement about *when* it was true. Two
> parts of it survive the fix, and both are asserted rather than remembered. The blindness is a
> property of the formula, not of the inheritance: `run_bm801_lum_gate.py`'s leg 1 probes
> `vga.Frame.lum` over these same bytes at this same anchor and reproduces this finding's five
> digits exactly -- 21/17/7/6 on `dx dy ko jo`, 4 on `mode`, out of 45 samples -- which is why
> that leg is the permanent RED and B7's blind side became a base `Frame`. And "no gate calls
> `.lum(`" is what made an untested fix impossible to distinguish from a tested one, so B9's
> gate exists before its override does; leg 8 of it counts the production half unchanged at one
> call site (`bm801_vga.py:64`) and the gate half at this item. `run_bm801_path_audit_gate.py`'s
> leg 3 refuses to pass unless the table *at `a5bf99e3`* still says NO on all five, so this
> paragraph cannot be softened by editing the file it sits in.


**2. Two rows honour the phase but not the mode: `OffsetFrame.lum()` and `OffsetFrame.rgb()`.**
Each read `NO (wraps)` -- 6 of 45 samples unchanged where the bytes differ, i.e. under `clamp`
they returned the opposite edge instead of the sentinel. Inside this file they cannot bite:
`raw_cell()` tests `drops()` before it ever calls `rgb()`, and that is why B6 and B7 came out
clean. But both are public methods on a clamped view, and a caller that samples one pixel
directly gets a byte the capture never showed. That is the B6 defect at single-pixel scale --
B6 fixed the whole-file writer, not the two accessors the writer was written in terms of.
**B9 changed the reach of this finding, not its content:** with `OriginFrame.lum()` routed
through `raw_cell()`, the relabelling class no longer exposes a single-pixel read that invents
an edge (its leg 4 measures 0 invented pixels on all 104 dropped cells), while `OffsetFrame`'s
two still do -- and B9's leg 7 asserts that on every out-of-frame sampled cell, so the row
cannot be quietly marked settled by the item that settled its neighbour's.

> **Closed by B10 (2026-09-26), which took this finding as its item.** Both rows now read `yes`
> on `mode`: `OffsetFrame.rgb()` returns `SENTINEL` where `drops()` is true and
> `OffsetFrame.lum()` is `sum(rgb())`, so the pair and `raw_cell()` cannot disagree about one
> pixel of a dropped cell. Measured on the same capture: the pre-fix arithmetic invents a
> non-sentinel byte on 102 of the 104 dropped cells, the fixed pair on 0, and `wrap` returns
> byte-for-byte what it returned before on all 2000 cells x 5 sampled pixels -- which is the
> price this finding implied and the item's prediction named in advance. B9's leg 7 flipped
> sign with it, on the same five out-of-frame cells, and keeps the base formula inventing on
> all 104 as its control. What did *not* change is the finding's shape: inside
> `bm801_align.py` the two rules still never met, because `raw_cell()` tested `drops()` first;
> the fix was for a caller outside it.

**3. The coverage column is a finding of its own.** `raw_cell` (both classes), `physical`,
`lum` and `rgb` have **no direct call site in any gate file**. `OriginFrame.raw_cell()` reads
`yes` on all five columns, so it is exonerated -- but exonerated *by this audit*, which is not
a leg of any gate that runs before a receipt is written. `OffsetFrame.raw_cell()` is the
accessor `materialize()` builds the artifact from (B6's whole point), and the B6 gate reaches
it only through `materialize()` and `drops()`. `OriginFrame.physical()` is the only row that
returns a coordinate rather than pixels, and note what the table shows about it: it wraps with
`% vga.ROWS` / `% vga.COLS`, so the relabelling can never *itself* put a cell out of frame --
which is why `in_frame`'s `ko`/`jo` cells read `yes` only against an anchor that already carries
a sub-cell phase.

> **Amended by B9 (2026-09-25), which is the item this finding made possible.** `lum` is off
> the list: B9's gate calls it 8 times, so the row's gate column reads `lum`, and the audit's
> leg 4 now fails if any gate stops calling it. `raw_cell` (both classes) and `physical` are
> still on it -- that is B11, unclaimed. The count the finding was about is the count that
> moved: 9 pixel-reaching rows with no gate caller when B8 landed, 7 now, and the difference
> is one accessor that nobody could previously test.

> **Amended by B10 (2026-09-26), as a side effect of fixing finding 2.** `raw_cell` is off the
> list on both classes -- B10's gate calls it directly, to assert that a cell rebuilt from
> `rgb()` equals it on both modes -- so the count this finding is about has gone 9 -> 7 -> 4,
> and the remaining four are the base-class rows, which are a different claim: `nothing` there
> means no gate calls `vga.Frame.lum`/`grid`/`plane`/`ink_profile` unbound. `physical` is still
> on it -- it returns a coordinate, not pixels, so B10 could not clear it and B11 owns it. Leg
> 10 of this gate now checks this column against the probe results, which are computed two
> different ways from two different walks, so `nothing` cannot be quietly edited into a name.

> **Closed by B11 (2026-09-26), which took the last name on this list.** `rung8/run_bm801_physical_gate.py`
> calls `physical()` directly and the row's gate column now reads `physical`, so of the five
> names this finding listed -- `raw_cell` twice, `physical`, `lum`, `rgb` -- four are cleared by
> the gates that own them and the four that remain are the `vga.Frame` base rows, which are a
> different claim, as B10's amendment said. The sentence this finding quoted -- "the relabelling
> can never *itself* put a cell out of frame", which until now was an inference from the
> modulo's presence -- is leg 4 and leg 5 of that gate: at zero sub-cell phase no offset pair
> drops any of the 2,000 cells, and at the anchor phase every pair drops exactly the 104 cells
> the hand-derived rule names, the same 104 for all eight pairs. What the modulo is worth is
> measured with it removed: the same walk without the wrap drops 416 cells at `(ko, jo) = (2, 7)`
> and all 2,000 at `(25, 80)`. `drops()` gained this gate as a caller on both classes, which is
> the honest shape of a leg that pins a coordinate by what the mode gate makes of it; the two
> `in_frame` rows are unchanged, because that leg re-derives `in_frame` by hand rather than
> calling it.

**4. What is clean.** 19 of the 22 rows read `yes` or `n/a` in every column -- counted off the
block above, not by eye -- including all six whole-cell accessors on both classes. The
module-level sweep found three `X.pixels[...]` indexers in the entire ladder (`bm801_align.py` 2, `bm801_vga.py` 1) and **zero** under
`rung9/` -- the shape B6 was supposed to leave behind, still holding.

> **Re-counted by B9 (2026-09-25) off the block above: 20 of the 22**, the same two
> `OffsetFrame` pixel rows still reading `NO (wraps)` on `mode`. The indexer sweep is unchanged
> at 2 + 1 (the override reaches the bytes through `raw_cell()`, so it adds no subscript --
> leg 9 of this gate is what says so, and it passed on the run that regenerated the table).

> **Re-counted by B10 (2026-09-26) off the block above: 22 of the 22.** No row carries a `NO`
> cell any more, which is what leg 2 and leg 10 of this gate now assert against the landed
> table at `a5bf99e3` rather than against this tree. The indexer sweep moved to 1 + 1 + 1: the
> two accessors in `bm801_align.py` collapsed to one, because `OffsetFrame.rgb()` is now the
> only place its clamp branch does not already refuse, and `lum()` is `sum(rgb())`. The third
> file is `run_bm801_rgb_gate.py`, one subscript inside a function named `old_rgb` -- a
> superseded formula kept live so the RED stays measurable after the fix, which is what leg 9
> was widened for; `rung9/` remains at zero.

## What this does not establish

- Every `yes` is measured on one 720x400 beacon capture at one anchor phase `(3,5)` with block
  origin `(2,7)`, over 6-9 cells and 5 pixel positions. It is a measurement, not a proof over
  all inputs, and a `yes` on a parameter cannot rule out a compensating pair of errors that
  cancel at these samples.
- The last column counts *direct* attribute calls in `run_bm80*_gate.py`. A path reached only
  through `vga.build_atlas()` or `al.materialize()` shows as `nothing`, so `nothing` means "no
  leg names it", not "no leg's outcome depends on it".
- The audit changed nothing, so it cannot say whether a fix is cheap. Rows 1 and 2 are the two
  it would bet are, and B7's fix (17 lines, one accessor, gated twice) is the precedent.
  B9 answered this for row 1, and the answer was not "one line": the override is one line and
  one docstring, and the rest was the two other gates it moved -- B7's blind side had to be
  re-pointed at a base `Frame` because `Frame.grid` is built on `self.lum`, and this file's
  legs 1, 3, 4 and 0 re-pointed with it. Cheap, and not free in the way the bullet assumed.
- `reaches` is transitive over the *source text*, so a body that hands work to a name this file
  does not know about is charged `derived`. It is over-approximated on receivers and
  under-approximated on indirection, and both directions are stated rather than assumed.

## The three worst rows, queued

The item's cap is explicit: land the table, queue the worst three, do not start fixing during
the audit. These are builder items -- each needs no ruling and no hardware, and each is
one-accessor sized.

- **B9 -- `OriginFrame.lum()` honours none of the five and nothing reaches it. DONE
  2026-09-25, `run_bm801_lum_gate.py`.** Either give it
  the B7 treatment (route it through the relabelled, phase-shifted, mode-aware carve -- it is
  `rgb()`'s own sum, so the fix is three lines and one delegation) or cut it: make
  `OriginFrame` refuse single-pixel access and prove the refusal fires. Predict before
  measuring: the two options are not equivalent -- an override keeps `Frame.grid` usable as an
  unbound call on an `OriginFrame` (B7's leg 1 leans on exactly that), while a refusal breaks
  it, and B7's gate is the leg that would notice. **RED first:** the measurement already in
  this file is the RED, so the leg to write is the one that keeps it RED until the choice is
  made -- a call to `OriginFrame.lum()` at the anchor must be shown to equal the zero-offset
  value, and the audit table's row must flip when the fix lands.
  > **How it landed.** The override, one `return` through `raw_cell()`. The parenthetical above
  > was half right: an override does keep `Frame.grid` *usable* unbound, and it is not blind any
  > more, because `Frame.grid` is built on `self.lum` -- so B7's legs 1-4 lost their blind side
  > the moment this landed, and B9's leg 3 measures exactly that (0 of 5 sampled cells disagree
  > between `vga.Frame.grid(view, ...)` and the view's own honouring carve). B7's `blind_grid`
  > now takes a plain `vga.Frame` over the same bytes, and its whole leg output is identical
  > digit-for-digit to its pre-fix run except one line number. "Shown to equal the zero-offset
  > value" is leg 1, on the base formula, at B8's five digits. See `RECEIPT_BM801_LUM.md`.
- **B10 -- `OffsetFrame.lum()` / `OffsetFrame.rgb()` ignore `mode`. DONE 2026-09-26,
  `rung8/run_bm801_rgb_gate.py`.** Both index with `% h` and
  `% w` and neither consults `drops()`, so under `clamp` a single-pixel read invents an edge
  that B6 and B7 made the *cell* accessors refuse. Route `lum()` through `rgb()` and `rgb()`
  through the same `drops()` gate `raw_cell()` uses (or return a declared sentinel), then re-run
  this audit -- its `mode` column is the acceptance test, and leg 2 of the audit gate will fail
  until the row stops reading `NO (wraps)`. Watch the price: `build_atlas()`/`resolve()` reach
  pixels through `plane()`, so this cannot change any existing receipt; if one moves, the change
  is in this pair and that is the finding.
  > **How it landed.** Both halves of the route, and `SENTINEL` rather than a new one, chosen by
  > the equality B9 established: `sum(SENTINEL)` is the zero `raw_cell()`, `grid()` and
  > `plane()` already return for a dropped cell. `rgb()` grew the `drops()` branch and `lum()`
  > became `sum(self.rgb(...))` -- five lines and two docstrings, and `raw_cell()` untouched,
  > because it already sampled through `rgb()` behind its own `drops()` test. What the fix did
  > was put the single-pixel path under the gate the cell path has always had. The price was
  > real and it was three legs, not the one the bullet named: leg 2 of this audit could not
  > keep asserting a `NO` against live code that no longer produces it, so it asserts B8's
  > verdict against the landed table at `a5bf99e3` (leg 10 needed the same treatment for the
  > same reason, and gained a two-way cross-check on the gate column instead), and B9's leg 7 --
  > which existed to keep this row open -- flipped sign on the same five cells. The receipts did
  > not move: B7's grid gate `9/9`, B9's lum gate `10/10`, B4's clamp gate and B6's materialize
  > gate unchanged, and `wrap` returns byte-for-byte what it returned before on all 2000 cells x
  > 5 sampled pixels. Two things the bullet did not predict: a gate that keeps the superseded
  > formula in evidence must index `self.pixels` itself, which leg 9 forbade -- it now permits
  > one named `old_*` helper and prints it -- and an intermediate run of this item routed
  > `raw_cell()`'s in-frame branch at `rgb()`'s `bytes` slice instead of re-wrapping it in a
  > `tuple`, which changed the per-pixel type of an accessor this item was not asked to touch
  > and was reverted before landing. Nothing in any gate noticed, which is the same
  > no-consequence-and-no-consumer shape the coverage column exists to name.
  > See `RECEIPT_BM801_RGB.md`.
- **B11 -- the census gap: `raw_cell()` and `physical()` have no gate call site. DONE
  2026-09-26 (second half only), `rung8/run_bm801_physical_gate.py`; first half taken by B10.**
  `materialize()`
  writes the artifact from `view.raw_cell()`, and no gate calls that accessor directly -- B6's
  legs reach it sideways through `materialize()` and `drops()`. Add to the B6 gate (or a small
  new one) a leg that asserts `raw_cell(r,c)` and `plane(r,c)` agree cell-for-cell on both
  classes and both modes -- the equality that makes "the file and the mask agree" more than a
  sentence -- and one that pins `physical()`'s wrap so a future edit cannot silently turn the
  relabelling into a drop. Then re-run `--emit-table`: the last column is the deliverable, and
  it should stop saying `nothing` for those rows.
  > **Half taken by B10 (2026-09-26), without meaning to:** its leg 3 asserts the
  > `rgb()`-rebuild/`raw_cell()`/`grid()`/`plane()` equality on both classes and both modes, so
  > `raw_cell` left the `nothing` set and the count went 9 -> 7 -> 4. What is left of this item
  > is `physical()`, the one row that returns a coordinate: pinning its `% vga.ROWS` /
  > `% vga.COLS` wrap so a future edit cannot turn the relabelling into a silent drop. The
  > four rows still reading `nothing` are the `vga.Frame` base rows, which are a different
  > claim -- nothing calls them unbound -- and this item was never about them.
  > **How the second half landed (B11, 2026-09-26, `rung8/run_bm801_physical_gate.py`).** No
  > source change: the wrap is the behaviour that was already right, and what was missing was a
  > leg. Five legs of it, and the control is live code in the gate file -- `old_physical`, the
  > same relabelling with both modulo operations removed -- so each claim is measured against a
  > formula that really strays. Leg 1: 16,000 cell-and-pair comparisons equal the hand-derived
  > `(r+ko) mod 25`, `(c+jo) mod 80`, and the control disagrees on 9,311 of them. Leg 3 is the
  > one that stops a fake pass: the map must be a bijection, so a future edit cannot keep the
  > leg green by clamping instead of wrapping -- the control at `(2, 7)` names 321 samples
  > outside the grid and leaves 321 real cells unreachable. Legs 4 and 5 turn this finding's
  > quoted sentence into a measurement: at zero sub-cell phase no offset pair drops any of the
  > 2,000 cells, and at the anchor phase every one of the eight pairs drops exactly the 104
  > cells the hand-derived rule names (the whole logical row that maps to physical 24, the whole
  > logical column that maps to physical 79), while the no-wrap walk drops 416 at `(2, 7)` and
  > all 2,000 at `(25, 80)`. The `--emit-table` re-run moved three cells, one of them a side
  > effect worth naming: `physical` is off the `nothing` set, and both `drops()` rows gained
  > this gate as a caller, because pinning a coordinate means asking the mode what it makes of
  > it. See `rung8/RECEIPT_BM801_PHYSICAL.md`.

## Reproduce

    cd tools/bare_metal_poc
    python3 rung8/run_bm801_path_audit_gate.py                 # 13 legs (0-12); this audit boots
                                                               # once, and leg 12 boots B7's
                                                               # gate again -- two boots total
    python3 rung8/run_bm801_path_audit_gate.py --emit-table    # the block above, alone
    BM8_SKIP_OLDER=1 python3 rung8/run_bm801_path_audit_gate.py   # skip leg 12's nested B7 gate
    BM8_DETAILS=1  python3 rung8/run_bm801_path_audit_gate.py --emit-table   # per-cell evidence
    python3 rung8/run_bm801_lum_gate.py                        # B9's own gate: 11 legs (0-10),
                                                               # one boot here plus nested boots
                                                               # of B7's and this gate's
    BM9_SKIP_OLDER=1 python3 rung8/run_bm801_lum_gate.py       # skip leg 9's two nested gates

Host-only apart from `-snapshot` boots of the same 512K beacon image B1/B4/B5/B6/B7 already
use (one here, one more inside leg 12): no writes to any medium, no paint, no writeback, no
guest exec, and `ubuntu_desktop_pxc1_v3_selfhost/` is
named exactly once in the gate -- in a constant, never as a path it opens (leg 0 checks that).

## Land

Written at HEAD `64257fb6` (B7's landing) with `rung8/bm801_align.py` and
`rung8/bm801_vga.py` verified equal to their `HEAD` blobs by leg 0 -- this item is an audit,
so "changed no source" is a checked claim, not an intention.

`python3 doc_ref_audit.py` from `tools/bare_metal_poc`, run twice around this landing:

- **Before** (this file and the ROADMAP bullet did not exist yet):
  `92 prose files (83 fully resolving), 905 backticked path tokens checked, 163 line citations
  (0 stale), 2 skipped, 69 cited files outside HEAD (155 citations)`, `POINTER_STATUS=REVIEW (13)`.
- **After** (both exist, and the bullet names them): 908 tokens checked, 163 line
  citations (0 stale), 71 files outside HEAD (157 citations), `POINTER_STATUS=REVIEW (13)`.

Read the delta, not the totals: it is `+3` backticked tokens and `+2` files in the
outside-HEAD set -- this file and its gate, which are new and untracked at the moment the
reading was taken, and which stop being counted there once they are committed. Line
citations did not move (`163 -> 163`) and none went stale, so nothing this audit cites
shifted under it, and `POINTER_STATUS` stayed `REVIEW (13)`: the bullet adds no
unresolved pointer, which is the property the lane's prose is held to. The commit-time
`DONE` block in `.builder_queue/BM000_LADDER_LANE_STATE.md` carries the landing sha.

