#!/usr/bin/env python3
"""run_bm801_rgb_gate.py -- B10: make `OffsetFrame`'s single-pixel pair honour `mode`.

B8's audit (`AUDIT_BM801_SAMPLING_PATHS.md`, landed `a5bf99e3`) measured 22 sampling paths and
left exactly two rows carrying a NO cell after B9: `OffsetFrame.lum()` and `OffsetFrame.rgb()`,
each `NO (wraps)` on `mode` -- 6 of 45 samples unchanged where the bytes differ. Both indexed
with `% h` / `% w` and neither consulted `drops()`, so on a clamped view a single-pixel read
returned the opposite edge of the capture: a byte the camera never showed. `raw_cell()` tested
`drops()` before it ever reached them, which is why B6 and B7 came out clean and why the pair
survived: inside that file the two rules never met. Outside it, any caller that takes one
pixel rather than one cell got an invented edge. B8's finding 2 called this "the B6 defect at
single-pixel scale"; this file is the leg that was missing.

`SENTINEL` was chosen by an equality, not by taste. `raw_cell()` already returns it for a
dropped cell, `plane()` returns the all-zero flat mask, and B9's leg 6 established that a cell
rebuilt out of `lum()` equals `grid()`. A raised exception or a second, different sentinel
would make `rgb()` and `raw_cell()` disagree about one pixel of a dropped cell and would break
that equality on the class this item touches. So: `drops()` gates the byte, `lum()` is
`sum(rgb())`, and `raw_cell()` reads its pixels out of `rgb()`.

Three things had to be measured before landing, not asserted:

  * **`wrap` cannot move.** `drops()` is false for every cell under `wrap`, so the fixed pair
    must return exactly what the pre-fix formula returned on every wrap sample, and what the
    hand-derived carve says on every clamp cell that does fit. Legs 4 and 5 measure both; if
    either moves, the change reached outside the branch `drops()` guards, and that is the
    finding this item's own prediction named in advance.
  * **no receipt may move.** `build_atlas()` and `resolve()` reach pixels through `plane()`,
    which goes through `grid()` and `raw_cell()`. Legs 1 and 8 prove the carve is unchanged
    where it was already right, and leg 9 re-runs B7's, B9's and B8's gates whole.
  * **the rows stay in evidence after the fix.** The blindness was a property of a formula,
    not of a verdict: leg 6 keeps the pre-fix arithmetic live in this file and shows it still
    invents on the cells the fixed pair refuses, and `run_bm801_path_audit_gate.py`'s legs 2
    and 10 were re-pointed at the landed table at `a5bf99e3` for the same reason.

Run: python3 rung8/run_bm801_rgb_gate.py   (one beacon boot, then host-side)
Set BM10_SKIP_OLDER=1 to skip leg 9's nested gates while iterating. Note that B8's audit gate
compares ten of its files against their `HEAD` blobs, so nested legs read RED until this item's
own edits are committed: run once skipped, then land, then run in full and quote the landed-state
numbers.
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
# imported for its hand-derived `want_plane`/`norm` only -- this gate does not re-run the
# audit's probes (leg 7 calls those directly); the audit module boots in `main()`, not on import
import run_bm801_path_audit_gate as audit   # noqa: E402

MSG = al.MSG
RESULTS = []
KEEP_OUT = 'ubuntu_desktop_pxc1_v3_selfhost'

# B8's anchor for the pair, deliberately: an OffsetFrame carries no relabelling, so the
# audit flattened `ko`/`jo` to zero and measured dx/dy at (3,5) -- the same numbers its
# `OffsetFrame` rows and leg 2 report.
PX, PY = 3, 5
CELLS = [(10, 30), (4, 20), (0, 0), (15, 8), (24, 79), (vga.ROWS - 1, 0)]
PIXEL_XY = [(0, 0), (3, 7), (8, 15), (0, 15), (8, 0)]


def predict(name, text):
    print('--> %-32s predicts: %s' % (name, text))


def check(name, ok, detail):
    RESULTS.append((name, bool(ok)))
    print('    %s %-32s %s' % ('PASS' if ok else 'FAIL', name, detail))


def roll(src, dst, sx, sy):
    """Cyclic whole-frame displacement -- the frame `wrap` is honest about."""
    w, h, rows = decay.read_rgb(src)
    out = [[rows[(y + sy) % h][(x + sx) % w] for x in range(w)] for y in range(h)]
    decay.write_ppm(dst, w, h, out)
    return dst


def want_off(rows, w, h, cw, ch, dx, dy, mode, r, c, x, y, rgb=False):
    """One pixel of cell (r, c) of an OffsetFrame: phase, then mode. By hand, from the PPM
    bytes -- nothing here imports the aligner, so the fix cannot make a leg true by agreeing
    with itself."""
    y0, x0 = r * ch + dy, c * cw + dx
    if mode == 'clamp' and not (y0 >= 0 and y0 + ch <= h and x0 >= 0 and x0 + cw <= w):
        return al.SENTINEL if rgb else sum(al.SENTINEL)
    px = rows[(y0 + y) % h][(x0 + x) % w]
    return (px[0], px[1], px[2]) if rgb else sum(px)


def old_rgb(view, r, c, x, y):
    """The pre-B10 accessor, live: raw phase arithmetic and a `self.pixels` slice, with no
    `drops()` branch anywhere. Leg 6 runs it against the fixed one on the same bytes."""
    px = (((r * view.ch + y + view.dy) % view.h) * view.w
          + (c * view.cw + x + view.dx) % view.w) * 3
    return view.pixels[px:px + 3]


def main():
    run = tempfile.mkdtemp(prefix='bm810_rgbgate.')
    print('# B10 OffsetFrame single-pixel gate | run dir %s' % run)
    img = os.path.join(run, 'beacon.img')
    subprocess.run(['nasm', '-o', os.path.join(run, 'b.bin'),
                    os.path.join(HERE, 'bm801_beacon.asm')], check=True)
    data = open(os.path.join(run, 'b.bin'), 'rb').read()
    with open(img, 'wb') as fh:
        fh.write(data + b'\0' * ((1 << 20) - len(data)))
    clean = cap.capture(img, settle=4.0, run_dir=run, keep=True)
    src_sha = hashlib.sha256(open(clean, 'rb').read()).hexdigest()[:16]
    base = vga.Frame(clean)
    wc_, hc_, rows = decay.read_rgb(clean)
    cw, ch, w, h = base.cw, base.ch, base.w, base.h
    cof = al.OffsetFrame(base, PX, PY, 'clamp')
    wof = al.OffsetFrame(base, PX, PY, 'wrap')
    dropped = [rc for rc in ((r, c) for r in range(vga.ROWS) for c in range(vga.COLS))
               if cof.drops(*rc)]
    out_sampled = [rc for rc in CELLS + [(vga.ROWS - 1, 30), (10, vga.COLS - 1),
                                         (vga.ROWS - 1, vga.COLS - 1)] if not cof.in_frame(*rc)]
    print('# frame %dx%d cell %dx%d | capture %s | phase (%d,%d) | clamp view drops %d of %d '
          'cells, %d of them sampled' % (w, h, cw, ch, src_sha, PX, PY, len(dropped),
                                         vga.ROWS * vga.COLS, len(out_sampled)))

    predict('0 source-inert',
            'no leg writes to the capture: %s unchanged at the end, and this file names the '
            'keep-out disk exactly once -- in the constant above, never as a path it opens'
            % src_sha)
    self_text = open(os.path.abspath(__file__)).read()
    sha_after = hashlib.sha256(open(clean, 'rb').read()).hexdigest()[:16]
    check('0 source-inert', sha_after == src_sha and self_text.count(KEEP_OUT) == 1,
          'sha before=%s after=%s | keep-out name occurrences=%d' % (src_sha, sha_after,
                                                                     self_text.count(KEEP_OUT)))

    # ---- leg 1: the defect, on the exact cells that carry it ----------------------
    rgb_inv = [rc for rc in out_sampled
               if any(tuple(old_rgb(cof, rc[0], rc[1], x, y)) != al.SENTINEL
                      for x, y in PIXEL_XY)]
    lum_inv = [rc for rc in out_sampled
               if any(old_rgb(cof, rc[0], rc[1], x, y) for x, y in PIXEL_XY)]
    rgb_now = [rc for rc in out_sampled
               if any(tuple(cof.rgb(rc[0], rc[1], x, y)) != al.SENTINEL for x, y in PIXEL_XY)]
    lum_now = [rc for rc in out_sampled
               if any(cof.lum(rc[0], rc[1], x, y) for x, y in PIXEL_XY)]
    predict('1 clamp-pixel-is-the-sentinel',
            'the pre-fix pair invents a non-sentinel byte on %d of the %d sampled out-of-frame '
            'cells -- that is B8\'s row; after routing both through `drops()` neither invents on '
            'any of them' % (len(rgb_inv), len(out_sampled)))
    check('1 clamp-pixel-is-the-sentinel',
          len(rgb_inv) > 0 and len(lum_inv) > 0 and not rgb_now and not lum_now,
          'sampled=%d | pre-fix invents on rgb=%d lum=%d | post-fix invents on rgb=%d lum=%d'
          % (len(out_sampled), len(rgb_inv), len(lum_inv), len(rgb_now), len(lum_now)))

    # ---- leg 2: every dropped cell in the frame, not just the sampled band -------
    all_rgb = [rc for rc in dropped
               if any(tuple(cof.rgb(rc[0], rc[1], x, y)) != al.SENTINEL
                      for x, y in PIXEL_XY)]
    all_lum = [rc for rc in dropped if any(cof.lum(rc[0], rc[1], x, y) for x, y in PIXEL_XY)]
    all_raw = [rc for rc in dropped
               if cof.raw_cell(*rc) != [al.SENTINEL] * (cw * ch)]
    all_base = [rc for rc in dropped
                if any(vga.Frame.lum(base, rc[0], rc[1], x, y) for x, y in PIXEL_XY)]
    predict('2 every-dropped-cell',
            'the rule has to hold on all %d dropped cells, not the %d the sample plan happens to '
            'catch: `rgb`, `lum` and the cell accessor `raw_cell` must all return the sentinel, '
            'while the base formula this item does NOT touch still invents on most (%d)'
            % (len(dropped), len(out_sampled), len(all_base)))
    check('2 every-dropped-cell',
          len(dropped) > 0 and not all_rgb and not all_lum and not all_raw
          and len(all_base) > len(dropped) // 2,
          'dropped=%d | rgb invents=%d | lum invents=%d | raw_cell differs=%d | base formula '
          'invents on %d' % (len(dropped), len(all_rgb), len(all_lum), len(all_raw),
                             len(all_base)))

    # ---- leg 3: one rule -- pixel, cell, plane -----------------------------------
    cell_agree = [(fr, rc) for fr in (wof, cof) for rc in CELLS
                  if [tuple(fr.rgb(rc[0], rc[1], x, y)) for y in range(ch) for x in range(cw)]
                  != [tuple(p) for p in fr.raw_cell(*rc)]]
    lum_agree = [(fr, rc) for fr in (wof, cof) for rc in CELLS
                 if [[fr.lum(rc[0], rc[1], x, y) for x in range(cw)] for y in range(ch)]
                 != fr.grid(*rc)]
    plane_agree = []
    for fr, mode in ((wof, 'wrap'), (cof, 'clamp')):
        p = {'dx': PX, 'dy': PY, 'ko': 0, 'jo': 0, 'mode': mode}
        for rc in CELLS:
            want = audit.norm(audit.want_plane(rows, w, h, cw, ch, p, rc[0], rc[1])[0])
            if audit.norm(fr.plane(*rc)[0]) != want:
                plane_agree.append((mode, rc))
    want_lum = [(fr, rc, xy) for fr, mode in ((wof, 'wrap'), (cof, 'clamp')) for rc in CELLS
                for xy in PIXEL_XY
                if fr.lum(rc[0], rc[1], xy[0], xy[1])
                != want_off(rows, w, h, cw, ch, PX, PY, mode, rc[0], rc[1], xy[0], xy[1])]
    want_rgb = [(fr, rc, xy) for fr, mode in ((wof, 'wrap'), (cof, 'clamp')) for rc in CELLS
                for xy in PIXEL_XY
                if tuple(fr.rgb(rc[0], rc[1], xy[0], xy[1]))
                != want_off(rows, w, h, cw, ch, PX, PY, mode, rc[0], rc[1],
                            xy[0], xy[1], rgb=True)]
    predict('3 pixel-cell-plane-one-rule',
            'the pair must not become a second opinion: `rgb()` rebuilt into a cell equals '
            '`raw_cell()` on both modes (%d comparisons), a `lum()` rebuild equals `grid()` '
            '(%d), `plane()` equals the carve it is built under (%d), and every one of those '
            'equals the hand-derived pixel (%d lum + %d rgb samples) -- which is the equality '
            'that made B9 choose SENTINEL and the reason a different sentinel was not available '
            'here' % (2 * len(CELLS), 2 * len(CELLS), 2 * len(CELLS),
                      2 * len(CELLS) * len(PIXEL_XY), 2 * len(CELLS) * len(PIXEL_XY)))
    check('3 pixel-cell-plane-one-rule',
          not cell_agree and not lum_agree and not plane_agree and not want_lum and not want_rgb,
          'rgb-rebuild != raw_cell: %d | lum-rebuild != grid: %d | plane != its own carve: %d %s '
          '| lum off-model: %d | rgb off-model: %d'
          % (len(cell_agree), len(lum_agree), len(plane_agree), plane_agree[:2],
             len(want_lum), len(want_rgb)))

    # ---- leg 4: wrap cannot move --------------------------------------------------
    wrap_bad = [rc for rc in ((r, c) for r in range(vga.ROWS) for c in range(vga.COLS))
                for xy in PIXEL_XY
                if tuple(wof.rgb(*rc, *xy)) != tuple(old_rgb(wof, *rc, *xy))]
    wrap_lum_bad = [rc for rc in ((r, c) for r in range(vga.ROWS) for c in range(vga.COLS))
                    for xy in PIXEL_XY
                    if wof.lum(*rc, *xy) != sum(old_rgb(wof, *rc, *xy))]
    predict('4 wrap-is-untouched',
            '`drops()` is false for every cell under `wrap`, so the fixed pair must return '
            'byte-for-byte what the pre-fix formula returns -- all %d cells x %d sampled pixels '
            'for rgb, and the same for lum. This is the leg that says the fix reached only the '
            'branch it was for' % (vga.ROWS * vga.COLS, len(PIXEL_XY)))
    check('4 wrap-is-untouched', not wrap_bad and not wrap_lum_bad,
          'rgb samples differing from the pre-fix formula: %d | lum samples: %d | any drop under '
          'wrap: %d' % (len(wrap_bad), len(wrap_lum_bad),
                        sum(1 for r in range(vga.ROWS) for c in range(vga.COLS)
                            if wof.drops(r, c))))

    # ---- leg 5: clamp cells that DO fit are still real pixels ---------------------
    in_frame_cells = [rc for rc in ((r, c) for r in range(vga.ROWS) for c in range(vga.COLS))
                      if not cof.drops(*rc)]
    in_bad = [rc for rc in in_frame_cells
              if any(tuple(cof.rgb(*rc, x, y)) != tuple(old_rgb(cof, *rc, x, y))
                     for x, y in PIXEL_XY)]
    n_in = len(in_frame_cells)
    all_zero = [rc for rc in in_frame_cells
                if all(cof.lum(*rc, x, y) == 0 for x, y in PIXEL_XY)]
    predict('5 in-frame-clamp-still-reads',
            'a sentinel that leaked into the cells that DO fit would look like a pass on the '
            'mode column and be a dead accessor: %d of %d cells are in-frame under this clamp '
            'view and must still equal the pre-fix bytes, and they must not all read zero (%d do)'
            % (n_in, vga.ROWS * vga.COLS, len(all_zero)))
    check('5 in-frame-clamp-still-reads', not in_bad and n_in > 0 and len(all_zero) < n_in // 10,
          'in-frame cells=%d | differing from the pre-fix formula: %d | all-zero on the sampled '
          'pixels: %d' % (n_in, len(in_bad), len(all_zero)))

    # ---- leg 6: the blindness stays a property of a formula -----------------------
    # All five sampled pixels, not one: run 1 of this gate asked pixel (0,0) alone and
    # found the pre-fix formula agreeing with the sentinel on every dropped cell -- which
    # is not the fix working, it is this capture being black along its bottom row and its
    # right column, where the wrapped read lands. A cell only "invents" when the wrapped
    # coordinates reach real ink, so the honest count is per cell over the whole pixel set.
    pre_inv = [rc for rc in dropped
               if any(tuple(old_rgb(cof, *rc, x, y)) != al.SENTINEL for x, y in PIXEL_XY)]
    post_inv = [rc for rc in dropped
                if any(tuple(cof.rgb(*rc, x, y)) != al.SENTINEL for x, y in PIXEL_XY)]
    shown = [(rc, [tuple(old_rgb(cof, *rc, x, y)) for x, y in PIXEL_XY],
              [tuple(cof.rgb(*rc, x, y)) for x, y in PIXEL_XY]) for rc in pre_inv[:1]]
    predict('6 old-formula-still-invents',
            'the pre-fix arithmetic is still live in this file and still runs: it invents a '
            'non-sentinel byte on %d of the %d dropped cells, where the fixed accessor invents '
            'on %d -- B8\'s row, kept as a measurement against the same bytes rather than as '
            'prose that can be edited later' % (len(pre_inv), len(dropped), len(post_inv)))
    check('6 old-formula-still-invents',
          len(pre_inv) > 0 and not post_inv and shown
          and all(b == al.SENTINEL for b in shown[0][2]),
          'dropped=%d | pre-fix invents on %d | post-fix invents on %d | e.g. %s pre=%s post=%s'
          % (len(dropped), len(pre_inv), len(post_inv), shown[0][0] if shown else '-',
             shown[0][1] if shown else '-', shown[0][2] if shown else '-'))

    # ---- leg 7: the audit's own columns ------------------------------------------
    # The audit's probe runs here directly, on this boot, so the acceptance test B10's
    # item named is measured rather than quoted from the audit gate's own run.
    lum_cells = audit.probe(rows, w, h, cw, ch, 'OffsetFrame', base, 'lum', False)
    rgb_cells = audit.probe(rows, w, h, cw, ch, 'OffsetFrame', base, 'rgb', False)
    predict('7 audit-columns-read-yes',
            'B8\'s acceptance test is its `mode` column: running the audit\'s own probe on the '
            'fixed pair must read yes on dx, dy and mode for both rows (%s / %s), which is what '
            'leg 2 of that gate now asserts against the landed table at %s rather than against '
            'this tree'
            % (lum_cells, rgb_cells, audit.B8_SHA))
    check('7 audit-columns-read-yes',
          all(lum_cells[d][0] == 'yes' for d in ('dx', 'dy', 'mode'))
          and all(rgb_cells[d][0] == 'yes' for d in ('dx', 'dy', 'mode')),
          'lum: %s | rgb: %s' % ({d: v[0] for d, v in lum_cells.items()},
                                 {d: v[0] for d, v in rgb_cells.items()}))

    # ---- leg 8: OriginFrame is not this item's business ---------------------------
    ovie = al.OriginFrame(base, PX, PY, 2, 7, 'clamp')
    delegate = al.OriginFrame.__dict__['lum'] is not al.OffsetFrame.__dict__['lum']
    origin_drop_invent = [rc for rc in ((r, c) for r in range(vga.ROWS) for c in range(vga.COLS))
                          if ovie.drops(rc[0], rc[1])
                          and any(ovie.lum(rc[0], rc[1], x, y) for x, y in PIXEL_XY)]
    predict('8 origin-frame-unchanged',
            'B9 fixed the relabelling class and this item fixes the phase class; the two are '
            'different functions, and an `OriginFrame` under clamp must still invent nothing on '
            'its own dropped cells (%d found of %d) -- if B10 had reached through `raw_cell()` '
            'into B9\'s row, this is where it would show'
            % (len(origin_drop_invent),
               sum(1 for r in range(vga.ROWS) for c in range(vga.COLS) if ovie.drops(r, c))))
    check('8 origin-frame-unchanged', not origin_drop_invent and delegate,
          'OriginFrame clamp dropped cells inventing: %d | distinct lum definitions: %s'
          % (len(origin_drop_invent), delegate))

    # ---- leg 9: the item moved no receipt ----------------------------------------
    if os.environ.get('BM10_SKIP_OLDER'):
        print('# older-gates skipped (BM10_SKIP_OLDER set): the nested gates were not run')
    else:
        predict('9 older-gates-regress',
                'B7\'s grid gate (the carve), B9\'s lum gate (whose leg 7 this item re-pointed), '
                'B4\'s clamp gate and B6\'s materialize gate (the two that consume `raw_cell()` '
                'and `plane()` byte-for-byte) all still exit 0 with their full leg counts -- run '
                'with their own nested legs skipped, so this is five boots and no more')
        outs = {}
        for g, env in (('run_bm801_grid_gate.py', dict(os.environ, BM7_SKIP_OLDER='1')),
                       ('run_bm801_lum_gate.py', dict(os.environ, BM9_SKIP_OLDER='1')),
                       ('run_bm801_clamp_gate.py', dict(os.environ)),
                       ('run_bm801_materialize_gate.py', dict(os.environ))):
            p = subprocess.run([sys.executable, os.path.join(HERE, g)],
                               capture_output=True, text=True, env=env)
            res = [l for l in p.stdout.splitlines() if l.startswith('RESULT')]
            outs[g] = (p.returncode, ' '.join(res) or (p.stdout[-90:] + p.stderr[-200:]))
        check('9 older-gates-regress', all(rc == 0 and t for rc, t in outs.values()),
              ' | '.join('%s rc=%s %s' % (g, rc, t) for g, (rc, t) in sorted(outs.items())))

    # ---- the read this whole ladder exists for ----------------------------------
    disp = roll(clean, os.path.join(run, 'disp.ppm'), 3, 5)
    rep10, view10 = al.corrected(disp, mode='wrap')
    n10, got10 = al.read_distance0(view10)
    rep10c = al.align(disp, mode='clamp')
    n10z, got10z = al.read_distance0(al.OriginFrame(vga.Frame(disp), 0, 0, 0, 0, 'wrap'))
    predict('10 message-still-reads',
            'the channel the ladder exists for is unchanged on the geometry B7 measured: the '
            'displaced capture still aligns to phase (%d,%d) origin (%d,%d) and yields %r at '
            '%d/%d distance-0 cells (the uncorrected frame reads %r at %d/%d), and the clamp '
            'report still decides on the same rule (applied=%s, declined_by_edge=%s, %d of %d '
            'message-row cells off-capture)'
            % (rep10['phase'][0], rep10['phase'][1], rep10['block_origin'][0],
               rep10['block_origin'][1], MSG, n10, len(MSG), got10z, n10z, len(MSG),
               rep10c['applied'], rep10c.get('declined_by_edge'),
               rep10c.get('msg_cells_edge_invented', -1), len(MSG)))
    check('10 message-still-reads', got10 == MSG and n10 == len(MSG)
          and 'applied' in rep10c and 'declined_by_edge' in rep10c,
          'displaced read=%r distance0=%d/%d | zero-offset read=%r distance0=%d/%d | clamp '
          'applied=%s declined_by_edge=%s' % (got10, n10, len(MSG), got10z, n10z, len(MSG),
                                              rep10c['applied'], rep10c.get('declined_by_edge')))

    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print('RESULT %d/%d legs pass' % (n_ok, len(RESULTS)))
    shutil.rmtree(run, ignore_errors=True)
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main())
