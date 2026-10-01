# RECEIPT_BM801_GRID — B7: the second accessor that ignores the offset

**Date:** five gate invocations, 2026-09-25T01:24Z (first RED) to 02:30:49Z (final
GREEN), from the transcript's own tool-call timestamps and the log's last write.
**Files:** `rung8/bm801_align.py` (modified: `OffsetFrame.grid` at
`rung8/bm801_align.py:112`, `OriginFrame.grid` at `rung8/bm801_align.py:168`),
`rung8/run_bm801_grid_gate.py` (new, 10 legs).
**Depends on:** B4's aligner (`rung8/run_bm801_align_gate.py`), B5's clamp mode
(`rung8/run_bm801_clamp_gate.py`), B6's writer gate
(`rung8/run_bm801_materialize_gate.py`) and B1's beacon gate
(`rung8/run_bm801_beacon_gate.py`) — all four re-run unchanged by leg 9 — plus the
same boot path `rung8/bm801_capture.py`.
**One qemu boot of the beacon image, `-snapshot`, host-side pixels after that. No
hardware, no substrate, no ruling.** `ubuntu_desktop_pxc1_v3_selfhost/` was not
opened, named once in this gate as a `KEEP_OUT` string and never as a path it
opens; `pristine_reverify.sh` was not run.

## Why this exists

B6 named this hole in its own receipt, in the section that lists what it does not
fix: *"`OriginFrame.grid()` remains inherited from `vga.Frame` and so ignores
`dx`/`dy`/`ko`/`jo`. No reader path reaches it — `plane()` delegates to the offset
frame — but `ink_profile()` on an `OriginFrame` would carve unshifted cells.
Named, not fixed: no leg of any gate exercises it, so a fix here would be untested
by construction."* The last clause is the item. Two sampling paths that disagree
with the decision above them were found in one file by accident —
`materialize()` hand-rolling `% view.h` (B6), and `grid()` inheriting a carve that
knows nothing about the offset (B7) — and both survived several gates that each
printed their own full count.

The claim was checked before it was believed, and it held. `vga.Frame.grid` is not
a leaf: it is the body that both `vga.Frame.plane` (`rung8/bm801_vga.py:93`) and
`vga.Frame.ink_profile` (`rung8/bm801_vga.py:79`) are built on, and it addresses
`self.pixels` at `(r*ch + y)*w + c*cw + x` — no phase, no relabelling, no mode. So
an offset frame carried a path back to the reader's own thresholding rule that read
the uncorrected bytes.

## What changed

`OffsetFrame.grid()` and `OriginFrame.grid()` now exist, and both derive their rows
from `raw_cell()` — the accessor B6 introduced for exactly this reason:

    flat = self.raw_cell(r, c)
    return [[sum(px) for px in flat[y * self.cw:(y + 1) * self.cw]]
            for y in range(self.ch)]

`OriginFrame.grid` delegates through `physical()` to that method, the same shape as
`plane`, `raw_cell`, `drops` and `in_frame` already had.

**The choice, and the number that forced it.** The item allowed two landings: fix
`grid()`, or cut the class down so `grid()` refuses on an offset frame. The census
(leg 7, run 4) gives `.grid(` exactly **two** call sites in the tree, both inside
`bm801_vga.py` (lines 79 and 93, the bodies of `ink_profile()` and `plane()`), and
**zero** outside it; `.lum(` has exactly **one** call site tree-wide
(`rung8/bm801_vga.py:64`, inside `Frame.grid()`); `rung9/` reaches neither name.
Refusal would therefore have raised from inside `plane()` — the accessor every
reader, scorer and atlas in the tree goes through — to protect a caller that does
not exist, and `vga.Frame.plane` is inherited by the base class that has no offsets
to honour. So the smaller surface is not the refusal: it is one rule. Fixing
`grid()` also cost no caller, which the two zero-offset controls record below.

Routing through `raw_cell()` rather than through `self.lum()` is the part that
carries the mode. `OffsetFrame.lum` honours `dx`/`dy` but takes `% self.h` and
`% self.w`, so a `grid()` built on it would still wrap at the edges under `clamp` —
leg 5 measures that version: **104 of 104** cells the clamp view refuses to sample
came back as opposite-edge bytes rather than the sentinel.

