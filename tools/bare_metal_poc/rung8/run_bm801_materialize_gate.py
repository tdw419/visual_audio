#!/usr/bin/env python3
"""run_bm801_materialize_gate.py -- B6: does the written file obey the mode that authorized it?

`materialize()` (`rung8/bm801_align.py:236` before this item) hand-rolled its own
pixel indices with `% view.h` / `% view.w` and never called `plane()`, which is where
B5's clamp rule lives. So the aligner's DECISION and the aligner's OUTPUT were
produced by two different sampling rules: a clamp report carrying
`cells_edge_invented=0` could authorize a file full of opposite-edge pixels. B5's
receipt named exactly this as the first thing it does not fix.

Run 1 of this gate, against the code as it then stood, measured the RED and refuted
two of this file's own predictions; both are kept in the predictions below and in
`RECEIPT_BM801_MATERIALIZE.md`:
  * byte-difference counts are NOT the cell count times the cell area -- a source
    pixel already black coincides with the sentinel -- so every count here is taken
    cell-wise, and the byte figure is reported alongside, not asserted;
  * "a clamp view with an in-frame message row still reads the receipt" was assumed
    of the phase CLAMP chose, and clamp's lower score moves the winner, so that view
    read 30/33 garbage. Legs 3 and 4 now take the phase WRAP was accepted at and
    re-bind only the mode, which is also the only way to show the fix is bound to the
    mode rather than to a new default.

Run: python3 rung8/run_bm801_materialize_gate.py    (one beacon boot, then host-side)
Set BM6_SKIP_OLDER=1 to skip leg 8's two nested gates while iterating (legs 0-7
carry the rule; leg 8 is the regression check on B4's and B5's gates).
"""

import hashlib
import inspect
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
EDGE_ROW = 0                   # the row B5's leg 4 measured all-33-invented on
RESULTS = []


def predict(name, text):
    print('--> %-28s predicts: %s' % (name, text))


def check(name, ok, detail):
    RESULTS.append((name, bool(ok)))
    print('    %s %-28s %s' % ('PASS' if ok else 'FAIL', name, detail))


def roll(src, dst, sx, sy):
    """Cyclic whole-frame displacement -- the frame `wrap` is honest about."""
    w, h, rows = decay.read_rgb(src)
    out = [[rows[(y + sy) % h][(x + sx) % w] for x in range(w)] for y in range(h)]
    decay.write_ppm(dst, w, h, out)
    return dst


def body(path):
    b = open(path, 'rb').read()
    return b[b.index(b'\n255\n') + 5:]


def cell_block(buf, w, cw, ch, r, c):
    """The bytes of logical cell (r, c) out of a PPM body, row-major."""
    out = bytearray()
    for y in range(ch):
        o = ((r * ch + y) * w + c * cw) * 3
        out += buf[o:o + cw * 3]
    return bytes(out)


def rebuilt(path, view, mode):
    """Materialize the view a second way, without calling `materialize()`.

    Cell by cell from the source bytes: under `clamp` a cell whose whole carve is
    not inside the capture is written as the zero sentinel, exactly as `plane()`
    drops it; under `wrap` every cell is read cyclically. Geometry comes from the
    PPM header alone -- this is the cross-check, so it must not import the behaviour
    it checks.
    """
    w, h, rows = decay.read_rgb(path)
    cw, ch = w // vga.COLS, h // vga.ROWS
    dx, dy = view.dx, view.dy
    ko, jo = getattr(view, 'ko', 0), getattr(view, 'jo', 0)
    canvas = [[[0, 0, 0] for _ in range(w)] for _ in range(h)]
    dropped = 0
    for lr in range(vga.ROWS):
        for lc in range(vga.COLS):
            pr, pc = (lr + ko) % vga.ROWS, (lc + jo) % vga.COLS
            y0, x0 = pr * ch + dy, pc * cw + dx
            out_of = y0 + ch > h or x0 + cw > w
            if out_of and mode == 'clamp':
                dropped += 1
                continue
            for y in range(ch):
                for x in range(cw):
                    canvas[lr * ch + y][lc * cw + x] = rows[(y0 + y) % h][(x0 + x) % w]
    out = os.path.join(os.path.dirname(path), 'rebuild_%s_%d.ppm' % (mode, os.getpid()))
    decay.write_ppm(out, w, h, canvas)
    return out, dropped


