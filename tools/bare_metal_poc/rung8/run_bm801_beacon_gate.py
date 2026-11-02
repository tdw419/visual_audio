#!/usr/bin/env python3
"""run_bm801_beacon_gate.py -- gate the VGA-text receipt channel in emulation.

TASK_BM801 is blocked on a physical x86 box, but its receipt channel is not:
"fallback candidate: VGA text beacon verified by XOR-diff glyph matching, not
OCR" is a host-side reader, and it can be built, falsified and measured here.
Each leg prints its prediction before it measures, so a leg cannot be re-tuned
to fit its own result. rc=0 only if every leg holds.

Run: python3 run_bm801_beacon_gate.py [--keep]     (~6 qemu boots)
"""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bm801_capture as cap     # noqa: E402
import bm801_vga as vga         # noqa: E402

MSG = 'BM801-RECEIPT-OK>0123456789ABCDEF'
FILL_CODE = 0xB0
RESULTS = []


def leg(name, prediction, ok, detail):
    print('%-3s %-26s %s' % ('PASS' if ok else 'FAIL', name, detail))
    RESULTS.append((name, ok))
    return ok


def predict(name, text):
    print('--> %-26s predicts: %s' % (name, text))


def build_medium(dst_dir):
    asm = os.path.join(HERE, 'bm801_beacon.asm')
    binf = os.path.join(dst_dir, 'bm801_beacon.bin')
    subprocess.run(['nasm', '-o', binf, asm], check=True)
    img = os.path.join(dst_dir, 'beacon.img')
    with open(img, 'wb') as fh:
        fh.write(open(binf, 'rb').read())
        fh.write(b'\0' * (1024 * 1024 - os.path.getsize(binf)))
    return img


def nearest(plane, atlas):
    scored = sorted((vga.hamming(plane, p), c) for c, (p, f) in atlas.items() if not f)
    return scored[0][1], scored[0][0], (scored[1][1], scored[1][0])


