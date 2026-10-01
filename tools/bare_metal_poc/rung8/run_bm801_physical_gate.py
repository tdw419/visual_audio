#!/usr/bin/env python3
"""run_bm801_physical_gate.py -- B11: pin `OriginFrame.physical()`'s wrap, the one row the
audit's coverage column still called `nothing`.

B8's table (`AUDIT_BM801_SAMPLING_PATHS.md`, landed `a5bf99e3`) has 22 rows and exactly one of
them returns a coordinate instead of pixels: `OriginFrame.physical()`. Its body is
`(r + ko) % vga.ROWS, (c + jo) % vga.COLS`, and B8's finding 3 named what that modulo is for --
"the relabelling can never *itself* put a cell out of frame". Every accessor on the class is
built on it (`plane`, `raw_cell`, `grid`, `lum`, `drops`, `in_frame` all hand off through
`self.physical(r, c)`), so the whole-cell answer for a logical cell is decided by which physical
cell that line names. B9 and B10 fixed accessors that reached bytes; this row was left with no
gate call site at all, which is the same exposure B6 had: an accessor four other legs depend on
and none of them names.

Drop the two `%` and nothing raises. `r + ko` walks off the bottom of the grid for the last `ko`
rows, `in_frame` says no there, `clamp` drops those cells, and the frame silently loses rows it
should have had -- measured below: at the anchor phase the landed walk drops 104 of 2,000 cells
for every offset pair, the same walk without the modulo drops 416 at `(ko, jo) = (2, 7)` and all
2,000 at `(25, 80)`. The pin therefore has to be behavioural, not textual: the mapping equals the
hand-derived wrap on every cell, it never leaves the grid, it is a bijection (so no cell is
dropped *and* no cell is sampled twice), and the drop set it produces composes with `in_frame`
exactly as the hand-derived rule says.

`old_physical` is the same relabelling with the modulo removed, kept live in this file so each of
those claims is measured against a formula that really strays rather than against a sentence
saying it would. Nothing here subscripts `self.pixels` -- this accessor returns a coordinate --
so the capture is only ever the frame's dimensions, and `run_bm801_path_audit_gate.py`'s leg 9
(file-level indexer census) is untouched by this item.

Run: python3 rung8/run_bm801_physical_gate.py   (one beacon boot, then host-side; leg 8 nests
two more)
Set BM11_SKIP_OLDER=1 to skip leg 8's nested gates while iterating. Note that B8's audit gate
compares eleven of its files against their `HEAD` blobs and re-diffs its own landed table, so
leg 8 reads RED until this item's files are committed: run once skipped, then land, then run in
full and quote the landed-state numbers.
"""

import collections
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bm801_align as al        # noqa: E402
import bm801_capture as cap     # noqa: E402
import bm801_vga as vga         # noqa: E402
# imported for its census and its `landed_table` reader only; this gate boots its own
# capture, and the audit module boots in `main()`, not on import
import run_bm801_path_audit_gate as audit   # noqa: E402

RESULTS = []
KEEP_OUT = 'ubuntu_desktop_pxc1_v3_selfhost'

# the commit that last published the generated table, so leg 7's before-side is a fact in git
# and not a quote from this file's own prose
B10_TABLE_SHA = 'f74acfb4'

# the audit's anchor phase, kept identical on purpose: `(3,5)` is the phase at which B8's
# `mode` probes bite, so a clamp drop seen here is the same drop seen in the table
PX, PY = 3, 5
GRID = [(r, c) for r in range(vga.ROWS) for c in range(vga.COLS)]
LAST_ROW, LAST_COL = vga.ROWS - 1, vga.COLS - 1
# zero, both signs, |offset| == the grid side, |offset| > it, and a magnitude no cell arithmetic
# would ever be written with -- the wrap is a total function or it is nothing
OFFSETS = [(0, 0), (2, 7), (-3, 7), (24, -81), (25, 80), (-25, -80), (1000, -1337), (7, 2)]


def predict(name, text):
    print('--> %-32s predicts: %s' % (name, text))


def check(name, ok, detail):
    RESULTS.append((name, bool(ok)))
    print('    %s %-32s %s' % ('PASS' if ok else 'FAIL', name, detail))


# ------------------------------------------------------------------ hand-derived side
def want_phys(r, c, ko, jo):
    """Physical cell of logical `(r, c)`: relabel, then wrap into the grid. By hand -- no
    call to the aligner, so the pin cannot be made true by agreeing with itself."""
    return (r + ko) % vga.ROWS, (c + jo) % vga.COLS


def old_physical(r, c, ko, jo):
    """The control: the same relabelling with the two modulo operations removed. Live code,
    because the claim being pinned is what its absence costs."""
    return r + ko, c + jo