def header_invented(path, dx, dy, ko, jo):
    """Out-of-frame logical cells over the WHOLE frame, from the header alone."""
    w, h, _rows = decay.read_rgb(path)
    cw, ch = w // vga.COLS, h // vga.ROWS
    return sum(1 for lr in range(vga.ROWS) for lc in range(vga.COLS)
               if (((lr + ko) % vga.ROWS) * ch + dy + ch > h
                   or ((lc + jo) % vga.COLS) * cw + dx + cw > w))


def cellwise_diffs(a, b):
    """Logical cells whose bytes differ between two files, and the byte count."""
    ba, bb = body(a), body(b)
    w, h, _ = decay.read_rgb(a)
    cw, ch = w // vga.COLS, h // vga.ROWS
    diff = sum(1 for r in range(vga.ROWS) for c in range(vga.COLS)
               if cell_block(ba, w, cw, ch, r, c) != cell_block(bb, w, cw, ch, r, c))
    return diff, sum(1 for x, y in zip(ba, bb) if x != y)


def is_sentinel(path, w, cw, ch, r, c):
    return set(cell_block(body(path), w, cw, ch, r, c)) <= {0}


def read_at(path, row):
    fr = vga.Frame(path)
    got, cells = vga.read_line(fr, vga.build_atlas(fr), row, len(MSG))
    return got, sum(1 for c in cells if c and c['dist'] == 0), sum(1 for c in cells if c is None)


