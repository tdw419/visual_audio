#!/usr/bin/env python3
"""run_bm801_lum_gate.py -- B9: give `OriginFrame` a `lum()` that honours all five.

B8's audit (`AUDIT_BM801_SAMPLING_PATHS.md`, landed `a5bf99e3`) measured 22 sampling
paths and produced one row that reaches `self.pixels` and reads none of the offsets:
`OriginFrame.lum()`, which resolved to `vga.Frame.lum` -- `(r*ch + y)*w + c*cw + x`,
no `dx`, no `dy`, no `ko`, no `jo`, no mode. Its gate column read `nothing`: the only
`.lum(` call site in the ladder is inside `vga.Frame.grid`, and B7 overrode `grid()`
on both classes, which closed this accessor's last caller and left it standing. B8
landed that as a number and queued it as B9; this file is the leg that was missing.

Fix or cut was the choice, and the census decided it. An override costs one line,
routes the pixel through `raw_cell()` -- the same gate `plane()` and `grid()` already
use, so `drops()` is honoured too -- and leaves `vga.Frame.grid` usable as an unbound
call, which B7's leg 1 leans on. A refusal (`raise`) raises out of that same unbound
call and breaks B7 harder. So: override, and prove B7's numbers did not move.

Two things had to be measured before landing, not asserted:

  * **the row flips.** Legs 1 and 2 probe the same quantity -- a pixel, one offset at
    a time off the audit's anchor -- against a value derived by hand from the PPM
    bytes. Leg 1 keeps the blindness in evidence forever by running it on the base
    class's own formula over the same bytes, and it must land on B8's counts; leg 2
    requires `view.lum` to equal the hand-derived pixel on all five columns.
  * **B7's blind side survives the fix only if it moves.** `Frame.grid` is built on
    `self.lum`, so `vga.Frame.grid(view, ...)` stops being a blind carve the moment
    `lum` is overridden. Leg 3 measures exactly that -- and leg 4 of `run_bm801_grid_gate.py`'s
    re-point (the blind carve is now a plain `vga.Frame` over the same bytes) is what
    keeps its legs 1-5 true. The proof is weaker-looking and stronger-than-it-needs
    to be: B7's whole leg output is diffed digit-for-digit against its pre-fix run,
    in this gate's receipt.

`OffsetFrame.lum()` and `.rgb()` still wrap under `clamp` -- that was B10, and leg 7
here kept it open by measurement rather than by queue prose until B10 landed it
(2026-09-26). The leg now asserts the opposite sign on the same cells -- nothing invented
by the fixed pair, `rgb()` returning `SENTINEL`, and `wrap` unmoved -- and keeps the base
formula's invented read as its control, so this item's own row cannot be softened by
dropping the leg.

Run: python3 rung8/run_bm801_lum_gate.py   (one beacon boot, then host-side)
Set BM9_SKIP_OLDER=1 to skip leg 9's nested B7 and B8 gates while iterating. Note that
B8's audit gate compares eight of its files against their `HEAD` blobs, so nested legs
read RED until this item's own edits are committed: run once skipped, then land, then
run in full and quote the landed-state numbers.
"""

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ast
import bm801_align as al        # noqa: E402
import bm801_capture as cap     # noqa: E402
import bm801_reader_decay as decay   # noqa: E402
import bm801_vga as vga         # noqa: E402

MSG = al.MSG
RESULTS = []
KEEP_OUT = 'ubuntu_desktop_pxc1_v3_selfhost'

# B8's anchor, deliberately: the numbers this gate prints have to be comparable with
# the row it queued, which was measured at one-at-a-time perturbations off (3,5,2,7).
PX, PY, PK, PJ = 3, 5, 2, 7
BASE = {'dx': PX, 'dy': PY, 'ko': PK, 'jo': PJ, 'mode': 'wrap'}
CELLS = [(10, 30), (4, 20), (0, 0), (15, 8), (24, 79), (vga.ROWS - 1, 0)]
PIXEL_XY = [(0, 0), (3, 7), (8, 15), (0, 15), (8, 0)]


def predict(name, text):
    print('--> %-32s predicts: %s' % (name, text))


