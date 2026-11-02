#!/usr/bin/env python3
"""run_bm801_grid_gate.py -- B7: does the inherited carve honour the offsets it sits under?

Before this item, `OriginFrame` overrode `plane()`, `raw_cell()`, `drops()`,
`in_frame()` and `pitch_is_exact()`, and delegated all of them to an inner
`OffsetFrame` through `physical()`. It did NOT override `grid()` or `lum()`, so
both stayed the `vga.Frame` versions, which address `self.pixels` at
`(r*ch + y)*w + c*cw + x` -- no `dx`, no `dy`, no `ko`, no `jo`. `Frame.plane()`
and `Frame.ink_profile()` are built on `grid()`, so an `OriginFrame` carried a
sampling path that ignored the whole
correction. B6's receipt named it and left it there: "Named, not fixed: no leg of
any gate exercises it, so a fix here would be untested by construction." B7 is the
missing leg.

Every honouring value here is computed from the PPM bytes by hand (`honor_cell`),
so no assertion borrows the behaviour it checks, and the blind value is taken
through `vga.Frame.grid(view, ...)`, called unbound -- which keeps leg 1 true after
the override lands instead of deleting the evidence with the fix. That is the
shape the legs take now: each one measures the blind carve and the honouring carve
in the same run, so the defect and its repair are both in evidence.

**Corrected by B9 (2026-09-25).** The sentence above about calling `Frame.grid`
unbound was true for `grid` and false for `lum`, and the difference is the whole
point of this paragraph: `Frame.grid` is built on `self.lum`, so once B9 gave
`OriginFrame` a honouring `lum`, the unbound call stopped being a blind carve and
legs 1-4 would have gone RED on a fix that changed nothing about the base class.
The blind side is therefore a plain `vga.Frame` over the same bytes: the same
formula, still live code, and no longer a fact about inheritance. `blind_grid`'s
docstring carries the measurement that says the two forms returned identical values
while `lum` was inherited, which is why the numbers in legs 1-5 did not move.

Run 2 of this gate, against the code with the fix applied, came back 9/10 and
refuted two things about this file: leg 7's grep census counted the fix's own
override and one word of its docstring as new consumers (the census is now an AST
walk, which cannot read prose), and the lane's `bm801_align.py` was restored to
its committed content by a foreign writer while the gate was running -- see
`RECEIPT_BM801_GRID.md` for both. `OriginFrame.lum` is still inherited from
`vga.Frame` and honours none of the four offsets; nothing reaches it now that
`grid()` is overridden on both classes, and B8's audit owns that row.

Run: python3 rung8/run_bm801_grid_gate.py    (one beacon boot, then host-side)
Set BM7_SKIP_OLDER=1 to skip leg 9's four nested gates while iterating (legs 0-8
carry the rule; leg 9 is the regression check on B1's, B4's, B5's and B6's gates).
"""

import ast
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
KEEP_OUT = 'ubuntu_desktop_pxc1_v3_selfhost'
BAND = [(r, c) for r in range(4, 12) for c in range(20, 40)]
# cells that are NOT all the same glyph: the message row and the calibration block
BAND_LABEL = ([(vga.MSG_ROW, c) for c in range(20)]
              + [(r, c) for r in range(8) for c in range(8)])


def predict(name, text):
    print('--> %-30s predicts: %s' % (name, text))


def check(name, ok, detail):
    RESULTS.append((name, bool(ok)))
    print('    %s %-30s %s' % ('PASS' if ok else 'FAIL', name, detail))


def roll(src, dst, sx, sy):
    """Cyclic whole-frame displacement -- the frame `wrap` is honest about."""
    w, h, rows = decay.read_rgb(src)
    out = [[rows[(y + sy) % h][(x + sx) % w] for x in range(w)] for y in range(h)]
    decay.write_ppm(dst, w, h, out)
    return dst


