#!/usr/bin/env python3
"""bm801_reader_decay.py -- where the VGA receipt reader stops being trustworthy.

`RECEIPT_BM801_CHANNEL.md` names its own gap: a capture off a real monitor is
not a screendump. This measures that gap instead of waving at it -- degrade a
known frame along four axes and ask, at each level, not "is the answer right?"
but "when it is wrong, does the reader SAY so?". A receipt channel is allowed to
be defeated by a bad picture. It is not allowed to confirm a wrong message with
a clean bill of health.

The pass criterion is therefore zero silent high-confidence misreads, per mode,
and the product is a measured trust boundary -- which knob fails first, and at
what level. Predictions print before measurement, including the one that this
run exists to test: sub-pixel misalignment should fail first, because a
mis-gridded frame still divides evenly and so walks straight past
pitch_is_exact().

Run: python3 rung8/bm801_reader_decay.py            (one qemu boot, ~25 s)
"""

import math
import os
import random
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bm801_capture as cap      # noqa: E402
import bm801_vga as vga          # noqa: E402

MSG = 'BM801-RECEIPT-OK>0123456789ABCDEF'
FLAT_SPAN = vga.FLAT_SPAN
RESULTS = []
ROWS = []


def write_ppm(path, w, h, rows):
    flat = bytearray()
    for row in rows:
        for px in row:
            flat += bytes(max(0, min(255, int(c))) for c in px)
    with open(path, 'wb') as fh:
        fh.write(b'P6\n%d %d\n255\n' % (w, h))
        fh.write(flat)


def read_rgb(path):
    """Pixels as (r,g,b) triples in a row-major list, plus the header dimensions."""
    w, h, body = vga.parse_ppm(path)
    rows = [[list(body[(y * w + x) * 3:(y * w + x) * 3 + 3]) for x in range(w)]
            for y in range(h)]
    return w, h, rows


def bilinear(rows, w, h, nw, nh):
    src = [[tuple(v) for v in row] for row in rows]
    out = []
    for y in range(nh):
        sy = min(h - 1, max(0, int(math.floor((y + 0.5) * h / nh))))
        sy1 = min(h - 1, sy + 1)
        fy = (y + 0.5) * h / nh - sy
        row = []
        for x in range(nw):
            sx = min(w - 1, max(0, int(math.floor((x + 0.5) * w / nw))))
            sx1 = min(w - 1, sx + 1)
            fx = (x + 0.5) * w / nw - sx
            px = src[sy][sx]
            qx = src[sy][sx1]
            rx = src[sy1][sx]
            sx2 = src[sy1][sx1]
            row.append(tuple(int(round(px[c] * (1 - fx) * (1 - fy) + qx[c] * fx * (1 - fy) +
                                             rx[c] * (1 - fx) * fy + sx2[c] * fx * fy))
                             for c in range(3)))
        out.append([list(p) for p in row])
    return out


def degrade(src_ppm, dst_ppm, scale=None, shift=0, noise=0, contrast=None, crop_edge=0):
    """Apply the named degradations and write a new frame. Returns the applied knobs."""
    w, h, rows = read_rgb(src_ppm)
    applied = {'scale': scale, 'shift': shift, 'noise': noise, 'contrast': contrast,
               'crop_edge': crop_edge}
    if contrast is not None:
        for row in rows:
            for px in row:
                for c in range(3):
                    px[c] = int(round(128 + (px[c] - 128) * contrast))
    if crop_edge:
        rows = [[px for px in row[crop_edge:w - crop_edge]] for row in rows[crop_edge:h - crop_edge]]
        w, h = w - 2 * crop_edge, h - 2 * crop_edge
    if shift:
        rows = [[rows[y][(x + shift) % w] for x in range(w)] for y in range(h)]
    if scale and scale != 1.0:
        rows = bilinear(rows, w, h, max(8, int(w * scale)), max(8, int(h * scale)))
        w, h = len(rows[0]), len(rows)
    if noise:
        rnd = random.Random(20260921)
        for row in rows:
            for px in row:
                for c in range(3):
                    px[c] = max(0, min(255, px[c] + rnd.randint(-noise, noise)))
    if scale and scale != 1.0:
        rows = bilinear(rows, w, h, 720, 400)
        w, h = 720, 400
    write_ppm(dst_ppm, w, h, rows)
    return applied


