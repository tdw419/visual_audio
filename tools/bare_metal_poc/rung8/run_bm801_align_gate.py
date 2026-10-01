#!/usr/bin/env python3
"""run_bm801_align_gate.py -- B4: does the grid aligner fix misreads without cheating?

The claim under test is narrow: a capture displaced by up to a cell in each axis
still yields the exact receipt string, and the aligner's correction is admissible
only when it strictly increases the number of cells the reader matches exactly.
The second half is the dangerous one -- a search that maximises any score will
find one, so every leg here prints its prediction before it measures, and the
increase-only rule is checked on frames where the aligner has every incentive to
over-reach (a clean frame, and a frame whose phase is already right).

One boot, then all legs are host-side pixel work. Exit 0 only if every leg passes.

Run: python3 rung8/run_bm801_align_gate.py
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
import bm801_vga as vga         # noqa: E402
import bm801_reader_decay as decay   # noqa: E402

MSG = al.MSG
RESULTS = []


def predict(name, text):
    print('--> %-22s predicts: %s' % (name, text))


def check(name, ok, detail):
    RESULTS.append((name, bool(ok)))
    print('    %s %-22s %s' % ('PASS' if ok else 'FAIL', name, detail))


def roll(src, dst, sx, sy):
    """Cyclic whole-frame displacement, the same knob B3 used, widened to two axes."""
    w, h, rows = decay.read_rgb(src)
    out = [[rows[(y + sy) % h][(x + sx) % w] for x in range(w)] for y in range(h)]
    decay.write_ppm(dst, w, h, out)
    return dst


def sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()[:16]


def main():
    run = tempfile.mkdtemp(prefix='bm801_aligegate.')
    print('# B4 grid-alignment gate | run dir %s' % run)
    img = os.path.join(run, 'beacon.img')
    subprocess.run(['nasm', '-o', os.path.join(run, 'b.bin'),
                    os.path.join(HERE, 'bm801_beacon.asm')], check=True)
    data = open(os.path.join(run, 'b.bin'), 'rb').read()
    with open(img, 'wb') as fh:
        fh.write(data + b'\0' * ((1 << 20) - len(data)))
    clean = cap.capture(img, settle=4.0, run_dir=run, keep=True)

    predict('0 input-untouched', 'align() reads pixels only: the frame sha256 is identical after')
    h0 = sha(clean)
    al.align(clean)
    check('0 input-untouched', sha(clean) == h0, 'before=%s after=%s' % (h0, sha(clean)))

    predict('1 clean-frame-decline', 'a correct frame must be LEFT ALONE: applied=False, phase '
                                     '(0,0), and the uncorrected read already exact on all %d cells'
            % len(MSG))
    r1 = al.align(clean)
    check('1 clean-frame-decline',
          r1['applied'] is False and r1['phase'] == (0, 0) and r1['block_origin'] == (0, 0)
          and r1['distance0_naive'] == len(MSG),
          'applied=%s phase=%s origin=%s distance0_naive=%d declined=<%s>'
          % (r1['applied'], r1['phase'], r1['block_origin'], r1['distance0_naive'], r1['declined']))

    predict('2 sub-pixel-recovery', 'for shifts (1,0) (2,0) (0,1) (0,3) (1,2) (2,7): each finds '
                                    'phase = (-s) mod cell, registers the block, and reads the '
                                    'message exactly (distance0 = %d)' % len(MSG))
    REPS = [('clean', r1)]
    cw, ch = int(r1['cell'].split('x')[0]), int(r1['cell'].split('x')[1])
    bad2 = []
    for sx, sy in [(1, 0), (2, 0), (0, 1), (0, 3), (1, 2), (2, 7)]:
        f = roll(clean, os.path.join(run, 'roll_%d_%d.ppm' % (sx, sy)), sx, sy)
        rep = al.align(f)
        REPS.append(('roll(%d,%d)' % (sx, sy), rep))
        want_phase = ((-sx) % cw, (-sy) % ch)
        ok = rep['read_corrected'] == MSG and rep['distance0_corrected'] == len(MSG) and rep['applied']
        print('      roll(%d,%d) phase=%s want_phase=%s origin=%s naive=%d corrected=%d applied=%s'
              % (sx, sy, rep['phase'], want_phase, rep['block_origin'], rep['distance0_naive'],
                 rep['distance0_corrected'], rep['applied']))
        if not ok:
            bad2.append((sx, sy, rep['read_corrected']))
        if rep['phase'] != want_phase:
            print('      NOTE phase %s is not the inverse %s: a different grid is consistent '
                  'with this frame' % (rep['phase'], want_phase))
    check('2 sub-pixel-recovery', not bad2, 'all six rolls read exactly' if not bad2 else str(bad2))

    predict('3 whole-cell-slide', 'a 9-px horizontal slide is pitch-aligned so the phase search '
                                  'finds (0,0); only the block registration can fix it, and the '
                                  'fill-count window must name it')
    f = roll(clean, os.path.join(run, 'roll_9_0.ppm'), 9, 0)
    r3 = al.align(f)
    REPS.append(('roll(9,0)', r3))
    check('3 whole-cell-slide',
          r3['phase'] == (0, 0) and r3['read_corrected'] == MSG and r3['applied']
          and r3['fill_cells_in_window'] < r3['fill_cells_total'],
          'phase=%s origin=%s fill_in_window=%d of %d naive=%d corrected=%d read=%r'
          % (r3['phase'], r3['block_origin'], r3['fill_cells_in_window'], r3['fill_cells_total'],
             r3['distance0_naive'], r3['distance0_corrected'], r3['read_corrected']))

    predict('4 increase-only', 'on a degraded-but-aligned frame the search may propose a phase; '
                               'it must never apply one that does not raise the exact-cell count, '
                               'so applied=True implies corrected > naive, always')
    bad4 = []
    for noise in (0, 6, 16, 32):
        d = os.path.join(run, 'noise_%d.ppm' % noise)
        decay.degrade(clean, d, noise=noise)
        rep = al.align(d)
        REPS.append(('noise(%d)' % noise, rep))
        viol = rep['applied'] and not rep['distance0_corrected'] > rep['distance0_naive']
        print('      noise=%-3d phase=%s origin=%s exact_offblock=%d/%d naive=%d corrected=%d '
              'applied=%s' % (noise, rep['phase'], rep['block_origin'], rep['exact_offblock'],
                              rep['exact_offblock_total'], rep['distance0_naive'],
                              rep['distance0_corrected'], rep['applied']))
        if viol:
            bad4.append(noise)
    check('4 increase-only', not bad4,
          'no correction ever lowered the exact-cell count' if not bad4 else 'VIOLATION %s' % bad4)

    predict('5 never-worse', 'across the %d frames already measured, the reported corrected count '
                             'is never below the naive one -- the aligner may decline, but it may '
                             'not talk itself into a worse read' % len(REPS))
    worse = [(tag, rep['distance0_naive'], rep['distance0_corrected'])
             for tag, rep in REPS
             if not rep.get('refused')
             and rep['distance0_corrected'] < rep['distance0_naive']]
    check('5 never-worse', not worse,
          '%d frames, none made worse; %d declined' % (len(REPS), sum(1 for _t, r in REPS
                                                                     if not r['applied']))
          if not worse else str(worse))

    predict('6 materialised-frame', 'the correction is a fact about pixels, not a story the report '
                                    'tells: writing the corrected view out and reading it with the '
                                    'UNMODIFIED bm801_vga.Frame gives the exact string too, and an '
                                    'identity view writes the source bytes back unchanged')
    f6 = roll(clean, os.path.join(run, 'roll_4_5.ppm'), 4, 5)
    rep6, view = al.corrected(f6)
    out6 = os.path.join(run, 'corrected.ppm')
    al.materialize(view, out6)
    id6 = os.path.join(run, 'identity.ppm')
    al.materialize(al.OriginFrame(vga.Frame(clean)), id6)
    identical = open(clean, 'rb').read() == open(id6, 'rb').read()
    fr = vga.Frame(out6)
    got6, cells6 = vga.read_line(fr, vga.build_atlas(fr), vga.MSG_ROW, len(MSG))
    check('6 materialised-frame', got6 == MSG and fr.pitch_is_exact()
          and all(c and c['dist'] == 0 for c in cells6) and identical,
          'phase=%s origin=%s read=%r exact_cells=%d/%d identity-write-byte-identical=%s'
          % (rep6['phase'], rep6['block_origin'], got6,
             sum(1 for c in cells6 if c and c['dist'] == 0), len(MSG), identical))

    predict('7 refusal', 'a frame whose pitch does not divide is refused outright, applied=False, '
                         'no exception -- the aligner must not guess a grid onto a bad capture')
    w, h, rows = decay.read_rgb(clean)
    trunc = os.path.join(run, 'trunc.ppm')
    decay.write_ppm(trunc, w - 7, h, [r[:w - 7] for r in rows])
    r7 = al.align(trunc)
    junk = os.path.join(run, 'junk.ppm')
    with open(junk, 'wb') as fh:
        fh.write(b'P6\nnot a frame\n')
    r7b = al.align(junk)
    check('7 refusal', r7.get('refused') and r7['applied'] is False
          and r7b.get('refused') and r7b['applied'] is False,
          'pitch=<%s> parse=<%s>' % (str(r7.get('refused'))[:60], str(r7b.get('refused'))[:60]))

    predict('8 guard-fires', 'a frame whose two halves disagree (the atlas half rolled by 2, the '
                             'message half left alone) must make the search PROPOSE a nonzero '
                             'phase and the guard decline it -- and the report must still name '
                             'the phase it found, because that is the operator\'s evidence')
    w8, h8, rows8 = decay.read_rgb(clean)
    half = os.path.join(run, 'halfroll.ppm')
    decay.write_ppm(half, w8, h8,
                    [[rows8[y][(x + 2) % w8] if y < 20 * 16 else rows8[y][x] for x in range(w8)]
                     for y in range(h8)])
    r8 = al.align(half)
    REPS.append(('halfroll', r8))
    check('8 guard-fires',
          r8['applied'] is False and r8['phase'] != (0, 0) and r8['declined']
          and r8['distance0_corrected'] <= r8['distance0_naive'],
          'phase=%s origin=%s exact_offblock=%d (at zero %d) naive=%d corrected=%d applied=%s'
          % (r8['phase'], r8['block_origin'], r8['exact_offblock'], r8['exact_offblock_at_zero'],
             r8['distance0_naive'], r8['distance0_corrected'], r8['applied']))

    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print('RESULT %d/%d legs pass' % (n_ok, len(RESULTS)))
    shutil.rmtree(run, ignore_errors=True)
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main())
