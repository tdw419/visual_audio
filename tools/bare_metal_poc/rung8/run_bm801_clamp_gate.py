#!/usr/bin/env python3
"""run_bm801_clamp_gate.py -- B5: does the aligner know which pixels it never had?

`wrap` sampling (B3/B4) takes a cell that runs off an edge from the opposite
edge. For a cyclically rolled frame that is the truth; for a capture off a real
monitor it is a fabrication -- the displaced strip is not there, and a phase
scored partly on opposite-edge bytes is a phase confirmed by pixels the camera
never showed. This gate measures the `clamp` mode that answers the difference:
it samples only cells whose whole carve is inside the capture, so the usable-cell
set shortens and nothing is invented to fill it.

Every leg prints its prediction before it measures, and the two hard rules B3/B4
set are re-checked rather than assumed: no phase that fails to raise the
distance-0 count is ever applied, the offset found is always reported, and
`clamp` may never make a bad capture guessable.

Run: python3 rung8/run_bm801_clamp_gate.py     (one beacon boot, then host-side)
"""

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
import bm801_reader_decay as decay   # noqa: E402
import bm801_vga as vga         # noqa: E402

MSG = al.MSG
RESULTS = []


def predict(name, text):
    print('--> %-26s predicts: %s' % (name, text))


def check(name, ok, detail):
    RESULTS.append((name, bool(ok)))
    print('    %s %-26s %s' % ('PASS' if ok else 'FAIL', name, detail))


def roll(src, dst, sx, sy):
    """Cyclic whole-frame displacement -- the frame `wrap` is honest about."""
    w, h, rows = decay.read_rgb(src)
    out = [[rows[(y + sy) % h][(x + sx) % w] for x in range(w)] for y in range(h)]
    decay.write_ppm(dst, w, h, out)
    return dst


def lost_strip(src, dst, sy):
    """Content moved down by sy with the vacated strip blacked out: a real capture.

    `roll` cannot distinguish the two; this can, and it is the shape clamp exists
    for, so leg 6 uses it to show the modes separate on evidence and not on
    arithmetic alone.
    """
    w, h, rows = decay.read_rgb(src)
    blank = [[0, 0, 0] for _ in range(w)]
    out = [rows[y - sy] if y >= sy else blank for y in range(h)]
    decay.write_ppm(dst, w, h, out)
    return dst


def invented_geometry(path, dx, dy, cells):
    """Cell count outside the capture, from the header numbers alone.

    Deliberately does not call bm801_align: a report field is only evidence if a
    second, independent derivation reaches the same number.
    """
    w, h, _rows = decay.read_rgb(path)
    cw, ch = w // vga.COLS, h // vga.ROWS
    return sum(1 for (r, c) in cells
               if r * ch + dy + ch > h or c * cw + dx + cw > w)


