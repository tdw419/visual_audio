# RECEIPT_BM801_PHYSICAL — B11: the one row that returns a coordinate, and the wrap that keeps it honest

Verdict: **GREEN, landed as a pin.** `OriginFrame.physical()` had no gate call site in the
ladder; `rung8/run_bm801_physical_gate.py` gives it one, and B8's coverage column -- the
deliverable the item named -- now reads `physical` for that row instead of `nothing`. The
accessor's source is unchanged: this item adds a leg, not a fix, because the behaviour it pins
is the one that is already right.

## What was found, in B8's words

`AUDIT_BM801_SAMPLING_PATHS.md` (landed `a5bf99e3`) measured 22 sampling paths on the two offset
frames and published a last column, "reached by a pre-existing gate?", counted by an AST walk of
call sites in `run_bm80*_gate.py`. Finding 3 listed five names that column called `nothing`:
`raw_cell` on both classes, `physical`, `lum`, `rgb`. B9 cleared `lum`, B10 cleared `rgb` and
`raw_cell` -- and B10 named what that left:

> What is left of this item is `physical()`, the one row that returns a coordinate: pinning its
> `% vga.ROWS` / `% vga.COLS` wrap so a future edit cannot turn the relabelling into a silent
> drop.

The row itself read `n/a | n/a | yes | yes | n/a | nothing`: sensitive to `ko` and `jo` and to
nothing else, which is what a relabelling should be. The reason it was left standing is the same
reason B6's hole stood for four gates -- everything that depends on it depends on it *through*
something else. `OriginFrame.plane`, `raw_cell`, `grid`, `lum`, `drops` and `in_frame` all hand
off via `self.physical(r, c)`, so the whole-cell answer for a logical cell is decided by which
physical cell that one line names, and no leg named it.

## What the wrap is for, measured

B8's finding 3 stated the property as an inference from the source text:

> `OriginFrame.physical()` is the only row that returns a coordinate rather than pixels, and
> note what the table shows about it: it wraps with `% vga.ROWS` / `% vga.COLS`, so the
> relabelling can never *itself* put a cell out of frame

That sentence is now two legs, and the control is live code -- `old_physical` in the gate file,
the same relabelling with the two modulo operations removed. Nothing raises if someone deletes
those `%`; the walk just starts naming cells that are not on the screen, `in_frame` answers no
there, `clamp` drops them, and the frame quietly loses rows it should have had. Measured at the
anchor phase `(dx, dy) = (3, 5)` on the beacon capture:

| `(ko, jo)` | landed wrap: cells `clamp` drops | control, no modulo |
|---|---|---|
| `(0, 0)` | 104 | 104 (no relabelling, so no difference) |
| `(2, 7)` | 104 | 416 |
| `(-3, 7)` | 104 | 416 |
| `(24, -81)` | 104 | 2,000 |
| `(25, 80)` | 104 | 2,000 |
| `(1000, -1337)` | 104 | 2,000 |
| `(7, 2)` | 104 | 691 |

104 is the drop the *phase* earns: at `(3, 5)` the 9x16 carve runs past the bottom edge on
physical row 24 and past the right edge on physical column 79, so 80 + 25 - 1 = 104 cells do not
fit. The wrap makes `physical` a bijection on the 2,000-cell grid, which is why the count is the
same for every pair while *which* labels drop moves: the whole logical row `(24-ko) mod 25` and
the whole logical column `(79-jo) mod 80`. At `(25, 80)` -- an offset exactly one grid wide --
the control drops every cell in the frame. That is the silent drop the item was written against,
and it is the number a textual "the source still contains a `%`" assertion would not have caught
either way, because the pin here is on behaviour.

## What this moved in the table

Re-running `python3 rung8/run_bm801_path_audit_gate.py --emit-table` on the same capture
(`85efe386fd8c6703`) changed exactly three cells, and the audit's own leg 11 reports
`generated block == the landed block`:

| row | before | after |
|---|---|---|
| `OriginFrame.physical()` | gate column `nothing` | `physical` |
| `OffsetFrame.drops()` | `grid, lum, materialize, rgb` | `grid, lum, materialize, physical, rgb` |
| `OriginFrame.drops()` | `grid, lum, materialize, rgb` | `grid, lum, materialize, physical, rgb` |