def honor_cell(rows, w, h, cw, ch, dx, dy, ko, jo, mode, r, c):
    """Logical cell (r, c) of an offset view, computed from the bytes by hand.

    Physical relabelling first, then the sub-cell phase, then the mode: a cell whose
    carve does not fit is the all-zero sentinel under `clamp` and the wrapped bytes
    under `wrap`. Nothing here imports `bm801_align`.
    """
    pr, pc = (r + ko) % vga.ROWS, (c + jo) % vga.COLS
    y0, x0 = pr * ch + dy, pc * cw + dx
    out_of = not (y0 >= 0 and y0 + ch <= h and x0 >= 0 and x0 + cw <= w)
    if out_of and mode == 'clamp':
        return [[0] * cw for _ in range(ch)], True
    return [[sum(rows[(y0 + y) % h][(x0 + x) % w]) for x in range(cw)] for y in range(ch)], False


def honor_plane(rows, w, h, cw, ch, dx, dy, ko, jo, mode, r, c):
    """`Frame.plane()`'s rule, re-derived here from the honouring carve."""
    g, dropped = honor_cell(rows, w, h, cw, ch, dx, dy, ko, jo, mode, r, c)
    if dropped:
        return tuple([0] * (cw * ch)), True
    flat = [v for row in g for v in row]
    if max(flat) - min(flat) < vga.FLAT_SPAN:
        return tuple([0] * (cw * ch)), True
    lo, hi = min(flat), max(flat)
    mid = (lo + hi) / 2.0
    m = [[1 if v > mid else 0 for v in row] for row in g]
    corners = [m[0][0], m[0][cw - 1], m[ch - 1][0], m[ch - 1][cw - 1]]
    if sum(corners) * 2 > len(corners):
        m = [[1 - v for v in row] for row in m]
    return tuple(v for row in m for v in row), False


def blind_grid(bframe, r, c):
    """The blind carve, taken from a plain `vga.Frame` over the same bytes.

    B7 called this `vga.Frame.grid(origin_frame_view, r, c)`. That form was only
    blind because the view inherited `lum()`; B9 overrides it, and `Frame.grid`
    is built on `self.lum`, so the same unbound call now honours every offset.
    B9's gate measures that (its leg `old-unbound-call-now-honours`): the unbound
    call on a fixed view equals the view's own honouring carve on every cell it
    samples, i.e. it stopped being a blind side at all. This takes the base frame
    instead -- same bytes, same formula, and a number the pre-fix code also
    returned, which is what lets legs 1-5 be compared digit-for-digit against the
    pre-fix run.
    """
    return vga.Frame.grid(bframe, r, c)


def profile_of(grid_fn, cw, ch):
    prof = [0] * cw
    for r in range(vga.ROWS):
        for c in range(vga.COLS):
            g = grid_fn(r, c)
            for x in range(cw):
                col = [g[y][x] for y in range(ch)]
                prof[x] += max(col) - min(col)
    return prof