def main():
    keep = '--keep' in sys.argv
    run_dir = tempfile.mkdtemp(prefix='bm801_gate.')
    print('# bm801 beacon gate | run dir %s' % run_dir)
    try:
        img = build_medium(run_dir)

        predict('carve', 'the frame divides exactly into 80x25 cells, and the ink profile says '
                         'which columns of the cell are live (an 8-wide carve would drop column 8)')
        ppm1 = cap.capture(img, settle=4.0, run_dir=run_dir, keep=True)
        ppm1 = _stash(run_dir, ppm1, 'boot1.ppm') if keep else ppm1
        f1 = vga.Frame(ppm1)
        prof = f1.ink_profile()
        live = [x for x, v in enumerate(prof) if v]
        leg('carve', None, f1.pitch_is_exact() and live == list(range(f1.cw)),
            'frame %dx%d cell %dx%d, live columns %s (last carries %d of the total ink span)' %
            (f1.w, f1.h, f1.cw, f1.ch, live, prof[-1]))
        atlas = vga.build_atlas(f1)

        predict('A identity', 'row 20 reads back %r with every cell at xor-distance 0' % MSG)
        got1, cells1 = vga.read_line(f1, atlas, vga.MSG_ROW, len(MSG))
        d1 = [c['dist'] for c in cells1 if c]
        leg('A identity', None, got1 == MSG and max(d1) == 0 and len(cells1) == len(MSG),
            'read %r, %d cells, distances min/max %d/%d' % (got1, len(cells1), min(d1), max(d1)))

        predict('B colour-blind', 'row 21 carries the same glyphs in two other colours and '
                                  'still resolves at distance 0')
        got2, cells2 = vga.read_line(f1, atlas, vga.MSG2_ROW, len(MSG))
        d2 = [c['dist'] for c in cells2 if c]
        fillres = vga.resolve(f1, atlas, 0, vga.ATLAS_SIDE)
        leg('B colour-blind', None,
            got2 == MSG and max(d2) == 0 and fillres and fillres['code'] == FILL_CODE and fillres['dist'] == 0,
            'row21 %r (dist<=%d); off-layout fill cell -> %s' %
            (got2, max(d2),
             'FLAT (unreadable)' if fillres is None else
             '0x%02X at dist %d' % (fillres['code'], fillres['dist'])))

        predict('C atlas-ambiguity', 'the %d beacon glyphs are pairwise unique bitmaps; report how '
                                     'many of the 256 codes are NOT' % len(set(MSG)))
        shared, _ = vga.ambiguity(atlas)
        dup_codes = sorted({c for cs in shared.values() for c in cs})
        flat_codes = sorted(c for c, (_p, fl) in atlas.items() if fl)
        used = sorted({ord(ch) for ch in MSG})
        collide = [c for c in used if any(c in cs for cs in shared.values())]
        leg('C atlas-ambiguity', None, not collide,
            '%d codes share a bitmap across %d planes; flat codes %s; %d beacon codes, %d of them ambiguous'
            % (len(dup_codes), len(shared), [hex(c) for c in flat_codes], len(used), len(collide)))

        predict('D noise-margin', 'report, not assert: how many pixels must corrupt a cell before '
                                  'the reader switches to a different glyph')
        margins, flip_at_first = [], []
        for c in range(len(MSG)):
            plane, _ = f1.plane(vga.MSG_ROW, c)
            base_code = vga.resolve(f1, atlas, vga.MSG_ROW, c)['code']
            first_flip = None
            for n in range(1, 13):
                p2 = _flip(plane, n)
                code, dist, _r = nearest(p2, atlas)
                if code != base_code and first_flip is None:
                    first_flip = n
            # the smallest perturbation that survives: distance at n=1
            p1 = _flip(plane, 1)
            _c, d_at_1, _r = nearest(p1, atlas)
            margins.append(d_at_1)
            flip_at_first.append(first_flip)
        never = [c for c in range(len(MSG)) if flip_at_first[c] is None]
        leg('D noise-margin', None, min(margins) >= 1,
            'distance after 1 flipped pixel: min %d, median %d; first misread at k in %s; %d/%d cells never '
            'misread within k<=12 (%s)' %
            (min(margins), sorted(margins)[len(margins) // 2],
             sorted(set(n for n in flip_at_first if n)), len(never), len(MSG),
             'all cells' if len(never) == len(MSG) else never))

        predict('E negative-control', 'a reader holding the wrong font must NOT confirm the message')
        shifted = {(c + 1) % 256: atlas[c] for c in atlas}
        got_e, _ = vga.read_line(f1, shifted, vga.MSG_ROW, len(MSG))
        shifted_ok = got_e != MSG
        # and the shifted reader must still be a reader: it resolves the code it holds
        _code_s, dist_s, _ = nearest(atlas[ord('B')][0], shifted)
        leg('E negative-control', None, shifted_ok,
            'atlas-shifted-by-one reads %r (differs from truth: %s); a held glyph is still found at dist %d'
            % (got_e, got_e != MSG, dist_s))

        predict('F determinism', 'a second boot of the same image gives all %d cell planes identical'
                                 % (vga.COLS * vga.ROWS))
        ppm2 = cap.capture(img, settle=4.0, run_dir=run_dir, keep=True)
        f2 = vga.Frame(ppm2)
        diffs = [(r, c) for r in range(vga.ROWS) for c in range(vga.COLS)
                 if f1.plane(r, c) != f2.plane(r, c)]
        leg('F determinism', None, not diffs,
            '%d of %d cells differ between boots' % (len(diffs), vga.ROWS * vga.COLS))

        n_ok = sum(1 for _, ok in RESULTS if ok)
        print('RESULT %d/%d legs pass' % (n_ok, len(RESULTS)))
        if keep:
            print('# artifacts kept in %s' % run_dir)
        else:
            shutil.rmtree(run_dir, ignore_errors=True)
        return 0 if n_ok == len(RESULTS) else 1
    finally:
        if not keep:
            shutil.rmtree(run_dir, ignore_errors=True)


def _flip(plane, n):
    """Flip n pixels at fixed positions so the sweep is reproducible."""
    idx = [(i * 37 + 11) % len(plane) for i in range(n)]
    out = list(plane)
    for i in idx:
        out[i] ^= 1
    return tuple(out)


def _stash(run_dir, path, name):
    dst = os.path.join(run_dir, name)
    shutil.copy(path, dst)
    return dst


if __name__ == '__main__':
    sys.exit(main())