The two `drops()` cells are a side effect, named rather than smoothed over: this gate calls
`drops()` to compose the coordinate with the mode, so the census rightly sees it. The
`in_frame` rows did not move, because that walk is re-derived by hand in the gate
(`hw_in_frame`) rather than called -- the hand-derived side has to be independent of the
aligner, or the leg passes by agreeing with itself.

## Runs

Pre-commit, each with its skip flag, on the 2026-09-26 lane tick:

- `rung8/run_bm801_physical_gate.py` with `BM11_SKIP_OLDER=1`: `RESULT 8/8`.
- `rung8/run_bm801_physical_gate.py`, no skip: `RESULT 8/9`. The single FAIL is leg 8, and it
  fails on this item's own uncommitted state, not on a regression: the nested audit gate is
  `11/12` with leg 0 printing `drifted=['run_bm801_physical_gate.py(not-in-HEAD)']`, which is
  what the item that adds a `SOURCES` file looks like mid-run (B9 recorded the same shape). The
  other nested gate, B10's, is `10/10` with `BM10_SKIP_OLDER=1`.
- `rung8/run_bm801_path_audit_gate.py` with `BM8_SKIP_OLDER=1`: `RESULT 11/12`, same single
  FAIL at leg 0; leg 9 (the module-level indexer census) is unaffected -- this gate subscripts
  no pixels, so no `old_*` allowance was needed; leg 10 still prints
  `pixel rows with no gate caller=4` and `table says nothing for=4`.
- `python3 doc_ref_audit.py`: quoted in the lane record.

## What this does not establish

- The pin is on `OriginFrame.physical()`, one accessor, at one anchor phase on one 720x400
  capture. It is a measurement over the whole 2,000-cell grid for eight offset pairs -- but the
  grid, not the frame: a change to `ROWS`/`COLS` or to a non-square cell carve is outside what
  these legs see.
- It does not make `vga.Frame`'s four base rows reachable. Those still read `nothing`, and B10's
  amendment is right that they are a different claim: nothing calls them unbound, and the only
  ladder path to them is through an override that both offset classes define.
- A bijection on coordinates is not a statement about ink. This item pins which physical cell a
  logical label names; whether the bytes read out of that cell are the right bytes is what B6,
  B7, B9 and B10's gates cover, and they are unchanged by this one.
- Nothing here prevents a future edit from *removing* the wrap and updating this gate to match.
  What it prevents is doing that silently: `old_physical` is the control, and the drop-count
  legs go RED on the run that removes the modulo, before anyone has a chance to re-point them.

## Landed (2026-09-26, commit `dd8b55ea`)

The pre-commit numbers above are the ones the item had to name; these are the runs the tree
makes after it, each with its skip flag, all on the same capture (`85efe386fd8c6703`):

- `rung8/run_bm801_physical_gate.py`, no skip flags: `RESULT 9/9`, rc=0. Leg 8's nested gates:
  B8's audit `12/12` with `BM8_SKIP_OLDER=1` (leg 0 now `drifted=none` -- this file and
  `rung8/run_bm801_physical_gate.py` are both in `HEAD`, so the pre-commit FAIL at leg 0 is
  discharged by the commit, not by a re-pointed expectation), and B10's rgb gate `10/10` with
  `BM10_SKIP_OLDER=1`.
- `rung8/run_bm801_path_audit_gate.py`, no skip flags: `RESULT 13/13`, rc=0, leg 11
  `generated block == the landed block` with the `physical` row reading `physical` in its gate
  column, and leg 12's nested B7 grid gate `9/9`.
- `python3 doc_ref_audit.py`: `95 prose files (86 fully resolving), 956 backticked path tokens
  checked, 174 line citations (0 stale), 2 skipped, 69 cited files outside HEAD (156
  citations)`, `POINTER_STATUS=REVIEW (13)`. Against B10's landed run that is +1 prose file and
  +12 tokens -- this receipt and the audit/ROADMAP paragraphs -- with the unresolved-pointer
  count unchanged at 13 and `0 stale` holding. The self-reference rule: the totals moved because
  this item named files, not because anything drifted. Point-in-time, both figures: the
  paragraph that quotes 956 adds tokens of its own, so a re-run on the text you are reading
  prints a few more with the same 174 line citations at `0 stale` -- the token total is a
  per-instant number, and this file is one of the files it counts.