## What the gate measured

One capture (`sha256[:16] = 85efe386fd8c6703`), frame 720x400, cell 9x16, and one
displacement throughout: `roll(3,5)`, which B4/B5's harness aligns to phase (6,11)
with the calibration block at origin (24,79); the clamp view of that geometry drops
104 cells.

Run 1, against `bm801_align.py` as it stood (01:25:41Z): legs 3, 4, 5 and 6 RED, and
the run died in leg 8's message before printing a total. Run 2, same code, gate
repaired and legs 0-8 only (01:26:37Z and 01:29:12Z): `RESULT 7/9 legs pass`, rc=1,
with legs 4 and 5 the failures that carry the defect.

    FAIL 4  view profile == honouring: False | blind == uncorrected-frame profile: True
           | columns where blind differs from honouring: 9/9
           | view=[1020960, 194811, 1019412] honouring=[126354, 991776, 155826]
    FAIL 5  clamp view drops 104 cells; inherited carve invents 104 of them;
           grid() disagrees with the honouring carve on 104 dropped + 160 sampled
           in-frame cells

Those two vectors are the item in one line: the profile a displaced view reported
summed to 2,235,183 across three columns and the profile of the pixels actually
there summed to 1,273,956. Run 3, fix applied, detached from 01:40:19Z:
`RESULT 9/10`, rc=1, the single failure leg 7's census (see below). Run 4, fix
re-applied byte-identically and the census rewritten, 02:11:15Z to 02:30:49Z:
**`RESULT 10/10 legs pass`, `GATE_RC=0`**, with

    PASS 4  view profile == honouring: True | blind == uncorrected-frame profile: True
           | view=[126354, 991776, 155826] honouring=[126354, 991776, 155826]
    PASS 5  clamp view drops 104 cells; inherited carve invents 104 of them;
           grid() disagrees with the honouring carve on 0 dropped + 0 sampled
           in-frame cells
    PASS 6  wrap view: 0/108 pairs disagree | clamp view: 0/108 pairs disagree
    PASS 9  run_bm801_align_gate.py rc=0 RESULT 9/9 | run_bm801_beacon_gate.py rc=0
           RESULT 7/7 | run_bm801_clamp_gate.py rc=0 RESULT 9/9 |
           run_bm801_materialize_gate.py rc=0 RESULT 9/9

The blind column is still printed at PASS legs, on purpose: `blind_grid()` calls
`vga.Frame.grid` **unbound** on the view, so the defect stays measured inside the
run that fixes it rather than being deleted along with it. Legs 1 and 2 are the two
halves of the claim "this is invisible when the frame needs no correction": 160 of
160 sampled cells disagree at the displaced geometry, 0 of 160 at zero offset.

## Predictions this gate refuted, kept rather than deleted

1. **"the blind carve disagrees with its own label on all 160 sampled cells."** It
   disagreed on none. Run 1 measured `0/160` differing and `160/160` matching the
   carve 24 rows and 79 columns earlier — on the beacon's *fill* rows, which are one
   repeated glyph over the whole frame, so a whole-cell relabel is unobservable
   there by construction. That invisibility is part of why the hole survived. The
   leg now samples the message row and the calibration block: `84/84` disagree with
   their own label and `84/84` equal the earlier carve, and the fill-row band is
   reported inside the same leg as the control that explains run 1's zero.
2. **"leg 6 will show 19/108 disagreements caused by the code."** Ten-ish of them
   were the gate's own hand-computed reference: `honor_cell()` returned its
   out-of-frame flag as the dropped flag on the wrap path, so the reference dropped
   cells the mode keeps. Fixed to return `False` under wrap, measured again: 0/108
   on both modes. The RED figure is kept above because it was really printed.