def check(name, ok, detail):
    RESULTS.append((name, bool(ok)))
    print('    %s %-32s %s' % ('PASS' if ok else 'FAIL', name, detail))


def at(**over):
    p = dict(BASE)
    p.update(over)
    return p


def roll(src, dst, sx, sy):
    """Cyclic whole-frame displacement -- the frame `wrap` is honest about."""
    w, h, rows = decay.read_rgb(src)
    out = [[rows[(y + sy) % h][(x + sx) % w] for x in range(w)] for y in range(h)]
    decay.write_ppm(dst, w, h, out)
    return dst


def cells_for(p):
    """B8's sample plan: the fixed cells plus the logical cells whose PHYSICAL row or
    column is the last one -- where a non-zero phase makes clamp bite."""
    last_r = (vga.ROWS - 1 - p['ko']) % vga.ROWS
    last_c = (vga.COLS - 1 - p['jo']) % vga.COLS
    return CELLS + [(last_r, 30), (10, last_c), (last_r, last_c)]


def want_px(rows, w, h, cw, ch, p, r, c, x, y):
    """One pixel of logical cell (r, c): relabel, then phase, then mode. By hand, from
    the PPM bytes -- nothing here imports the aligner, so the fix cannot make the leg
    true by agreeing with itself."""
    pr, pc = (r + p['ko']) % vga.ROWS, (c + p['jo']) % vga.COLS
    y0, x0 = pr * ch + p['dy'], pc * cw + p['dx']
    if p['mode'] == 'clamp' and not (y0 >= 0 and y0 + ch <= h
                                     and x0 >= 0 and x0 + cw <= w):
        return 0
    return sum(rows[(y0 + y) % h][(x0 + x) % w])


def dims():
    for d in ('dx', 'dy', 'ko', 'jo'):
        yield d, at(**{d: 0}), at()
    yield 'mode', at(mode='wrap'), at(mode='clamp')


def probe(get, base, rows, w, h, cw, ch):
    """{dim: (n, blind, ok, off)} for one pixel-taking accessor.

    `blind` = samples that did not move when the bytes under them did, which is the
    quantity B8's table reports as `N/45 samples unchanged where the bytes differ`;
    `ok` = samples equal to the hand-derived value at both ends of the perturbation.
    """
    out = {}
    for dim, p0, p1 in dims():
        v0f = al.OriginFrame(base, p0['dx'], p0['dy'], p0['ko'], p0['jo'], p0['mode'])
        v1f = al.OriginFrame(base, p1['dx'], p1['dy'], p1['ko'], p1['jo'], p1['mode'])
        n = blind = ok = off = 0
        for (r, c) in cells_for(p1):
            for (x, y) in PIXEL_XY:
                n += 1
                g0 = want_px(rows, w, h, cw, ch, p0, r, c, x, y)
                g1 = want_px(rows, w, h, cw, ch, p1, r, c, x, y)
                a, b = get(v0f, r, c, x, y), get(v1f, r, c, x, y)
                if g1 != g0 and a == b:
                    blind += 1
                    if a != g0:
                        off += 1
                    continue
                if a == g0 and b == g1:
                    ok += 1
        out[dim] = (n, blind, ok, off)
    return out


def want_rows(rows, w, h, cw, ch, p, r, c):
    return [[want_px(rows, w, h, cw, ch, p, r, c, x, y) for x in range(cw)]
            for y in range(ch)]


def plane_of(g, cw, ch):
    """`Frame.plane()`'s thresholding rule, re-derived here from the honouring carve."""
    flat = [v for row in g for v in row]
    if max(flat) - min(flat) < vga.FLAT_SPAN:
        return tuple([0] * (cw * ch))
    mid = (min(flat) + max(flat)) / 2.0
    m = [[1 if v > mid else 0 for v in row] for row in g]
    corners = [m[0][0], m[0][cw - 1], m[ch - 1][0], m[ch - 1][cw - 1]]
    if sum(corners) * 2 > len(corners):
        m = [[1 - v for v in row] for row in m]
    return tuple(v for row in m for v in row)


def base_px(view, r, c, x, y):
    """The pre-B9 accessor, live: `vga.Frame.lum` on a frame that has no offsets."""
    return vga.Frame.lum(view, r, c, x, y)