def verdict(frame_path):
    """Read the message off a degraded frame. Never raises -- refusing IS the result."""
    try:
        f = vga.Frame(frame_path)
    except Exception as exc:                        # noqa: BLE001 - the reader's own refusal
        return {'outcome': 'REFUSED-AT-PARSE', 'why': str(exc)[:70], 'wrong': None,
                'worst_dist': None}
    if not f.pitch_is_exact():
        return {'outcome': 'REFUSED-PITCH', 'why': '%dx%d not divisible by 80x25' % (f.w, f.h),
                'wrong': None, 'worst_dist': None}
    atlas = vga.build_atlas(f)
    got, cells = vga.read_line(f, atlas, vga.MSG_ROW, len(MSG))
    dists = [c['dist'] for c in cells if c]
    unres = sum(1 for c in cells if c is None)
    ties = sum(1 for c in cells if c and c['ties'] and len(c['ties']) > 1)
    gaps = [c['runner_dist'] - c['dist'] for c in cells
            if c and c.get('runner_dist') is not None]
    worst_gap = min(gaps) if gaps else None
    return {'outcome': 'CONFIRMED' if got == MSG else 'MISREAD',
            'why': '' if got == MSG else 'read %r' % got,
            'wrong': None if got == MSG else sum(1 for a, b in zip(got, MSG) if a != b),
            'worst_dist': max(dists) if dists else None,
            'unresolved': unres, 'tied': ties, 'worst_gap': worst_gap}


def sweep(run_dir, ppm, name, values, **fixed):
    print('--> %-14s predicts: %s' % (name, PREDICTIONS[name]))
    silent = None
    ran = 0
    for v in values:
        dst = os.path.join(run_dir, 'deg_%s_%s.ppm' % (name, str(v).replace('.', 'p')))
        knobs = dict(fixed)
        knobs[name] = v
        try:
            degrade(ppm, dst, **knobs)
        except Exception as exc:                    # noqa: BLE001
            print('    %-8s DEGRADE-FAILED %s: %s' % (v, type(exc).__name__, exc))
            continue
        r = verdict(dst)
        first_wrong = r['outcome'] == 'MISREAD'
        print('    %-8s %-14s worst_dist=%-5s worst_gap=%-5s wrong=%-5s unresolved=%-3s '
              'tied=%-3s %s' %
              (v, r['outcome'], r.get('worst_dist'), r.get('worst_gap'), r.get('wrong'),
               r.get('unresolved', 0), r.get('tied', 0), r['why']))
        if first_wrong and r.get('worst_dist') == 0 and not r.get('tied'):
            silent = v
        ROWS.append((name, v, r))
        ran += 1
    if not ran:
        print('    FAIL %-14s no level in this sweep produced a frame -- a sweep that never '
              'ran cannot report a pass' % name)
        RESULTS.append((name, False))
        return None
    ok = silent is None
    RESULTS.append((name, ok))
    print('    %s %-14s %s' % ('PASS' if ok else 'FAIL', name,
                               'no silent high-confidence misread in this sweep'
                               if ok else 'SILENT MISREAD at %s -- confirmed a wrong message with '
                                          'distance 0 and no tie' % silent))
    return silent


PREDICTIONS = {
    'scale': 'resolution loss degrades into unresolved/tied cells before a confident wrong glyph',
    'shift': 'a whole-frame shift is a misaligned grid: expected to be the FIRST confident '
             'misread, and pitch_is_exact will not catch it, so the margin must',
    'noise': 'additive noise raises distances (low margin is the warning), never distance 0',
    'contrast': 'contrast collapse hits the flat-cell rule first: cells become unresolved, not wrong',
    'crop_edge': 'cropping the frame changes its size, so it must be refused at parse or at pitch',
}