def main():
    run = tempfile.mkdtemp(prefix='bm801_matgate.')
    print('# B6 materialize-mode gate | run dir %s' % run)
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
    print('# frame %dx%d cell %dx%d -> one cell is %d bytes' % (w, h, cw, ch, cw * ch))

    # ---- the shared geometry: B5's measured all-33-invented edge case -------
    edge_f = roll(clean, os.path.join(run, 'edge.ppm'), 0, 2)
    rep_edge, view_edge = al.corrected(edge_f, row=EDGE_ROW, mode='clamp')
    rep_edge_w, view_edge_w = al.corrected(edge_f, row=EDGE_ROW, mode='wrap')
    print('# edge clamp: phase=%s origin=%s msg_inv=%d cells_inv=%d'
          % (rep_edge['phase'], rep_edge['block_origin'], rep_edge['msg_cells_edge_invented'],
             rep_edge['cells_edge_invented']))
    print('# edge wrap : phase=%s origin=%s msg_inv=%d cells_inv=%d'
          % (rep_edge_w['phase'], rep_edge_w['block_origin'],
             rep_edge_w['msg_cells_edge_invented'], rep_edge_w['cells_edge_invented']))

    predict('0 source-inert', 'no leg writes to the capture: %s unchanged, and each view keeps '
                              'the mode it was built with' % src_sha)
    check('0 source-inert',
          hashlib.sha256(open(clean, 'rb').read()).hexdigest()[:16] == src_sha
          and view_edge.mode == 'clamp' and view_edge_w.mode == 'wrap',
          'sha before=%s after=%s edge.mode=%s wrap.mode=%s'
          % (src_sha, hashlib.sha256(open(clean, 'rb').read()).hexdigest()[:16],
             view_edge.mode, view_edge_w.mode))

    # ---- leg 1: the RED-to-GREEN pair --------------------------------------
    n_head = header_invented(edge_f, view_edge.dx, view_edge.dy, view_edge.ko, view_edge.jo)
    predict('1 mode-binds-the-file',
            'RED (run 1, pre-fix): materialize(clamp) was BYTE-IDENTICAL to materialize(wrap) '
            'at this phase (0 differing bytes) and 9771 bytes from the header-arithmetic '
            'rebuild. GREEN: materialize(clamp) is byte-identical to the clamp rebuild, '
            'materialize(wrap) to the wrap rebuild, and every cell the two files differ on is '
            'one of the %d out-of-frame cells. Run 1 also refuted "the two files differ on ALL '
            '%d": a cell the capture paints black is already the sentinel, so it cannot differ '
            '-- the leg therefore asserts containment plus that explanation, not equality.'
            % (n_head, n_head))
    mat_clamp = os.path.join(run, 'mat_clamp.ppm')
    mat_wrap = os.path.join(run, 'mat_wrap.ppm')
    rec_clamp = al.materialize(view_edge, mat_clamp)
    rec_wrap = al.materialize(view_edge_w, mat_wrap)
    reb_clamp, reb_dropped = rebuilt(edge_f, view_edge, 'clamp')
    reb_wrap, _ = rebuilt(edge_f, view_edge_w, 'wrap')
    d_cr, b_cr = cellwise_diffs(mat_clamp, reb_clamp)
    d_wr, b_wr = cellwise_diffs(mat_wrap, reb_wrap)
    d_cw_, b_cw = cellwise_diffs(mat_clamp, mat_wrap)
    inv_cells = [(r, c) for r in range(vga.ROWS) for c in range(vga.COLS)
                 if view_edge.drops(r, c)]
    # a dropped cell that does NOT differ must have been all-black in the capture
    quiet = [(r, c) for r, c in inv_cells
             if cell_block(body(mat_clamp), w, cw, ch, r, c)
             == cell_block(body(mat_wrap), w, cw, ch, r, c)]
    quiet_explained = all(set(cell_block(body(mat_wrap), w, cw, ch, r, c)) <= {0}
                          for r, c in quiet)
    check('1 mode-binds-the-file',
          d_cr == 0 and b_cr == 0 and d_wr == 0 and b_wr == 0 and n_head > 0 and quiet_explained
          and d_cw_ == n_head - len(quiet),
          'clamp-vs-rebuild=%d/%d cells/bytes wrap-vs-rebuild=%d/%d (the rebuild models the '
          'old wrap exactly) | clamp-vs-wrap=%d of %d invented cells, %d bytes, %d invented cells '
          'already black in the capture=%s'
          % (d_cr, b_cr, d_wr, b_wr, d_cw_, n_head, b_cw, len(quiet), quiet_explained))

    predict('2 sentinel-count-reported',
            'the writer reports how many cells it wrote as the declared sentinel, and that is '
            'the %d the header arithmetic gives without calling the aligner; under wrap it is 0 '
            'and the mode travels with the report. The artifact carries it too: the clamp file\'s '
            'PPM header names the count, so the claim cannot be separated from the pixels, and a '
            'plain Frame still parses it.' % n_head)
    hdr_clamp = open(mat_clamp, 'rb').read(96).split(b'\n')[2]
    hdr_wrap = open(mat_wrap, 'rb').read(96).split(b'\n')[2]
    parses = vga.Frame(mat_clamp)
    check('2 sentinel-count-reported',
          isinstance(rec_clamp, dict) and rec_clamp.get('sentinelled') == n_head == reb_dropped
          and rec_clamp.get('mode') == 'clamp'
          and isinstance(rec_wrap, dict) and rec_wrap.get('sentinelled') == 0
          and rec_wrap.get('mode') == 'wrap'
          and (('sentinelled=%d' % n_head).encode() in hdr_clamp) and hdr_wrap == b'255'
          and (parses.w, parses.h) == (w, h),
          'clamp report=%s | wrap report=%s | header-arithmetic=%d rebuild-dropped=%d | '
          'clamp file header=%r wrap file header=%r | commented file reparsed %dx%d'
          % (rec_clamp, rec_wrap, n_head, reb_dropped, hdr_clamp, hdr_wrap, parses.w, parses.h))

    # ---- leg 3: in-frame paths still round-trip ----------------------------
    predict('3 in-frame-round-trip',
            'the fix must cost nothing where the capture has the pixels: (a) an identity clamp '
            'view writes the source bytes back exactly and %r reads at distance 0 on all %d '
            'cells; (b) a rolled frame WRAP was accepted at, re-bound to clamp with every '
            'message-row cell inside the capture, still reads %r from the written file. Run 1 '
            'also refuted a criterion here: no displaced frame the aligner accepts keeps the '
            '16x16 atlas intact -- registration always slides at least one block row off the '
            'edge (measured atlas_drop=16 even at msg_drop=0), so the atlas damage is REPORTED, '
            'not required away.' % (MSG, len(MSG), MSG))
    id_clamp = os.path.join(run, 'identity_clamp.ppm')
    rec_idc = al.materialize(al.OriginFrame(vga.Frame(clean), 0, 0, 0, 0, 'clamp'), id_clamp)
    ident_clamp = open(clean, 'rb').read() == open(id_clamp, 'rb').read()
    got3a, d03a, bl3a = read_at(id_clamp, vga.MSG_ROW)
    picked = None
    for sx, sy in [(4, 5), (0, 2), (2, 0), (5, 7), (1, 1), (7, 3), (0, 4), (8, 12)]:
        f = roll(clean, os.path.join(run, 'l3_%d_%d.ppm' % (sx, sy)), sx, sy)
        r3, v3 = al.corrected(f, row=vga.MSG_ROW, mode='wrap')
        if r3.get('refused') or r3['read_corrected'] != MSG or r3['distance0_corrected'] != len(MSG):
            print('      try roll(%d,%d): wrap read=%r d0=%s skipped'
                  % (sx, sy, r3.get('read_corrected'), r3.get('distance0_corrected')))
            continue
        cv3 = al.OriginFrame(vga.Frame(f), r3['phase'][0], r3['phase'][1],
                             r3['block_origin'][0], r3['block_origin'][1], 'clamp')
        inv3 = header_invented(f, cv3.dx, cv3.dy, cv3.ko, cv3.jo)
        msg_drop = sum(1 for c in range(len(MSG)) if cv3.drops(vga.MSG_ROW, c))
        atlas_drop = sum(1 for r_ in range(vga.ATLAS_SIDE) for c_ in range(vga.ATLAS_SIDE)
                         if cv3.drops(r_, c_))
        print('      try roll(%d,%d): phase=%s origin=%s invented=%d msg_drop=%d atlas_drop=%d'
              % (sx, sy, r3['phase'], r3['block_origin'], inv3, msg_drop, atlas_drop))
        if inv3 > 0 and msg_drop == 0:
            picked = (sx, sy, f, r3, cv3, inv3, atlas_drop)
            break
    if picked:
        s3, t3, f3, r3, cv3, inv3, atlas3 = picked
        mat3 = os.path.join(run, 'mat_l3.ppm')
        rec3 = al.materialize(cv3, mat3)
        got3b, d03b, bl3b = read_at(mat3, vga.MSG_ROW)
        same3 = d03b == len(MSG) and got3b == MSG and rec3.get('sentinelled') == inv3
    else:
        s3 = t3 = inv3 = atlas3 = None
        got3b, d03b, bl3b, rec3 = None, 0, 0, None
        same3 = False
    check('3 in-frame-round-trip',
          ident_clamp and got3a == MSG and d03a == len(MSG) and bl3a == 0
          and rec_idc.get('sentinelled') == 0 and bool(picked) and same3,
          '(a) identity-clamp byte-identical=%s read=%r distance0=%d/%d sentinelled=%s | '
          '(b) roll(%s,%s) clamp-rebound: invented=%s sentinelled=%s atlas_cells_dropped=%s '
          'read=%r distance0=%s/%s blank=%s'
          % (ident_clamp, got3a, d03a, len(MSG), rec_idc.get('sentinelled'), s3, t3,
             inv3, rec3.get('sentinelled') if rec3 else None, atlas3, got3b, d03b, len(MSG),
             bl3b))

    # ---- leg 4: the off-edge row must not decode ---------------------------
    predict('4 off-edge-does-not-decode',
            'run 1 refuted the version of this prediction that expected the wrap file to return '
            '%r: B5 measured wrap at 32/33 distance 0 on 33 invented cells, and the 32 were '
            'PLAUSIBLE GLYPHS FROM THE CALIBRATION ROW, not the message -- which is the whole '
            'defect in one line. So: on the same geometry the clamp file must yield 0 plausible '
            'cells and 33 blank ones, while the wrap file keeps handing the reader evidence '
            '(distance 0 > 0, blank < 33). clamp may destroy a false read, never invent one.'
            % MSG)
    mat_edge_w = os.path.join(run, 'mat_edge_wrap.ppm')
    al.materialize(view_edge_w, mat_edge_w)
    got4c, d04c, bl4c = read_at(mat_clamp, EDGE_ROW)
    got4w, d04w, bl4w = read_at(mat_edge_w, EDGE_ROW)
    check('4 off-edge-does-not-decode',
          rep_edge['msg_cells_edge_invented'] == len(MSG) and bl4c == len(MSG) and d04c == 0
          and d04w > 0 and bl4w < len(MSG) and got4c != got4w,
          'msg_inv=%d clamp read=%r distance0=%d blank=%d/%d | wrap read=%r distance0=%d '
          'blank=%d' % (rep_edge['msg_cells_edge_invented'], got4c, d04c, bl4c, len(MSG),
                        got4w, d04w, bl4w))

    # ---- leg 5: two modes, one phase, two files ----------------------------
    predict('5 same-phase-two-files',
            'the leg that proves the rule binds the MODE and not a new default: one phase '
            '%s, one origin %s, two modes. Every sentinel cell must be all-zero bytes in the '
            'clamp file and NO in-frame cell may differ at all -- so the fix cannot reach '
            'outside the region the capture genuinely lacks. The differing-cell count is the '
            'invented count minus the invented cells that were already black (leg 1), so that '
            'is what is asserted, not the raw %d.'
            % (rep_edge['phase'], rep_edge['block_origin'], n_head))
    same_phase_wrap = al.OriginFrame(vga.Frame(edge_f), view_edge.dx, view_edge.dy,
                                     view_edge.ko, view_edge.jo, 'wrap')
    mat_sp = os.path.join(run, 'mat_same_phase_wrap.ppm')
    rec_sp = al.materialize(same_phase_wrap, mat_sp)
    dropped_cells = [(r, c) for r in range(vga.ROWS) for c in range(vga.COLS)
                     if view_edge.drops(r, c)]
    sentinel_ok = all(is_sentinel(mat_clamp, w, cw, ch, r, c) for r, c in dropped_cells)
    changed_in_frame = sum(1 for r in range(vga.ROWS) for c in range(vga.COLS)
                           if not view_edge.drops(r, c)
                           and cell_block(body(mat_clamp), w, cw, ch, r, c)
                           != cell_block(body(mat_sp), w, cw, ch, r, c))
    d5, b5 = cellwise_diffs(mat_clamp, mat_sp)
    check('5 same-phase-two-files',
          n_head > 0 and changed_in_frame == 0 and sentinel_ok
          and d5 == n_head - len(quiet) and rec_sp.get('sentinelled') == 0 and b5 > 0,
          'cells differ=%d = %d invented - %d already-black | every dropped cell all-zero=%s | '
          'in-frame cells changed=%d | clamp sentinelled=%s vs same-phase wrap sentinelled=%s'
          % (d5, n_head, len(quiet), sentinel_ok, changed_in_frame,
             rec_clamp.get('sentinelled'), rec_sp.get('sentinelled')))

    predict('6 wrap-unchanged',
            'no existing caller changes behaviour: the default mode is still %r, a default '
            'materialize of the identity view writes the source bytes back exactly, and the '
            'old wrap output is what the header-arithmetic rebuild says wrap always was (leg 1 '
            'wrap-vs-rebuild=0)' % 'wrap')
    default_mode = inspect.signature(al.OffsetFrame.__init__).parameters['mode'].default
    id_def = os.path.join(run, 'identity_default.ppm')
    rec_id = al.materialize(al.OriginFrame(vga.Frame(clean)), id_def)
    ident = open(clean, 'rb').read() == open(id_def, 'rb').read()
    check('6 wrap-unchanged',
          default_mode == 'wrap' and ident and rec_id.get('sentinelled') == 0 and d_wr == 0,
          'OffsetFrame default mode=%r identity-write-byte-identical=%s sentinelled=%s '
          'wrap-vs-rebuild=%d' % (default_mode, ident, rec_id.get('sentinelled'), d_wr))

    # ---- leg 7: the price, measured (the item predicted it) ----------------
    predict('7 clamp-price-measured',
            "the item's own numbers, measured two ways on B5's roll(0,%d). (a) In the REPORT: "
            'clamp should read 1629 of %d exact where wrap reads 1692, because wrap wins on %d '
            'invented cells. (b) In the FILE: at ONE fixed geometry, the clamp-materialized file '
            'scored by an UNMODIFIED plain Frame must come out strictly BELOW the '
            'wrap-materialized file, or the sentinel never reaches the scoring path and legs 1-5 '
            'test a file nobody reads. Run 2 refuted how this leg first asked it: it scored each '
            'mode at its OWN chosen phase, and clamp wins roll(0,34) at phase (0,0) where '
            'nothing falls off the edge -- sentinelled=0, both files 65/%d, a vacuous pair.'
            % (2 * ch + 2, len(al.sample_cells()), 80, len(al.sample_cells())))
    f7 = roll(clean, os.path.join(run, 'roll_0_34.ppm'), 0, 2 * ch + 2)
    rep7c, rep7w = al.align(f7, mode='clamp'), al.align(f7, mode='wrap')
    dx7, dy7 = rep7w['phase']
    ko7, jo7 = rep7w['block_origin']
    clamp7 = al.OriginFrame(vga.Frame(f7), dx7, dy7, ko7, jo7, 'clamp')
    wrap7 = al.OriginFrame(vga.Frame(f7), dx7, dy7, ko7, jo7, 'wrap')
    mat7c = os.path.join(run, 'mat7_clamp.ppm')
    mat7w = os.path.join(run, 'mat7_wrap.ppm')
    rec7c = al.materialize(clamp7, mat7c)
    al.materialize(wrap7, mat7w)
    cells7 = al.sample_cells()
    score7c = al.exact_matches(vga.Frame(mat7c), cells7)
    score7w = al.exact_matches(vga.Frame(mat7w), cells7)
    check('7 clamp-price-measured',
          rep7c['exact_offblock'] < rep7w['exact_offblock'] and rec7c['sentinelled'] > 0
          and score7c < score7w,
          '(a) report: clamp %d/%d at phase %s invented=%d vs wrap %d/%d at phase %s invented=%d '
          '(item predicted 1629 vs 1692: %s) | (b) file at wrap geometry %s/%s: clamp-materialized '
          '%d/%d exact vs wrap-materialized %d/%d, price %d cells, sentinelled=%d'
          % (rep7c['exact_offblock'], len(cells7), rep7c['phase'], rep7c['cells_edge_invented'],
             rep7w['exact_offblock'], len(cells7), rep7w['phase'], rep7w['cells_edge_invented'],
             (rep7c['exact_offblock'], rep7w['exact_offblock']) == (1629, 1692),
             rep7w['phase'], rep7w['block_origin'], score7c, len(cells7), score7w, len(cells7),
             score7w - score7c, rec7c['sentinelled']))

    if os.environ.get('BM6_SKIP_OLDER'):
        print('# leg 8 skipped (BM6_SKIP_OLDER set): the nested B4/B5 gates were not run')
    else:
        predict('8 older-gates-regress',
                "B4's 9 legs and B5's 9 legs both still exit 0, and the materialize census in "
                'each is reported honestly: if an older gate never calls materialize, legs 1-7 '
                'are the only thing holding this rule there')
        b4 = subprocess.run([sys.executable, os.path.join(HERE, 'run_bm801_align_gate.py')],
                            capture_output=True, text=True)
        b5p = subprocess.run([sys.executable, os.path.join(HERE, 'run_bm801_clamp_gate.py')],
                             capture_output=True, text=True)
        t4 = [l for l in b4.stdout.splitlines() if l.startswith('RESULT')]
        t5 = [l for l in b5p.stdout.splitlines() if l.startswith('RESULT')]
        census = {g: sum(1 for l in open(os.path.join(HERE, g)) if 'materialize(' in l)
                  for g in ('run_bm801_align_gate.py', 'run_bm801_clamp_gate.py')}
        check('8 older-gates-regress', b4.returncode == 0 and b5p.returncode == 0 and t4 and t5,
              'b4 rc=%s %s | b5 rc=%s %s | materialize-call-sites %s'
              % (b4.returncode, t4 or b4.stdout[-120:] + b4.stderr[-200:],
                 b5p.returncode, t5 or b5p.stdout[-120:] + b5p.stderr[-200:], census))

    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print('RESULT %d/%d legs pass' % (n_ok, len(RESULTS)))
    shutil.rmtree(run, ignore_errors=True)
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main())