def hw_in_frame(w, h, cw, ch, dx, dy, pr, pc):
    """`in_frame` re-derived by hand at a physical cell: does the whole carve fit?"""
    y0, x0 = pr * ch + dy, pc * cw + dx
    return y0 >= 0 and y0 + ch <= h and x0 >= 0 and x0 + cw <= w


def main():
    run = tempfile.mkdtemp(prefix='bm811_physgate.')
    print('# B11 OriginFrame.physical() wrap pin | run dir %s' % run)
    img = os.path.join(run, 'beacon.img')
    subprocess.run(['nasm', '-o', os.path.join(run, 'b.bin'),
                    os.path.join(HERE, 'bm801_beacon.asm')], check=True)
    data = open(os.path.join(run, 'b.bin'), 'rb').read()
    with open(img, 'wb') as fh:
        fh.write(data + b'\0' * ((1 << 20) - len(data)))
    clean = cap.capture(img, settle=4.0, run_dir=run, keep=True)
    src_sha = hashlib.sha256(open(clean, 'rb').read()).hexdigest()[:16]
    base = vga.Frame(clean)
    cw, ch, w, h = base.cw, base.ch, base.w, base.h
    print('# frame %dx%d cell %dx%d | capture %s | grid %dx%d | offsets %s'
          % (w, h, cw, ch, src_sha, vga.COLS, vga.ROWS,
             ' '.join('(%d,%d)' % o for o in OFFSETS)))

    # ---- leg 0: the item reads the capture and writes nothing --------------------
    predict('0 source-inert',
            'no leg writes to the capture: %s unchanged at the end, and this file names the '
            'keep-out disk exactly once -- in the constant above, never as a path it opens'
            % src_sha)
    self_text = open(os.path.abspath(__file__)).read()
    sha_after = hashlib.sha256(open(clean, 'rb').read()).hexdigest()[:16]
    check('0 source-inert', sha_after == src_sha and self_text.count(KEEP_OUT) == 1,
          'sha before=%s after=%s | keep-out name occurrences=%d'
          % (src_sha, sha_after, self_text.count(KEEP_OUT)))

    # ---- leg 1: the accessor equals the hand-derived wrap, cell for cell ---------
    views = {(ko, jo): al.OriginFrame(base, PX, PY, ko, jo, 'clamp') for ko, jo in OFFSETS}
    bad = [(ko, jo, rc, views[(ko, jo)].physical(*rc), want_phys(rc[0], rc[1], ko, jo))
           for ko, jo in OFFSETS for rc in GRID
           if views[(ko, jo)].physical(*rc) != want_phys(rc[0], rc[1], ko, jo)]
    control_moves = sum(1 for ko, jo in OFFSETS if (ko, jo) != (0, 0)
                        for rc in GRID if old_physical(rc[0], rc[1], ko, jo)
                        != want_phys(rc[0], rc[1], ko, jo))
    predict('1 equals-hand-derived-wrap',
            '%d cells x %d offset pairs = %d comparisons must each equal `((r+ko) %% %d, '
            '(c+jo) %% %d)` computed here from the integers, and the control -- the same pair '
            'without the modulo -- must disagree with that on %d of them, so a leg that '
            'compares nothing cannot pass'
            % (len(GRID), len(OFFSETS), len(GRID) * len(OFFSETS), vga.ROWS, vga.COLS,
               control_moves))
    check('1 equals-hand-derived-wrap', not bad and control_moves > 0,
          'comparisons=%d | mismatches=%d%s | control (no modulo) differs on %d cells'
          % (len(GRID) * len(OFFSETS), len(bad),
             (' e.g. %s' % (bad[0],)) if bad else '', control_moves))

    # ---- leg 2: it never leaves the grid -----------------------------------------
    stray = [(ko, jo, rc) for ko, jo in OFFSETS for rc in GRID
             if not (0 <= views[(ko, jo)].physical(rc[0], rc[1])[0] < vga.ROWS
                     and 0 <= views[(ko, jo)].physical(rc[0], rc[1])[1] < vga.COLS)]
    control_stray = [(ko, rc) for ko, _j in OFFSETS for rc in GRID
                     if not (0 <= old_physical(rc[0], rc[1], ko, 0)[0] < vga.ROWS)]
    strays_at = [o[0] for o in OFFSETS
                 if any(not (0 <= old_physical(r, c, o[0], o[1])[0] < vga.ROWS)
                        for r, c in GRID)]
    predict('2 never-strays-off-grid',
            'the relabelling is a total function on the grid: %d results, %d of them outside '
            '`0..%d x 0..%d`. Without the wrap the same walk leaves the grid through %d cells, '
            'at every ko except the pairs where it is zero: ko=%s'
            % (len(GRID) * len(OFFSETS), len(stray), LAST_ROW, LAST_COL, len(control_stray),
               strays_at or 'none'))
    check('2 never-strays-off-grid', not stray and len(control_stray) > 0,
          'in-range=%d/%d | strays=%d | control strays=%d cells'
          % (len(GRID) * len(OFFSETS) - len(stray), len(GRID) * len(OFFSETS), len(stray),
             len(control_stray)))

    # ---- leg 3: a bijection, so nothing is both dropped and doubled --------------
    counts = {o: collections.Counter(views[o].physical(r, c) for r, c in GRID)
              for o in OFFSETS}
    dupes = [(o, p, n) for o, cnt in counts.items() for p, n in cnt.items() if n > 1]
    missed = [(o, len(set(GRID) - set(cnt))) for o, cnt in counts.items()]
    control_cnt = {o: collections.Counter(old_physical(r, c, o[0], o[1]) for r, c in GRID)
                   for o in OFFSETS}
    control_off = sum(n for p, n in control_cnt[(2, 7)].items()
                      if not (0 <= p[0] < vga.ROWS and 0 <= p[1] < vga.COLS))
    control_unreached = len(set(GRID) - set(control_cnt[(2, 7)]))
    predict('3 relabelling-is-a-bijection',
            'every offset pair must map the %d logical cells onto %d distinct physical cells -- '
            'a mapping that repeats is two labels for one cell, one that misses is a cell no '
            'label reaches. Grid cells unreached, per pair: %s. The control at (2,7) names %d '
            'samples outside the grid and leaves %d real cells unreachable, so this leg is not '
            'satisfied by any map that simply stays in range'
            % (len(GRID), len(GRID),
               ' '.join('%s=%d' % (o, n) for o, n in missed), control_off, control_unreached))
    check('3 relabelling-is-a-bijection',
          not dupes and all(n == 0 for _o, n in missed)
          and len(counts[(2, 7)]) == len(GRID) and control_off > 0 and control_unreached > 0,
          'duplicates=%d | grid cells unreached=%s | distinct at (2,7)=%d/%d | control off-grid '
          'samples=%d, unreached cells=%d'
          % (len(dupes), sorted({n for _o, n in missed}), len(counts[(2, 7)]), len(GRID),
             control_off, control_unreached))

    # ---- leg 4: finding 3's sentence, measured ------------------------------------
    zero_drops = []
    for ko, jo in OFFSETS:
        v0 = al.OriginFrame(base, 0, 0, ko, jo, 'clamp')
        n = sum(1 for rc in GRID if v0.drops(*rc))
        if n:
            zero_drops.append(((ko, jo), n))
    predict('4 zero-phase-never-drops',
            'at dx=dy=0 the sub-cell phase fits every cell, so under `clamp` no offset pair may '
            'drop any of the %d cells -- this is B8\'s finding 3, "the relabelling can never '
            'itself put a cell out of frame", as a leg rather than a sentence. Pairs that do '
            'drop: %s' % (len(GRID), zero_drops or 'none'))
    check('4 zero-phase-never-drops', not zero_drops,
          'pairs tested=%d | dropped cells at zero phase=%d (%s)'
          % (len(OFFSETS), sum(n for _o, n in zero_drops),
             ' '.join('%s=%d' % (o, n) for o, n in zero_drops) or 'none'))

    # ---- leg 5: what the composition with in_frame actually costs -----------------
    # At this anchor phase the carve runs past the bottom edge on the last physical row and
    # past the right edge on the last physical column, so `clamp` earns ROWS + COLS - 1 drops
    # at zero relabelling; that number is read off the (0,0) pair here rather than asserted
    # from prose, because the claim below is about what happens to it when ko/jo move.
    def dropped_at(ko, jo, phys):
        return sorted(rc for rc in GRID
                      if not hw_in_frame(w, h, cw, ch, PX, PY, *phys(rc[0], rc[1], ko, jo)))
    base_dropped = [rc for rc in GRID if views[(0, 0)].drops(*rc)]
    per_pair = []
    for ko, jo in OFFSETS:
        got = sorted(rc for rc in GRID if views[(ko, jo)].drops(*rc))
        want = dropped_at(ko, jo, want_phys)
        control = dropped_at(ko, jo, old_physical)
        gs = set(got)
        row_hit = (LAST_ROW - ko) % vga.ROWS          # the logical row that lands on physical 24
        col_hit = (LAST_COL - jo) % vga.COLS          # ... and the logical column on physical 79
        per_pair.append(((ko, jo), len(got), got == want, row_hit,
                         all((row_hit, c) in gs for c in range(vga.COLS)), col_hit,
                         all((r, col_hit) in gs for r in range(vga.ROWS)), len(control)))
    bad5 = [p for p in per_pair if not p[2]]
    control_extra = [(p[0], p[7]) for p in per_pair if p[7] != len(base_dropped)]
    predict('5 drop-set-composes-by-permutation',
            'at phase (%d,%d) the carve runs off the bottom edge on physical row %d and off the '
            'right edge on physical column %d, so zero relabelling drops %d cells. The wrap makes '
            '`physical` a bijection, so every pair must drop exactly the pre-image of that same '
            'set -- %d cells, being the whole logical row that maps to physical 24 (that is row '
            '(24-ko) mod 25 = %s here) and the whole logical column that maps to physical 79 '
            '((79-jo) mod 80 = %s), minus the one cell they share. The pairs whose no-wrap control '
            'count differs from %d: %s'
            % (PX, PY, LAST_ROW, LAST_COL, len(base_dropped), len(base_dropped),
               [p[3] for p in per_pair], [p[5] for p in per_pair], len(base_dropped),
               ' '.join('%s=%d' % (o, c) for o, c in control_extra) or 'none'))
    check('5 drop-set-composes-by-permutation',
          not bad5 and all(p[1] == len(base_dropped) for p in per_pair)
          and all(p[4] and p[6] for p in per_pair)
          and all(p[1] < p[7] for p in per_pair if p[0] != (0, 0)),
          'base_dropped=%d | mismatches=%d | per-pair (ko,jo)->dropped/full-row/full-col/control: '
          '%s' % (len(base_dropped), len(bad5),
                  ' '.join('%s:%d/r%d/c%d/%d' % (p[0], p[1], p[3], p[5], p[7])
                           for p in per_pair)))

    # ---- leg 6: the census now reaches this row -----------------------------------
    hits = audit.census()
    gate_files = audit.gate_files_for('physical', hits)
    predict('6 census-names-this-gate',
            'the deliverable is the table\'s last column, and the mechanism behind it is B8\'s '
            'own AST walk: `physical(` must now have a call site inside a `run_bm80*_gate.py`, '
            'and that file must be this one. Callers of `.physical(` anywhere in the ladder: %s'
            % sorted({f for f, _l in hits.get('physical', ())}))
    check('6 census-names-this-gate',
          any(os.path.basename(f) == os.path.basename(__file__) for f in gate_files),
          'gate files for physical=%s | all callers=%s'
          % (gate_files or 'none',
             ' '.join('%s x%d' % (f, sum(1 for g, _l in hits['physical'] if g == f))
                      for f in sorted({f for f, _l in hits.get('physical', ())})) or 'none'))

    # ---- leg 7: the before-side survives the fix ----------------------------------
    try:
        old_doc = audit.landed_table(B10_TABLE_SHA)
        old_cols, old_gate = audit.cols_of(audit.row_line(old_doc, 'OriginFrame.physical()'))
        old_err = ''
    except Exception as exc:                        # a missing history leg is a failed leg
        old_cols, old_gate, old_err = None, None, str(exc)
    predict('7 row-was-unreached-at-b10',
            'the table as landed at %s reads `nothing` in the last column for '
            '`OriginFrame.physical()` while reading yes on ko and jo -- so B11 is measured '
            'against a published finding, and this paragraph in the audit cannot be softened by '
            'editing the file it sits in' % B10_TABLE_SHA)
    check('7 row-was-unreached-at-b10',
          not old_err and old_cols is not None and old_gate == 'nothing'
          and old_cols[2] == 'yes' and old_cols[3] == 'yes' and old_cols[0] == 'n/a',
          'at %s: cells=%s gate=%s%s' % (B10_TABLE_SHA, old_cols, old_gate,
                                         (' | git error: %s' % old_err) if old_err else ''))

    # ---- leg 8: the gates this item leans on --------------------------------------
    if os.environ.get('BM11_SKIP_OLDER'):
        print('# older-gates skipped (BM11_SKIP_OLDER set): the nested gates were not run')
    else:
        predict('8 older-gates-regress',
                'B8\'s audit gate (whose generated table this item re-points, run with its own '
                'nested leg skipped) and B10\'s rgb gate (whose leg 3 took the other half of B11) '
                'still exit 0 with their full leg counts')
        outs = {}
        for g, env in (('run_bm801_path_audit_gate.py', dict(os.environ, BM8_SKIP_OLDER='1')),
                       ('run_bm801_rgb_gate.py', dict(os.environ, BM10_SKIP_OLDER='1'))):
            p = subprocess.run([sys.executable, os.path.join(HERE, g)],
                               capture_output=True, text=True, env=env)
            res = [l for l in p.stdout.splitlines() if l.startswith('RESULT')]
            outs[g] = (p.returncode, ' '.join(res) or (p.stdout[-90:] + p.stderr[-200:]))
        check('8 older-gates-regress', all(rc == 0 and t for rc, t in outs.values()),
              ' | '.join('%s rc=%s %s' % (g, rc, t) for g, (rc, t) in sorted(outs.items())))

    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print('RESULT %d/%d legs pass' % (n_ok, len(RESULTS)))
    shutil.rmtree(run, ignore_errors=True)
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main())