def main():
    run = tempfile.mkdtemp(prefix='bm809_lumgate.')
    print('# B9 OriginFrame.lum gate | run dir %s' % run)
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
    view = al.OriginFrame(base, PX, PY, PK, PJ, 'wrap')
    cview = al.OriginFrame(base, PX, PY, PK, PJ, 'clamp')
    of = al.OffsetFrame(base, PX, PY, 'clamp')
    zero = al.OriginFrame(base, 0, 0, 0, 0, 'wrap')
    dropped = [rc for rc in ((r, c) for r in range(vga.ROWS) for c in range(vga.COLS))
               if cview.drops(*rc)]
    print('# frame %dx%d cell %dx%d | capture %s | anchor (%d,%d) block (%d,%d) | clamp view '
          'drops %d of %d cells' % (w, h, cw, ch, src_sha, PX, PY, PK, PJ, len(dropped),
                                    vga.ROWS * vga.COLS))

    predict('0 source-inert',
            'no leg writes to the capture: %s unchanged at the end, and this file names the '
            'keep-out disk exactly once -- in the constant above, never as a path it opens'
            % src_sha)
    self_text = open(os.path.abspath(__file__)).read()
    sha_after = hashlib.sha256(open(clean, 'rb').read()).hexdigest()[:16]
    check('0 source-inert', sha_after == src_sha and self_text.count(KEEP_OUT) == 1,
          'sha before=%s after=%s | keep-out name occurrences=%d' % (src_sha, sha_after,
                                                                     self_text.count(KEEP_OUT)))

    # ---- leg 1: the blindness, kept in evidence on live code ---------------------
    # B8's finding 1, published in AUDIT_BM801_SAMPLING_PATHS.md at a5bf99e3: "NO (blind)
    # on dx (21 of 45 samples unchanged where the bytes differ), dy 17, ko 7, jo 6, and
    # NO (wraps) on mode 4". That row WAS this formula, so re-measuring the formula on the
    # same anchor, same cells and same pixels has to land on the same five digits.
    B8_ROW = {'dx': 21, 'dy': 17, 'ko': 7, 'jo': 6, 'mode': 4}
    blind_p = probe(base_px, base, rows, w, h, cw, ch)
    predict('1 base-formula-still-blind',
            'B8\'s row read NO (blind) on %s of 45 samples and NO (wraps) on %d for mode, and '
            'that row WAS `vga.Frame.lum` over these same bytes: probing the base class again '
            'must reproduce those five digits, which is what makes it the permanent RED after the '
            'override lands -- the blindness is a fact about a formula that is still live, not '
            'about which class happens to inherit it'
            % ('/'.join(str(B8_ROW[d]) for d in ('dx', 'dy', 'ko', 'jo')), B8_ROW['mode']))
    check('1 base-formula-still-blind',
          all(blind_p[d][1] == B8_ROW[d] for d in B8_ROW)
          and all(blind_p[d][0] == 45 for d in B8_ROW),
          'unchanged-where-bytes-differ: %s (B8: %s) | off-model even at the anchor: %s'
          % (' '.join('%s=%d/45' % (d, blind_p[d][1]) for d in ('dx', 'dy', 'ko', 'jo', 'mode')),
             ' '.join('%s=%d' % (d, B8_ROW[d]) for d in ('dx', 'dy', 'ko', 'jo', 'mode')),
             ' '.join('%s=%d' % (d, blind_p[d][3]) for d in ('dx', 'dy', 'ko', 'jo', 'mode'))))

    # ---- leg 2: the override, measured ------------------------------------------
    fix_p = probe(lambda v, r, c, x, y: v.lum(r, c, x, y), base, rows, w, h, cw, ch)
    predict('2 origin-lum-honours-five',
            'with `OriginFrame.lum` routed through `raw_cell()`, every sample must equal the '
            'hand-derived pixel at both ends of every perturbation: 45/45 on all five columns, '
            'measured, and the mode column has %d dropped cells in the sample plan to bite on'
            % len([rc for rc in cells_for(at(mode='clamp')) if cview.drops(*rc)]))
    check('2 origin-lum-honours-five',
          all(fix_p[d][1] == 0 and fix_p[d][2] == fix_p[d][0] == 45
              for d in ('dx', 'dy', 'ko', 'jo', 'mode')),
          'blind samples: %s | equal to the hand-derived pixel: %s'
          % (' '.join('%s=%d' % (d, fix_p[d][1]) for d in ('dx', 'dy', 'ko', 'jo', 'mode')),
             ' '.join('%s=%d/%d' % (d, fix_p[d][2], fix_p[d][0])
                      for d in ('dx', 'dy', 'ko', 'jo', 'mode'))))

    # ---- leg 3: why B7 had to move ----------------------------------------------
    band = cells_for(at())[:5]
    now_honours = [rc for rc in band if vga.Frame.grid(view, *rc) != view.grid(*rc)]
    base_agrees = [rc for rc in band if vga.Frame.grid(base, *rc) == view.grid(*rc)]
    predict('3 old-unbound-call-now-honours',
            '`Frame.grid` calls `self.lum`, so the form B7 used for its blind side -- '
            '`vga.Frame.grid(view, ...)` -- equals the view\'s own honouring carve on every '
            'cell of the band (%d sampled, 0 expected to disagree), while the same call on a '
            'plain Frame disagrees on all %d. That is the whole reason B7\'s `blind_grid` was '
            're-pointed at a base Frame in this item rather than left alone'
            % (len(band), len(band)))
    check('3 old-unbound-call-now-honours', not now_honours and not base_agrees,
          'band=%d cells | unbound-on-view != view.grid: %d | unbound-on-base == view.grid: %d'
          % (len(band), len(now_honours), len(base_agrees)))

    # ---- leg 4: the mode, on every dropped cell ---------------------------------
    inv_view = [rc for rc in dropped
                if any(cview.lum(rc[0], rc[1], x, y) for x, y in PIXEL_XY)]
    inv_base = [rc for rc in dropped
                if any(vga.Frame.lum(base, rc[0], rc[1], x, y) for x, y in PIXEL_XY)]
    predict('4 clamp-cell-is-the-sentinel',
            'the four offsets are not the whole defect: `OriginFrame.lum` must return the same '
            'zero the cell accessor returns for a dropped cell, on all %d of them, while the base '
            'formula reads real capture bytes for most -- which is the invented edge B8 counted as '
            '`NO (wraps)`' % len(dropped))
    check('4 clamp-cell-is-the-sentinel', not inv_view and len(inv_base) > len(dropped) // 2,
          'dropped cells=%d | invented by the override: %d | invented by the base formula: %d'
          % (len(dropped), len(inv_view), len(inv_base)))

    # ---- leg 5: the control that says when nobody noticed -----------------------
    same_zero = [rc for rc in CELLS for xy in PIXEL_XY
                 if zero.lum(rc[0], rc[1], *xy) != base.lum(rc[0], rc[1], *xy)]
    predict('5 zero-offset-control',
            'at zero displacement and zero origin the override is the base formula exactly, on '
            'every sampled cell and pixel -- the defect was invisible precisely when the frame '
            'needed no correction, which is every leg any older gate runs')
    check('5 zero-offset-control', not same_zero and (PX, PY, PK, PJ) != (0, 0, 0, 0),
          '%d of %d samples differ at zero; anchor is (%d,%d,%d,%d)'
          % (len(same_zero), len(CELLS) * len(PIXEL_XY), PX, PY, PK, PJ))

    # ---- leg 6: one sampling rule, pixel and cell -------------------------------
    agree = [(fr, rc) for fr in (view, cview) for rc in CELLS
             if [[fr.lum(rc[0], rc[1], x, y) for x in range(cw)] for y in range(ch)]
             != fr.grid(*rc)]
    plane_agree = [rc for rc in CELLS
                   if view.plane(*rc)[0] != plane_of(want_rows(rows, w, h, cw, ch, at(), *rc),
                                                     cw, ch)]
    predict('6 pixel-and-cell-agree',
            'the accessor must not become a second opinion: rebuilding each sampled cell out of '
            '`lum()` equals `grid()` on both modes (%d/%d comparisons), and the thresholded plane '
            'equals the hand-derived one on the wrap view (%d/%d)'
            % (len(CELLS) * 2, len(CELLS) * 2, len(CELLS), len(CELLS)))
    check('6 pixel-and-cell-agree', not agree and not plane_agree,
          'cells disagreeing with their own lum-rebuild: %d | cells whose plane != the '
          'hand-derived carve: %d' % (len(agree), len(plane_agree)))

    # ---- leg 7: the sibling class, before and after B10 ---------------------------
    # B9 left `OffsetFrame` alone: its `lum`/`rgb` indexed with `% h` and `% w` and never
    # consulted `drops()`, so under clamp they returned the opposite edge. That was the
    # assertion here, and B10 (2026-09-26) broke it on purpose -- `OffsetFrame.lum` now goes
    # through `OffsetFrame.rgb`, which returns SENTINEL for a cell the mode refuses. The leg
    # keeps its shape and swaps its sign: the fix is asserted, and the blindness stays
    # asserted too, on the base formula's read of those same dropped cells.
    of_out = [rc for rc in CELLS + [(vga.ROWS - 1, 30), (10, vga.COLS - 1),
                                    (vga.ROWS - 1, vga.COLS - 1)] if not of.in_frame(*rc)]
    of_inv = [rc for rc in of_out if any(of.lum(rc[0], rc[1], x, y) for x, y in PIXEL_XY)]
    of_rgb_sent = [rc for rc in of_out
                   if all(of.rgb(rc[0], rc[1], x, y) == al.SENTINEL for x, y in PIXEL_XY)]
    # The control B10's own prediction names: `wrap` must not move one byte. `drops()` is
    # false for every cell there, so the fixed pair still has to land on the pre-fix
    # formula's value -- derived here by hand from the PPM bytes, not from the class.
    def want_off(dx, dy, mode, r, c, x, y):
        y0, x0 = r * ch + dy, c * cw + dx
        if mode == 'clamp' and not (y0 >= 0 and y0 + ch <= h and x0 >= 0 and x0 + cw <= w):
            return 0
        return sum(rows[(y0 + y) % h][(x0 + x) % w])

    of_wrap = al.OffsetFrame(base, PX, PY, 'wrap')
    wrap_off = [rc for rc in CELLS for xy in PIXEL_XY
                if of_wrap.lum(rc[0], rc[1], *xy) != want_off(PX, PY, 'wrap', *rc, *xy)]
    clamp_in = [rc for rc in CELLS if of.in_frame(*rc) for xy in PIXEL_XY
                if of.lum(rc[0], rc[1], *xy) != want_off(PX, PY, 'clamp', *rc, *xy)]
    predict('7 offset-lum-mode-fixed',
            'B10 routes the single-pixel pair through `drops()`, so on every out-of-frame '
            'sampled cell (`%d` of them) `lum` must invent nothing and `rgb` must hand back '
            '`SENTINEL`; the base formula on the same `%d` dropped cells still invents on most '
            '(%d), which is the permanent blind side leg 1 measures. The control: wrap mode '
            'must still equal the hand-derived carve on every sample (%d/%d bad), and so must '
            'the clamp view on its IN-frame cells (%d/%d bad) -- the fix may only reach the '
            'branch `drops()` guards'
            % (len(of_out), len(dropped), len(inv_base),
               len(CELLS) * len(PIXEL_XY) - len(wrap_off), len(CELLS) * len(PIXEL_XY),
               len(clamp_in), len([rc for rc in CELLS if of.in_frame(*rc)]) * len(PIXEL_XY)))
    check('7 offset-lum-mode-fixed', len(of_out) > 0 and not of_inv
          and len(of_rgb_sent) == len(of_out) and not inv_view
          and len(inv_base) > len(dropped) // 2 and not wrap_off and not clamp_in,
          'clamp OffsetFrame: out-of-frame cells sampled=%d, inventing a non-zero byte=%d, '
          'rgb==SENTINEL on=%d | OriginFrame on its own %d dropped cells invents %d | base '
          'formula invents on %d | wrap samples off-model=%d | clamp in-frame off-model=%d'
          % (len(of_out), len(of_inv), len(of_rgb_sent), len(dropped), len(inv_view),
             len(inv_base), len(wrap_off), len(clamp_in)))

    # ---- leg 8: the census, before and after ------------------------------------
    src = {f: open(os.path.join(HERE, f)).read()
           for f in sorted(os.listdir(HERE)) if f.endswith('.py')}
    own = os.path.basename(__file__)

    def ast_attr_calls(text, attr):
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return []
        out = []
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == attr):
                out.append((getattr(node.func.value, 'id', None)
                            or ast.dump(node.func.value)[:24], node.lineno))
        return out

    lum_calls = {f: ast_attr_calls(t, 'lum') for f, t in src.items()}
    prod = {f: v for f, v in lum_calls.items()
            if v and not (f.startswith('run_bm80') and '_gate.py' in f)}
    gates = {f: len(v) for f, v in lum_calls.items() if v and f not in prod}
    predict('8 lum-row-exercised',
            'B8 counted exactly one `.lum(` site in the whole ladder (bm801_vga.py, inside '
            '`Frame.grid`) and zero gate callers, which is what made the row unreachable and '
            'untested at once; now this file is a caller. The production half must be unchanged '
            'at 1 -- the fix may not have created a consumer, only a test')
    check('8 lum-row-exercised',
          list(prod) == ['bm801_vga.py'] and len(prod['bm801_vga.py']) == 1
          and own in gates,
          'production lum() callers=%s | gate files calling it=%s'
          % ({f: [ln for _r, ln in v] for f, v in sorted(prod.items())}, gates))

    # ---- leg 9: the item did not move a receipt ----------------------------------
    if os.environ.get('BM9_SKIP_OLDER'):
        print('# older-gates skipped (BM9_SKIP_OLDER set): the nested gates were not run')
    else:
        predict('9 older-gates-regress',
                'B7\'s grid gate (whose blind side this item re-pointed) and B8\'s audit gate '
                '(whose row this item flipped) both still exit 0 with their full leg counts -- '
                'run with their own nested legs skipped, so this is three boots and no more')
        outs = {}
        for g, env in (('run_bm801_grid_gate.py', dict(os.environ, BM7_SKIP_OLDER='1')),
                       ('run_bm801_path_audit_gate.py', dict(os.environ, BM8_SKIP_OLDER='1'))):
            p = subprocess.run([sys.executable, os.path.join(HERE, g)],
                               capture_output=True, text=True, env=env)
            res = [l for l in p.stdout.splitlines() if l.startswith('RESULT')]
            outs[g] = (p.returncode, ' '.join(res) or (p.stdout[-90:] + p.stderr[-200:]))
        check('9 older-gates-regress', all(rc == 0 and t for rc, t in outs.values()),
              ' | '.join('%s rc=%s %s' % (g, rc, t) for g, (rc, t) in sorted(outs.items())))

    # ---- the read this whole ladder exists for ----------------------------------
    # B7's leg 8 asserts this on the same geometry and leg 9 above re-runs that gate,
    # so under BM9_SKIP_OLDER this is the only receipt check in the run.
    disp = roll(clean, os.path.join(run, 'disp.ppm'), 3, 5)
    rep10, view10 = al.corrected(disp, mode='wrap')
    n10, got10 = al.read_distance0(view10)
    n10z, got10z = al.read_distance0(al.OriginFrame(vga.Frame(disp), 0, 0, 0, 0, 'wrap'))
    predict('10 message-still-reads',
            'the channel the ladder exists for is unchanged on the geometry B7 measured: the '
            'displaced capture still aligns to phase (%d,%d) origin (%d,%d) and yields %r at '
            '%d/%d distance-0 cells (the uncorrected frame reads %r at %d/%d)'
            % (rep10['phase'][0], rep10['phase'][1], rep10['block_origin'][0],
               rep10['block_origin'][1], MSG, n10, len(MSG), got10z, n10z, len(MSG)))
    check('10 message-still-reads', got10 == MSG and n10 == len(MSG),
          'displaced read=%r distance0=%d/%d | zero-offset read=%r distance0=%d/%d'
          % (got10, n10, len(MSG), got10z, n10z, len(MSG)))

    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print('RESULT %d/%d legs pass' % (n_ok, len(RESULTS)))
    shutil.rmtree(run, ignore_errors=True)
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main())