3. **"`.grid(` has zero call sites outside `bm801_vga.py`, therefore the census is
   done."** Run 3 reported `1 outside this gate [('bm801_align.py', 169)]` — the
   delegating override this item added — plus an `ink_profile` "call site" that was
   a word of its docstring. A grep census measures the patch, not the consumers, so
   leg 7 is now an AST walk: `grid() calls: 2 in bm801_vga.py [93, 79], 1 in
   bm801_align.py [169], elsewhere none`. The assertion changed shape accordingly
   and now *names* the aligner's own override as the only expected non-`vga`
   consumer instead of pretending it is absent.
4. **"a GREEN run means the item is landed."** It does not, twice over. See the next
   section: the lane's `bm801_align.py` was restored to its committed content by
   another process during runs 3 and 4, and a green log is not a green tree.

## A collision this item records rather than resolves

While this gate was running, `tools/bare_metal_poc/rung8/bm801_align.py` was
rewritten to its committed content twice, both times from outside this session:

| instant | evidence |
|---|---|
| 2026-09-25T01:56:38Z | aligner mtime, size back to 17,242 B = `git show HEAD:` byte-for-byte; `.git/index` written 15 s later (20:56:53 local); `.pytest_cache/v/cache/nodeids` 1 s before |
| 2026-09-25T02:17:31Z | same file, same size, `grep -c 'def grid('` 0; `/tmp/hermes-snap-8bf5de8223cb.sh` created in the same second |

Both restors left untracked files alone — the gate itself,
`rung8/run_bm801_grid_gate.py`, survived both — which is the signature of a
restore of *tracked* paths rather than a deletion. This lane's work lock was held
only around the state-file appends, not across the run, so nothing in the protocol
would have stopped a writer that does not take it, and the four-term busy test at
02:08Z saw a clean tree because the first restore had already cleaned it. Attribution
stops at those two timestamps: a pytest swarm and a hermes shell snapshot are what
is adjacent in time, and neither is evidence of who typed the command. Three
interactive agent sessions hold this repository as their cwd at the time of writing
(`ps` over `/proc/*/cwd`: pids 2058135, 2129393, 2479272).

What the item did about it: the fix was replayed from the session transcript's own
`Edit` payloads rather than retyped, and the replay was checked — HEAD content plus
those two edits is byte-identical to the file the gate measured (md5
`1aa9cfc81a1c1b2fc3e103555cabaf08`, 18,074 B). Landing is the end of the exposure:
a restore-to-committed is a no-op once the change is committed. That is a lane
observation, not a ruling; the standing question of whether another automation tick
is cleaning tracked files it finds dirty belongs to the operator.

## Line-citation drift this change caused, and does not repair

`rung8/bm801_align.py` gained 14 lines at :111 and 3 more at :168, so every
citation into it past :111 moves. Rule 6: the old records stay as written; the
mapping is here.

| cited in `RECEIPT_BM801_CLAMP.md` / `RECEIPT_BM801_MATERIALIZE.md` as | pointed at | now lives at |
|---|---|---|
| `:114` | `return sum(self.pixels[px:px + 3])` (offset `lum`) | :128 |
| `:117` | `def edge_invented` | :131 |
| `:135` | `self.dx, self.dy, self.ko, self.jo =` | :149 |
| `:139` | `def physical` | :153 |
| `:151` | `def raw_cell` (OriginFrame) | :165 |
| `:225` | `'cells_scored': reg['cells'],` | :242 |
| `:236` | `view = OriginFrame(base, bx, by, ko, jo, mode)` | :253 |
| `:256` | `'cells_scored'` line in the report | :273 |
| `:267` | `def materialize` | :284 |
| `:290` | a `for r in range(vga.ROWS):` line | :307 |
| `:312` | a docstring line | :329 |

`:290` and `:312` were already pointing at the wrong text before this change: B6's
own table puts `rep['declined_by_edge'] =` at :328 and `REPORT_KEYS =` at :350, and
this insert moves those to :345 and :367. That is the failure mode the next
paragraph restates: the audit range-checks the numbers, so a citation that was wrong
when it was written stays "live" forever.
| `:328` | `rep['declined_by_edge'] =` | :345 |
| `:350` | `REPORT_KEYS =` | :367 |