def main():
    run = tempfile.mkdtemp(prefix='bm801_clampgate.')
    print('# B5 clamp-mode gate | run dir %s' % run)
    img = os.path.join(run, 'beacon.img')
    subprocess.run(['nasm', '-o', os.path.join(run, 'b.bin'),
                    os.path.join(HERE, 'bm801_beacon.asm')], check=True)
    data = open(os.path.join(run, 'b.bin'), 'rb').read()
    with open(img, 'wb') as fh:
        fh.write(data + b'\0' * ((1 << 20) - len(data)))
    clean = cap.capture(img, settle=4.0, run_dir=run, keep=True)
    cells = al.sample_cells()
    base = vga.Frame(clean)
    cw, ch = base.cw, base.ch
    print('# frame %dx%d cell %dx%d, %d scored cells off the calibration block'
          % (base.w, base.h, cw, ch, len(cells)))

    predict('0 both-modes-inert', 'neither mode writes: the frame sha256 is identical after '
                                  'align() in wrap and in clamp')
    h0 = hashlib.sha256(open(clean, 'rb').read()).hexdigest()[:16]
    al.align(clean, mode='wrap')
    al.align(clean, mode='clamp')
    check('0 both-modes-inert',
          hashlib.sha256(open(clean, 'rb').read()).hexdigest()[:16] == h0,
          'before=%s after=%s' % (h0, hashlib.sha256(open(clean, 'rb').read()).hexdigest()[:16]))

    predict('1 edge-arithmetic', 'a %d-px y-shift is bigger than the %d-px pitch, so whole rows '
                                 'leave the capture: in_frame() is False for exactly the cells '
                                 'whose carve passes row %d, and clamp returns a flat plane there '
                                 'while wrap returns the opposite edge' % (2 * ch, ch, base.h))
    big = al.OffsetFrame(base, 0, 2 * ch)
    clamp_big = al.OffsetFrame(base, 0, 2 * ch, 'clamp')
    out_cells = [rc for rc in cells if not big.in_frame(*rc)]
    same = all(clamp_big.plane(r, c) == big.plane(r, c)
               for (r, c) in cells if big.in_frame(r, c))
    dropped_flat = all(clamp_big.plane(r, c)[1] for (r, c) in out_cells)
    wrapped_nonflat = sum(1 for (r, c) in out_cells if not big.plane(r, c)[1])
    check('1 edge-arithmetic', bool(out_cells) and same and dropped_flat,
          'shift=%dpx rows_out=%d cells_out=%d of %d in-frame-planes-identical=%s '
          'dropped-all-flat=%s wrap-instead-found-%d-glyphs'
          % (2 * ch, len({r for r, _c in out_cells}), len(out_cells), len(cells), same,
             dropped_flat, wrapped_nonflat))

    predict('2 shortens-never-fills', 'for every phase tried, exact_clamp <= exact_wrap and '
                                      'usable_clamp == total - invented: clamp may lose evidence, '
                                      'it may not manufacture any')
    bad2 = []
    for dx, dy in [(0, 0), (1, 0), (0, 4), (4, 5), (0, 12), (8, 20), (0, 2 * ch)]:
        ew = al.exact_matches(al.OffsetFrame(base, dx, dy, 'wrap'), cells)
        ec = al.exact_matches(al.OffsetFrame(base, dx, dy, 'clamp'), cells)
        inv = len([rc for rc in cells if not al.OffsetFrame(base, dx, dy).in_frame(*rc)])
        usable = len(cells) - inv
        if ec > ew or al.exact_matches(al.OffsetFrame(base, dx, dy, 'clamp'),
                                       [rc for rc in cells
                                        if al.OffsetFrame(base, dx, dy).in_frame(*rc)]) != ec:
            bad2.append((dx, dy, ew, ec))
        print('      phase=(%d,%d) wrap_exact=%d clamp_exact=%d invented=%d usable=%d %s'
              % (dx, dy, ew, ec, inv, usable, 'ok' if (dx, dy) not in
                 [b[:2] for b in bad2] else 'BAD'))
    check('2 shortens-never-fills', not bad2,
          '7 phases, clamp never exceeded wrap and counted only in-frame cells'
          if not bad2 else str(bad2))

    predict('3 large-shift-disagreement', 'v2, after run 1 at 03:03Z measured and refuted v1 '
                                          "('clamp still finds the true phase, just with a lower "
                                          'score"): on both rolls of (0,%d) and (%d,%d) clamp '
                                          'reports a LOWER exact_offblock, a DIFFERENT winning '
                                          'phase, and zero invented cells, while wrap'"'"'s chosen '
                                          'phase leans on %d -- clamping moves the answer away from '
                                          'the edge, it does not merely shrink its confidence'
            % (2 * ch + 2, cw, 2 * ch + 2, 80))
    disagree = []
    for tag, sx, sy in [('roll_0_34', 0, 2 * ch + 2), ('roll_9_34', cw, 2 * ch + 2)]:
        f = roll(clean, os.path.join(run, tag + '.ppm'), sx, sy)
        rw = al.align(f, mode='wrap')
        rc = al.align(f, mode='clamp')
        disagree.append((tag, rw, rc))
        print('      %-11s wrap: phase=%s origin=%s exact=%d/%d inv=%d d0n=%d d0c=%d applied=%s'
              % (tag, rw['phase'], rw['block_origin'], rw['exact_offblock'],
                 rw['exact_offblock_total'], rw['cells_edge_invented'], rw['distance0_naive'],
                 rw['distance0_corrected'], rw['applied']))
        print('      %-11s clamp: phase=%s origin=%s exact=%d/%d inv=%d d0n=%d d0c=%d applied=%s'
              % (tag, rc['phase'], rc['block_origin'], rc['exact_offblock'],
                 rc['exact_offblock_total'], rc['cells_edge_invented'], rc['distance0_naive'],
                 rc['distance0_corrected'], rc['applied']))
    ok3 = all(rc['exact_offblock'] < rw['exact_offblock'] and rc['phase'] != rw['phase']
              and rc['cells_edge_invented'] == 0 and rw['cells_edge_invented'] > 0
              and (not rc['applied'] or rc['distance0_corrected'] > rc['distance0_naive'])
              and (not rw['applied'] or rw['distance0_corrected'] > rw['distance0_naive'])
              for _t, rw, rc in disagree)
    check('3 large-shift-disagreement', ok3,
          '%d rolls: clamp score lower and phase different on each, wrap leaned on %d/%d invented '
          'cells and clamp on 0, increase-only held in both modes'
          % (len(disagree), disagree[0][1]['cells_edge_invented'],
             disagree[1][1]['cells_edge_invented']) if ok3 else str(
              [(t, rw['phase'], rw['cells_edge_invented'], rc['phase'], rc['cells_edge_invented'],
                rw['exact_offblock'], rc['exact_offblock']) for t, rw, rc in disagree]))

    predict('4 decline-not-confirm', 'v4. Runs 1-2 measured msg_cells_edge_invented=0 on every '
                                     'candidate (registration moved the requested row onto '
                                     'captured pixels). Run 3 reached the case: roll(0,2) read at '
                                     'row 0 gave BOTH modes 33 invented message cells, wrap '
                                     'applied it at distance0 %d>%d, and clamp refused -- but '
                                     'named "increase-only", because the score guard ran first and '
                                     'hid the edge. So one row is all-in or all-out (in_frame '
                                     'depends on the row only), and the honest leg is: on the '
                                     'candidates whose CLAMPED view leans on invented message '
                                     'cells, clamp never applies AND says the edge, while wrap on '
                                     'the same pixels does apply. Measured here: %s.'
            % (32, 16, 'roll(0,2) row 0: wrap applied=True d0 16->32 on 33 invented cells, '
                       'clamp applied=False'))
    cands = [('roll_8_34_row20', roll(clean, os.path.join(run, 'cand1.ppm'), 8, 2 * ch + 2),
              vga.MSG_ROW),
             ('roll_0_2_row0', roll(clean, os.path.join(run, 'cand2.ppm'), 0, 2), 0),
             ('roll_0_2_row1', roll(clean, os.path.join(run, 'cand3.ppm'), 0, 2), 1)]
    EDGE_CASES = []
    for tag4, f4, row4 in cands:
        r4w = al.align(f4, row=row4, mode='wrap')
        r4c = al.align(f4, row=row4, mode='clamp')
        print('      %-16s wrap : phase=%s origin=%s row=%2d msg_inv=%d d0n=%2d d0c=%2d applied=%s'
              % (tag4, r4w['phase'], r4w['block_origin'], row4, r4w['msg_cells_edge_invented'],
                 r4w['distance0_naive'], r4w['distance0_corrected'], r4w['applied']))
        print('      %-16s clamp: phase=%s origin=%s msg_inv=%d d0n=%2d d0c=%2d applied=%s '
              'declined=<%s>' % ('', r4c['phase'], r4c['block_origin'],
                                 r4c['msg_cells_edge_invented'], r4c['distance0_naive'],
                                 r4c['distance0_corrected'], r4c['applied'], r4c['declined']))
        if r4c['msg_cells_edge_invented'] > 0:
            EDGE_CASES.append((tag4, r4w, r4c))
    by_edge = [t for t, _w, c in EDGE_CASES if str(c['declined']).startswith('clamp:')]
    contrast = [t for t, w, c in EDGE_CASES if w['applied'] and not c['applied']]
    ok4 = (bool(EDGE_CASES) and len(by_edge) == len(EDGE_CASES) and contrast
           and not [t for t, _w, c in EDGE_CASES if c['applied']])
    check('4 decline-not-confirm', ok4,
          '%d candidate(s) reached invented message cells (%s); clamp declined naming the edge on '
          'all of them, and on %s wrap applied the same read clamp refused'
          % (len(EDGE_CASES), by_edge, contrast)
          if ok4 else 'candidates tried: %d, invented-cell cases: %s, edge-named: %s, '
                      'wrap-confirmed-where-clamp-declined: %s'
                      % (len(cands), [(t, c['msg_cells_edge_invented'], c['applied'])
                                      for t, _w, c in EDGE_CASES], by_edge, contrast))

    predict('5 bad-capture-still-refused', 'item leg (ii): a frame that is off-grid, or smaller '
                                           'than the reference and off-grid, or too small for a '
                                           'glyph, is refused in BOTH modes with applied=False and '
                                           'no exception -- clamp must not make a bad capture '
                                           'guessable')
    w5, h5, rows5 = decay.read_rgb(clean)
    cases = {}
    cases['crop_713x400'] = os.path.join(run, 'c713.ppm')
    decay.write_ppm(cases['crop_713x400'], w5 - 7, h5, [r[:w5 - 7] for r in rows5])
    cases['short_720x390'] = os.path.join(run, 'c390.ppm')
    decay.write_ppm(cases['short_720x390'], w5, h5 - 10, rows5[:h5 - 10])
    cases['tiny_40x32'] = os.path.join(run, 'ctiny.ppm')
    decay.write_ppm(cases['tiny_40x32'], 40, 32, [r[:40] for r in rows5[:32]])
    cases['junk'] = os.path.join(run, 'junk.ppm')
    with open(cases['junk'], 'wb') as fh:
        fh.write(b'P6\nnot a frame\n')
    bad5 = []
    for tag, p in sorted(cases.items()):
        got = {}
        for mode in ('wrap', 'clamp'):
            try:
                rep = al.align(p, mode=mode)
                got[mode] = (bool(rep.get('refused')), rep.get('applied', True))
            except Exception as exc:                       # noqa: BLE001
                got[mode] = ('RAISED %s' % type(exc).__name__, None)
        print('      %-14s wrap=%s clamp=%s' % (tag, got['wrap'], got['clamp']))
        if not (got['wrap'][0] and got['clamp'][0]
                and got['wrap'][1] is False and got['clamp'][1] is False):
            bad5.append((tag, got))
    check('5 bad-capture-still-refused', not bad5,
          '%d bad captures refused identically in both modes' % len(cases)
          if not bad5 else str(bad5))

    predict('6 report-count-is-real', 'item leg (iii), v2. Run 2 measured the OPPOSITE of v1 '
                                      '("the two modes do not report the same score"): on a '
                                      'lost-strip capture both modes scored %d/%d at the same '
                                      'phase, because the strip wrap reaches for is the blacked-out '
                                      'region, which matches no glyph. v2 predicts the agreement '
                                      'and draws the real conclusion: identical scores with a '
                                      'NONZERO invented count are exactly why the count has to be '
                                      'in the report -- "aligned" and "aligned on pixels this '
                                      'capture does not contain" score the same and are not the '
                                      'same claim. The reported count must equal a count taken '
                                      'from the header arithmetic alone, in both modes.' % (1504, 1744))
    f6 = lost_strip(clean, os.path.join(run, 'lost.ppm'), 2 * ch + 2)
    r6w, r6c = al.align(f6, mode='wrap'), al.align(f6, mode='clamp')
    indep_w = invented_geometry(f6, r6w['phase'][0], r6w['phase'][1], cells)
    indep_c = invented_geometry(f6, r6c['phase'][0], r6c['phase'][1], cells)
    print('      wrap : exact=%d/%d inv=%d reported-vs-geometry=%s applied=%s'
          % (r6w['exact_offblock'], r6w['exact_offblock_total'], r6w['cells_edge_invented'],
             (r6w['cells_edge_invented'], indep_w), r6w['applied']))
    print('      clamp: exact=%d/%d inv=%d reported-vs-geometry=%s applied=%s'
          % (r6c['exact_offblock'], r6c['exact_offblock_total'], r6c['cells_edge_invented'],
             (r6c['cells_edge_invented'], indep_c), r6c['applied']))
    check('6 report-count-is-real',
          r6w['cells_edge_invented'] == indep_w and r6c['cells_edge_invented'] == indep_c
          and r6w['cells_edge_invented'] > 0
          and r6c['exact_offblock'] == r6w['exact_offblock']
          and r6c['phase'] == r6w['phase'],
          'both modes scored %d/%d at phase %s while reporting %d invented cells, and that %d is '
          'the same number the header arithmetic gives independently (%s, %s)'
          % (r6w['exact_offblock'], r6w['exact_offblock_total'], r6w['phase'],
             r6w['cells_edge_invented'], r6c['cells_edge_invented'], indep_w, indep_c)
          if (r6w['cells_edge_invented'] == indep_w and r6c['cells_edge_invented'] == indep_c
              and r6w['cells_edge_invented'] > 0) else
          'arithmetic disagrees with the report: wrap (%d,%d) clamp (%d,%d), or the invented count '
          'came out zero and the leg is vacuous'
          % (r6w['cells_edge_invented'], indep_w, r6c['cells_edge_invented'], indep_c))
    REPORTS = disagree + [('lost_strip', r6w, r6c)] + EDGE_CASES

    predict('7 b4-regression', "wrap stays the default and B3/B4's rules are unchanged: the "
                               '9-leg B4 gate, run as-is by a subprocess, still exits 0')
    b4 = subprocess.run([sys.executable, os.path.join(HERE, 'run_bm801_align_gate.py')],
                        capture_output=True, text=True)
    tail = [l for l in b4.stdout.splitlines() if l.startswith('RESULT')]
    check('7 b4-regression', b4.returncode == 0 and bool(tail),
          'rc=%s %s' % (b4.returncode, tail[0] if tail else 'NO RESULT LINE: '
                        + b4.stdout[-200:] + b4.stderr[-200:]))

    predict('8 hard-rules-hold', 'across every report measured above (%d frame pairs, both '
                                 'modes): no applied phase fails to raise the distance-0 count, '
                                 'and NO clamp report whose message row leaned on invented cells '
                                 'was applied -- at least one such report must exist, or this leg '
                                 'is vacuous' % len(REPORTS))
    broke = [(t, m) for t, rw, rc in REPORTS for m, r in (('wrap', rw), ('clamp', rc))
             if r['applied'] and not r['distance0_corrected'] > r['distance0_naive']]
    never_applied = [(t, rc['phase'], rc['msg_cells_edge_invented'])
                     for t, _rw, rc in REPORTS
                     if rc['applied'] and rc['msg_cells_edge_invented']]
    declined_on_edge = [t for t, _rw, rc in REPORTS
                        if rc['mode'] == 'clamp' and rc['msg_cells_edge_invented']
                        and not rc['applied'] and str(rc['declined']).startswith('clamp:')]
    check('8 hard-rules-hold', not broke and not never_applied and bool(declined_on_edge),
          '%d reports checked; increase-only violations %d; clamp-applied-despite-edge %d; '
          'declined-on-edge seen on %s'
          % (1 + 2 * len(REPORTS), len(broke), len(never_applied), declined_on_edge))

    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print('RESULT %d/%d legs pass' % (n_ok, len(RESULTS)))
    shutil.rmtree(run, ignore_errors=True)
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main())