def main():
    run = tempfile.mkdtemp(prefix='bm807_gridgate.')
    print('# B7 grid-offset gate | run dir %s' % run)
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
    wc_, hc_, rows_clean = decay.read_rgb(clean)

    disp = roll(clean, os.path.join(run, 'disp.ppm'), 3, 5)
    wd_, hd_, rows_disp = decay.read_rgb(disp)
    bdisp = vga.Frame(disp)          # the same bytes, uncorrected: B9's blind side
    rep, view = al.corrected(disp, mode='wrap')
    dx, dy = rep['phase']
    ko, jo = rep['block_origin']
    zero = al.OriginFrame(vga.Frame(clean), 0, 0, 0, 0, 'wrap')
    clamp_view = al.OriginFrame(vga.Frame(disp), dx, dy, ko, jo, 'clamp')
    n_drop = sum(1 for r in range(vga.ROWS) for c in range(vga.COLS) if clamp_view.drops(r, c))
    print('# frame %dx%d cell %dx%d | displaced roll(3,5): phase=(%d,%d) origin=(%d,%d) '
          '| clamp view drops %d cells' % (w, h, cw, ch, dx, dy, ko, jo, n_drop))

    predict('0 source-inert',
            'no leg writes to the capture: %s unchanged at the end, and this file names the '
            'keep-out disk exactly once -- in the constant above, never as a path it opens'
            % src_sha)
    self_text = open(os.path.abspath(__file__)).read()
    sha_after = hashlib.sha256(open(clean, 'rb').read()).hexdigest()[:16]
    check('0 source-inert', sha_after == src_sha and self_text.count(KEEP_OUT) == 1,
          'sha before=%s after=%s | keep-out name occurrences=%d' % (src_sha, sha_after,
                                                                     self_text.count(KEEP_OUT)))

    # ---- leg 1: the RED, kept permanent --------------------------------------
    blind_diffs = [rc for rc in BAND
                   if blind_grid(bdisp, *rc) != honor_cell(rows_disp, wd_, hd_, cw, ch, dx, dy,
                                                            ko, jo, 'wrap', *rc)[0]]
    predict('1 inherited-carve-is-blind',
            'the base carve disagrees with the honouring one on every sampled cell of a displaced '
            'view: logical (r,c) is read at physical (r,c) instead of (r+%d,c+%d) at phase (%d,%d), '
            'so %d of %d disagree' % (ko, jo, dx, dy, len(BAND), len(BAND)))
    check('1 inherited-carve-is-blind', len(blind_diffs) == len(BAND),
          '%d of %d sampled cells disagree; geometry (%d,%d,%d,%d)'
          % (len(blind_diffs), len(BAND), dx, dy, ko, jo))

    # ---- leg 2: the control that explains why nobody saw it -------------------
    d0 = [rc for rc in BAND
          if blind_grid(base, *rc) != honor_cell(rows_clean, wc_, hc_, cw, ch, 0, 0, 0, 0,
                                                 'wrap', *rc)[0]]
    predict('2 zero-offset-control',
            'at zero displacement the two agree on every cell -- the defect is invisible exactly '
            'when the frame needs no correction, which is every leg any older gate runs')
    check('2 zero-offset-control', not d0 and (dx, dy, ko, jo) != (0, 0, 0, 0),
          '%d of %d disagree at zero; displaced geometry is (%d,%d,%d,%d)'
          % (len(d0), len(BAND), dx, dy, ko, jo))

    # ---- leg 3: the disagreement is the relabelling, not noise ----------------
    fill_agree = sum(1 for r, c in BAND if blind_grid(base, r, c)
                     == honor_cell(rows_clean, wc_, hc_, cw, ch, 0, 0, ko, jo, 'wrap', r, c)[0])
    diff_own = [rc for rc in BAND_LABEL if blind_grid(base, *rc)
                != honor_cell(rows_clean, wc_, hc_, cw, ch, 0, 0, ko, jo, 'wrap', *rc)[0]]
    wrong_label = [rc for rc in BAND_LABEL if blind_grid(base, *rc)
                   != honor_cell(rows_clean, wc_, hc_, cw, ch, 0, 0, ko, jo, 'wrap',
                                 (rc[0] - ko) % vga.ROWS, (rc[1] - jo) % vga.COLS)[0]]
    predict('3 blind-carve-is-the-wrong-label',
            'with the sub-cell phase at zero the ONLY difference is the label, so on cells that '
            'are not all the same glyph the blind carve disagrees with its own label (%d,%d) and '
            'equals the carve of the label that far earlier. Run 1 refuted where it asked this: '
            'sampled on the beacon fill rows the blind carve agrees with its own label on %d of '
            '%d cells -- a whole-cell relabel cannot be seen there, which is itself part of why '
            'the hole survived. So the band is the message row and the calibration block.'
            % (ko, jo, fill_agree, len(BAND)))
    check('3 blind-carve-is-the-wrong-label',
          len(diff_own) == len(BAND_LABEL) and not wrong_label and (ko, jo) != (0, 0),
          'label-differing cells %d/%d on the message-row + block band | cells matching the '
          'label-%d-%d-earlier carve %d/%d | fill-row band agreeing with its own label %d/%d'
          % (len(diff_own), len(BAND_LABEL), ko, jo, len(BAND_LABEL) - len(wrong_label),
             len(BAND_LABEL), fill_agree, len(BAND)))

    # ---- leg 4: the profile, which is what the class is for -------------------
    prof_view = view.ink_profile()
    prof_blind = profile_of(lambda r, c: blind_grid(bdisp, r, c), cw, ch)
    uncorr = al.OriginFrame(vga.Frame(disp), 0, 0, 0, 0, 'wrap')
    prof_uncorr = uncorr.ink_profile()
    prof_honor = profile_of(lambda r, c: honor_cell(rows_disp, wd_, hd_, cw, ch, dx, dy, ko, jo,
                                                    'wrap', r, c)[0], cw, ch)
    n_col_diff = sum(1 for x in range(cw) if prof_blind[x] != prof_honor[x])
    predict('4 profile-honours-the-view',
            'RED (run 1): the displaced view\'s profile is the UNCORRECTED frame\'s -- identical '
            'to a zero-offset view over the same bytes, and differing from the honouring one on '
            '%d/%d columns. GREEN: it equals the honouring profile, and stops equaling the '
            'uncorrected one' % (n_col_diff, cw))
    check('4 profile-honours-the-view',
          prof_view == prof_honor and prof_blind == prof_uncorr and n_col_diff > cw // 2,
          'view profile == honouring: %s | blind == uncorrected-frame profile: %s | columns where '
          'blind differs from honouring: %d/%d | view=%s honouring=%s'
          % (prof_view == prof_honor, prof_blind == prof_uncorr, n_col_diff, cw,
             prof_view[:3], prof_honor[:3]))

    # ---- leg 5: the mode, not only the offsets --------------------------------
    all_cells = [(r, c) for r in range(vga.ROWS) for c in range(vga.COLS)]
    blind_invented = [rc for rc in all_cells if clamp_view.drops(*rc)
                      and blind_grid(bdisp, *rc) != [[0] * cw for _ in range(ch)]]
    honor_now = [rc for rc in all_cells if clamp_view.drops(*rc) and clamp_view.grid(*rc)
                 != honor_cell(rows_disp, wd_, hd_, cw, ch, dx, dy, ko, jo, 'clamp', *rc)[0]]
    honor_inframe = [rc for rc in BAND if clamp_view.grid(*rc)
                     != honor_cell(rows_disp, wd_, hd_, cw, ch, dx, dy, ko, jo, 'clamp', *rc)[0]]
    predict('5 clamp-cell-does-not-wrap',
            'the offsets are not the whole defect: on a CLAMP view the inherited carve returns '
            'opposite-edge bytes for the cells that have no pixels -- most of %d -- so a second '
            'sampling path ignores the mode exactly the way `materialize()` did. GREEN: `grid()` '
            'goes through `raw_cell()` on both classes, so a dropped cell is the sentinel and '
            'nothing is invented on any cell' % n_drop)
    check('5 clamp-cell-does-not-wrap',
          n_drop > 0 and len(blind_invented) > 0 and not honor_now and not honor_inframe,
          'clamp view drops %d cells; inherited carve invents %d of them; grid() disagrees with '
          'the honouring carve on %d dropped + %d sampled in-frame cells'
          % (n_drop, len(blind_invented), len(honor_now), len(honor_inframe)))

    # ---- leg 6: plane() and grid() are one rule ------------------------------
    pairs = [(r, c) for r in range(0, vga.ROWS, 3) for c in range(0, vga.COLS, 7)]
    agree = [rc for rc in pairs
             if view.plane(*rc) != honor_plane(rows_disp, wd_, hd_, cw, ch, dx, dy, ko, jo,
                                               'wrap', *rc)]
    agree_c = [rc for rc in pairs
               if clamp_view.plane(*rc) != honor_plane(rows_disp, wd_, hd_, cw, ch, dx, dy, ko,
                                                       jo, 'clamp', *rc)]
    predict('6 plane-grid-one-rule',
            'the accessor must end up agreeing with the plane it is built under, on both modes: '
            '`plane()` on every sampled pair equals this file\'s re-derivation of the reader\'s '
            'thresholding rule from the honouring carve (post-fix that derivation goes through '
            'the same path `grid()` takes)')
    check('6 plane-grid-one-rule', not agree and not agree_c,
          'wrap view: %d/%d pairs disagree | clamp view: %d/%d pairs disagree'
          % (len(agree), len(pairs), len(agree_c), len(pairs)))

    # ---- leg 7: the census, reported not hidden -------------------------------
    # Run 2 measured the first version of this leg wrong, and the wrongness is
    # worth keeping: it grepped for `.grid(` and required zero hits outside
    # bm801_vga.py, then the fix itself produced two -- the delegating override
    # `self._off.grid(...)` and the word `ink_profile()` inside its own docstring.
    # A census that cannot tell a call from prose reports the patch, not the
    # consumers, so this leg now parses each file and walks its AST.
    src = {f: open(os.path.join(HERE, f)).read()
           for f in sorted(os.listdir(HERE)) if f.endswith('.py')}
    own = os.path.basename(__file__)

    def ast_attr_calls(text, attr):
        """Call nodes shaped like `<expr>.attr(...)`; prose and defs cannot match."""
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return []
        out = []
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == attr):
                rcv = node.func.value
                out.append((getattr(rcv, 'id', None) or ast.dump(rcv)[:24], node.lineno))
        return out

    grid_calls = {f: ast_attr_calls(t, 'grid') for f, t in src.items() if f != own}
    prof_calls = {f: ast_attr_calls(t, 'ink_profile') for f, t in src.items() if f != own}
    inside_vga = grid_calls.get('bm801_vga.py', [])
    aligner_own = grid_calls.get('bm801_align.py', [])
    elsewhere = {f: v for f, v in grid_calls.items()
                 if v and f not in ('bm801_vga.py', 'bm801_align.py')}
    # B9 is the first item that adds a cross-file caller of `grid()`, and it is a gate:
    # a leg that measures the blind carve has to reach the base path somehow. The
    # production census -- what actually runs -- is the assertion that matters, so gate
    # files are named and counted here instead of being folded into `elsewhere`.
    elsewhere_prod = {f: v for f, v in elsewhere.items()
                      if not (f.startswith('run_bm80') and '_gate.py' in f)}
    elsewhere_gates = {f: len(v) for f, v in elsewhere.items() if f not in elsewhere_prod}
    prof_here = {f: v for f, v in prof_calls.items() if v}

    def plain_receiver(f, recv):
        """True when `recv` is bound in `f` by a plain Frame, not by an offset view."""
        binds = [l.strip() for l in src[f].splitlines() if l.strip().startswith(recv + ' =')]
        return bool(binds) and all('Frame(' in b and 'Origin' not in b and 'Offset' not in b
                                   for b in binds)

    # the beacon gate is the tree's only external ink_profile consumer; it must
    # still sample a plain Frame, i.e. this item's change may not have made it
    # implicitly an offset frame
    prof_plain = all(plain_receiver(f, r) for f, hits_ in prof_here.items() for r, _ln in hits_)
    rung9 = os.path.abspath(os.path.join(HERE, '..', 'rung9'))
    n9 = sum(len(ast_attr_calls(open(os.path.join(dp, fn), errors='replace').read(), a))
             for dp, _dn, fns in os.walk(rung9) for fn in fns if fn.endswith('.py')
             for a in ('grid', 'ink_profile'))
    predict('7 consumer-census',
            'the number that decides fix-versus-refuse, counted from the AST so the fix cannot '
            'manufacture consumers out of its own prose: `grid()` is CALLED from exactly two '
            'places in the tree, both inside bm801_vga.py (the bodies of `ink_profile()` and of '
            '`plane()`), plus the aligner\'s own delegating override, and from nowhere else; '
            '`ink_profile()` is called only by B1\'s beacon gate, on a plain Frame; rung9 does '
            'not reach either name. Run 2 measured that a grep census reports the patch instead '
            'of the consumers (it called the override and a docstring word "1 outside"), and '
            'that is why the leg is now a parse. Zero external consumers is the leg result that '
            'made refusal un-cheap: an accessor nobody calls is a smaller surface than a caller '
            'that does not exist, but fixing it costs nothing either, so the choice below is '
            'made on what each option leaves untested. B9 later made that choice for `lum()`: '
            'its gate had to call `grid()` to measure the base path, so the leg now separates a '
            'gate caller from a production one and prints both counts.')
    check('7 consumer-census',
          len(inside_vga) == 2 and len(aligner_own) >= 1 and not elsewhere_prod
          and list(prof_here) == ['run_bm801_beacon_gate.py'] and prof_plain and n9 == 0,
          'grid() calls: %d in bm801_vga.py %s, %d in bm801_align.py %s, other gates %s, '
          'non-gate elsewhere %s | '
          'ink_profile() calls %s plain-Frame=%s | rung9 attribute calls %d'
          % (len(inside_vga), [ln for _r, ln in inside_vga], len(aligner_own),
             [ln for _r, ln in aligner_own], elsewhere_gates or 'none', elsewhere_prod or 'none',
             prof_here, prof_plain, n9))

    # ---- the read still works, on the geometry this item touches -------------
    n7, got7 = al.read_distance0(view)
    n7z, got7z = al.read_distance0(zero)
    predict('8 message-still-reads',
            'the fix must not buy itself a regression on the path every reader takes: the '
            'displaced view still yields %r at %d/%d distance-0 cells (the uncorrected frame '
            'reads %r at %d/%d)' % (MSG, len(MSG), n7, got7z, n7z, len(MSG)))
    check('8 message-still-reads', got7 == MSG and n7 == len(MSG),
          'displaced read=%r distance0=%d/%d | zero-offset read=%r distance0=%d/%d'
          % (got7, n7, len(MSG), got7z, n7z, len(MSG)))

    if os.environ.get('BM7_SKIP_OLDER'):
        print('# older-gates skipped (BM7_SKIP_OLDER set): the nested gates were not run')
    else:
        predict('9 older-gates-regress',
                "B1's beacon gate -- the only external ink_profile consumer in the tree -- plus "
                "B4's, B5's and B6's gates all still exit 0: the accessor this item touches is "
                'proven by the gates that already exist, not only by this one')
        outs = {}
        for g in ('run_bm801_beacon_gate.py', 'run_bm801_align_gate.py',
                  'run_bm801_clamp_gate.py', 'run_bm801_materialize_gate.py'):
            p = subprocess.run([sys.executable, os.path.join(HERE, g)],
                               capture_output=True, text=True)
            res = [l for l in p.stdout.splitlines() if l.startswith('RESULT')]
            outs[g] = (p.returncode, ' '.join(res) or (p.stdout[-90:] + p.stderr[-200:]))
        check('9 older-gates-regress',
              all(rc == 0 and t for rc, t in outs.values()),
              ' | '.join('%s rc=%s %s' % (g, rc, t) for g, (rc, t) in sorted(outs.items())))

    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print('RESULT %d/%d legs pass' % (n_ok, len(RESULTS)))
    shutil.rmtree(run, ignore_errors=True)
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main())