def main():
    run_dir = tempfile.mkdtemp(prefix='bm801_decay.')
    print('# bm801 reader-decay sweep | run dir %s' % run_dir)
    img = os.path.join(run_dir, 'beacon.img')
    subprocess_run_nasm(run_dir, img)
    ppm = cap.capture(img, settle=4.0, run_dir=run_dir, keep=True)
    base = verdict(ppm)
    print('baseline (undegraded): %s %s' % (base['outcome'], base['why']))
    if base['outcome'] != 'CONFIRMED':
        print('FAIL the sweep is meaningless if the clean frame does not read')
        return 1
    sweep(run_dir, ppm, 'contrast', [1.0, 0.5, 0.2, 0.1, 0.05])
    sweep(run_dir, ppm, 'noise', [0, 6, 16, 32, 64, 96])
    sweep(run_dir, ppm, 'scale', [1.0, 0.5, 0.34, 0.25, 0.125])
    sweep(run_dir, ppm, 'shift', [0, 1, 2, 4, 9])
    sweep(run_dir, ppm, 'crop_edge', [0, 1, 7, 31])
    wrong = [r for _n, _v, r in ROWS if r['outcome'] == 'MISREAD']
    right = [r for _n, _v, r in ROWS if r['outcome'] == 'CONFIRMED']
    floor = min((r['worst_dist'] for r in wrong), default=None)
    broke = len(wrong)
    # The acceptance rule this sweep exists to evaluate: a receipt counts ONLY when every
    # cell matches its atlas entry exactly. Scored on wrong-but-accepted (must be zero);
    # right-but-refined is a false rejection, which costs a re-look and is reported, not
    # failed on -- a receipt that declines is a different thing from a receipt that lies.
    accepted_wrong = [(n, v) for n, v, r in ROWS
                      if r.get('worst_dist') == 0 and r['outcome'] != 'CONFIRMED']
    accepted_right = [(n, v) for n, v, r in ROWS
                      if r.get('worst_dist') == 0 and r['outcome'] == 'CONFIRMED']
    declined_right = [(n, v, r['worst_dist']) for n, v, r in ROWS
                      if r['outcome'] == 'CONFIRMED' and r.get('worst_dist') != 0]
    g_wrong = [r['worst_gap'] for r in wrong if r.get('worst_gap') is not None]
    g_right = [r['worst_gap'] for _n, _v, r in ROWS
               if r['outcome'] == 'CONFIRMED' and r.get('worst_gap') is not None]
    print('    separation by raw distance : wrong reads %s..%s, correct reads %s..%s' %
          (min((r['worst_dist'] for r in wrong), default='-'),
           max((r['worst_dist'] for r in wrong), default='-'),
           min((r['worst_dist'] for r in right), default='-'),
           max((r['worst_dist'] for r in right), default='-')))
    print('    separation by runner-up gap: wrong reads %s..%s, correct reads %s..%s' %
          (min(g_wrong, default='-'), max(g_wrong, default='-'),
           min(g_right, default='-'), max(g_right, default='-')))
    print('--> %-14s predicts: the exact-match rule accepts %d levels and 0 of them wrong; '
          'it declines %d levels that were in fact read right, and the number that matters '
          'is the first one' % ('accept-rule', len(accepted_right) + len(accepted_wrong),
                                len(declined_right)))
    ok_rule = not accepted_wrong and broke >= 1 and len(accepted_right) >= 1
    print('    %s accept-rule    accepted=%d (wrong among them: %d), declined-though-right=%d, '
          'levels that broke the reader=%d' %
          ('PASS' if ok_rule else 'FAIL', len(accepted_right) + len(accepted_wrong),
           len(accepted_wrong), len(declined_right), broke))
    print('    declined-though-right levels: %s' % declined_right)
    RESULTS.append(('accept-rule', ok_rule))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print('RESULT %d/%d sweeps show no silent misread' % (n_ok, len(RESULTS)))
    return 0 if n_ok == len(RESULTS) else 1


def subprocess_run_nasm(run_dir, img):
    import subprocess
    binf = os.path.join(run_dir, 'b.bin')
    subprocess.run(['nasm', '-o', binf, os.path.join(HERE, 'bm801_beacon.asm')], check=True)
    data = open(binf, 'rb').read()
    with open(img, 'wb') as fh:
        fh.write(data + b'\0' * ((1 << 20) - len(data)))


if __name__ == '__main__':
    sys.exit(main())