`:46`, `:70`, `:76`, `:85`, `:89`, `:92`, `:94`, `:99` are unchanged. The same
caveat B6 recorded about the checker still applies: `doc_ref_audit.py` range-checks
these numbers and will call a moved citation live, because the line it names exists
either way.

## What this does not fix

- `OffsetFrame.lum` and `OriginFrame.lum` still take `% self.h` / `% self.w`, so
  they honour `dx`/`dy` and not `mode`, and `OriginFrame.lum` still honours none of
  the four offsets. After this change nothing on an offset frame reaches them:
  `Frame.grid` was `lum`'s only caller tree-wide, and both classes now override
  `grid`. The only way in is an unbound `vga.Frame.grid(view, ...)`, which is what
  this gate does deliberately to keep its own RED visible. That row belongs to B8's
  table, with the number above it.
- The census covers `rung8/` and `rung9/`, which is what the lane owns. It is not a
  claim about the repository.
- `align()`'s decision is unchanged, `wrap` is still the default mode, and which
  mode a real photograph needs is still unanswered. What changed is that one fewer
  path in the reader disagrees with the answer.
- Nothing here was measured on physical hardware or on the substrate.
- The foreign restore is recorded, not resolved. If it recurs after this commit,
  the file will go back to containing `def grid`, because it is now committed; the
  next thing to notice would be a commit appearing that this lane did not write.

## Reproduce

    cd tools/bare_metal_poc && python3 rung8/run_bm801_grid_gate.py
    # 10/10, exit 0, ~31 min, one boot (legs 0-8 alone are ~2 min: the nested
    # regression chain is the long part). Set BM7_SKIP_OLDER=1 for legs 0-8 only.

## Land

Landed by the lane tick that ran it, 2026-09-25, one commit, paths enumerated:
`tools/bare_metal_poc/ROADMAP.md`,
`tools/bare_metal_poc/rung8/bm801_align.py`,
`tools/bare_metal_poc/rung8/run_bm801_grid_gate.py`,
`tools/bare_metal_poc/rung8/RECEIPT_BM801_GRID.md`.

Audit totals, taken after the ROADMAP append and after this file was last written
(`python3 doc_ref_audit.py` from `tools/bare_metal_poc`): **91 prose files (82 fully
resolving), 895 backticked path tokens, 161 line citations with 0 stale, 2 skipped,
70 cited files outside HEAD (159 citations), `POINTER_STATUS=REVIEW (13)`.** Against
B6's landing figures (90 / 870 / 155 / 0 / 2 / 70 / 13) that is one prose file, 25
tokens and 6 citations, all of them this file. Point-in-time as always, and this
sentence moves one of the numbers: the same reading taken after the sentence itself
is written gives **896** tokens and nothing else changes, the extra token being the
audit's own filename named in it. The audit also
prints `in range` for the drifted `bm801_align.py` citations named in the table
above, because a range check cannot see that `:151` now holds
`self._off = OffsetFrame(base, dx, dy, mode)`.

## Correction: B9 landed the row this section named (2026-09-25)

The first bullet above is what B9 was queued from, and it is superseded in both halves.
`OriginFrame.lum` is overridden now (`bm801_align.py:168-179`, one `return` through
`raw_cell()`), so it honours all five and invents nothing on a clamped cell; the audit
table's row reads `yes`/`yes`/`yes`/`yes`/`yes` with `lum` in its gate column. And the
sentence "the only way in is an unbound `vga.Frame.grid(view, ...)`, which is what this
gate does deliberately to keep its own RED visible" was true exactly as long as the
inherited `lum` was: `Frame.grid` is built on `self.lum`, so overriding it made this
gate's blind side honour the offsets. `blind_grid()` takes a plain `vga.Frame` over the
same bytes instead, and B9's leg 3 measures the reason (0 of 5 sampled cells disagree
between `vga.Frame.grid(view, ...)` and the view's own carve). Legs 0-6 and 8 of this
gate print values identical to the runs recorded above; leg 7's census now separates a
gate caller from a production one. `OffsetFrame.lum`/`rgb` still wrap under `clamp` --
that is B10, and B9's leg 7 asserts it still does. See `RECEIPT_BM801_LUM.md`.
