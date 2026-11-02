#!/usr/bin/env python3
"""bm801_align.py -- recover the pixel grid's phase before the reader carves it.

B3 (`bm801_reader_decay.py`) measured the case a real capture is actually in: a
one-pixel shift of the whole frame MISREADS the receipt, and `pitch_is_exact()`
cannot see it, because a shifted 720x400 still divides evenly into 80x25. A
screendump is pixel-exact by construction; a photograph of a monitor is not. So
the receipt channel is unusable off-hardware until something recovers the grid
-- and recovering it must not become a licence to shift until the answer looks
right.

The phase signal is the boot sector's own redundancy: `bm801_beacon.asm` lays
out all 256 font codes in a 16x16 calibration block, so the frame carries its
own reference bitmaps. Every cell OFF the block is sampled at each candidate
phase and scored on how many of them carve to a plane that matches some block
entry exactly. At the true phase that is all of them (the carve is the same
carve that produced the reference); one pixel off, ink from the neighbouring
cell bleeds across the cell boundary and the exact matches collapse. This is
the whole-frame version of "maximise exact matches", not a match inside the
block -- a block cell compared against an atlas built from the same frame and
the same offset always matches itself, which would score every phase equally.

Two rules are load-bearing, both from B3's RED leg:
  * `align` may only ever INCREASE the number of distance-0 cells in what the
    reader actually reads, so a search that "fixes" an already-clean frame is a
    bug, and the guard is measured through `bm801_vga`, not through this file's
    own scoring;
  * it reports the offset it found instead of silently returning a shifted
    frame, because a real capture's misalignment is a measured fact about the
    box and the operator has to see it.

Run: python3 rung8/bm801_align.py <frame.ppm>   (no boot, no hardware, ~20 s)
"""

import sys
import time

HERE = __import__('os').path.dirname(__import__('os').path.abspath(__file__))
sys.path.insert(0, HERE)
import bm801_vga as vga          # noqa: E402

MSG = 'BM801-RECEIPT-OK>0123456789ABCDEF'

# What a cell this frame's mode refuses to sample is written as: the same all-zero
# plane `plane()` returns for a dropped cell, so the file and the mask agree.
SENTINEL = (0, 0, 0)

# Everything but the calibration block: the 9 rows below it (the beacon's fill,
# the two message rows, the tail rows) and the block's own rows to the right of
# column 15. Cells inside the block are excluded on purpose -- see the docstring.
def sample_cells(cols=vga.COLS, rows=vga.ROWS, block=vga.ATLAS_SIDE):
    cells = [(r, c) for r in range(block, rows) for c in range(cols)]
    cells += [(r, c) for r in range(block) for c in range(block, cols)]
    return cells


class OffsetFrame(vga.Frame):
    """A Frame whose cell carve starts at pixel (dx, dy), in one of two modes.

    Same pixels, same dimensions: only the sampling origin moves, so every
    existing reader routine works on it unchanged and `pitch_is_exact()` keeps
    reporting the frame's real divisibility rather than the aligner's opinion.

    `wrap` (the default, and B3/B4's behaviour) is how B3's `shift` knob
    degrades a frame: a carve that runs off an edge re-enters from the opposite
    one. That is a *self-consistent* frame -- a cyclic roll really does carry
    those pixels -- and it is also the thing a photograph of a monitor cannot
    do. `clamp` is the capture-shaped answer: a cell whose carve does not fit
    inside the pixels that exist is dropped, so the usable-cell set shortens
    and nothing is invented to fill it. Dropping is done at `plane()` because
    every reader, scorer and atlas in the tree goes through it.
    """

    def __init__(self, base, dx=0, dy=0, mode='wrap'):
        self.path, self.w, self.h, self.pixels = base.path, base.w, base.h, base.pixels
        self.cw, self.ch = base.cw, base.ch
        self.dx, self.dy = dx, dy
        self.mode = mode

    def in_frame(self, r, c):
        """True when this cell's whole carve lies inside the captured pixels."""
        y0, x0 = r * self.ch + self.dy, c * self.cw + self.dx
        return y0 >= 0 and y0 + self.ch <= self.h and x0 >= 0 and x0 + self.cw <= self.w

    def drops(self, r, c):
        """True when this frame's mode refuses to sample the cell at all."""
        return self.mode == 'clamp' and not self.in_frame(r, c)

    def plane(self, r, c):
        if self.drops(r, c):
            return tuple([0] * (self.cw * self.ch)), True
        return vga.Frame.plane(self, r, c)

    def rgb(self, r, c, x, y):
        """One RGB byte of logical cell (r, c), or `SENTINEL` where this mode has no pixels.

        B10's row: until this item the body was the raw phase arithmetic and a
        `self.pixels` slice, so under `clamp` it returned the opposite edge -- a byte the
        capture never showed -- while `raw_cell()`, which tests `drops()` first, returned
        the sentinel for the same cell. The two accessors disagreed about one pixel of a
        dropped cell, and a caller that took a single pixel rather than a cell got an
        invented edge. `wrap` is untouched by this: `drops()` is false for every cell
        there, so the arithmetic below still runs on all of them.
        """
        if self.drops(r, c):
            return SENTINEL
        y0, x0 = (r * self.ch + y + self.dy) % self.h, (c * self.cw + x + self.dx) % self.w
        px = (y0 * self.w + x0) * 3
        return self.pixels[px:px + 3]

    def raw_cell(self, r, c):
        """The cell's bytes as this frame's mode sees them, row-major.

        `plane()` is the accessor every reader, scorer and atlas goes through, and
        `drops()` is the gate behind its clamp branch; a writer that re-derives its
        own indices honours neither, which is how a clamp report came to authorize a
        file of opposite-edge pixels. Sampling through here leaves one rule.
        """
        if self.drops(r, c):
            return [SENTINEL] * (self.cw * self.ch)
        return [tuple(self.rgb(r, c, x, y)) for y in range(self.ch) for x in range(self.cw)]

    def grid(self, r, c):
        """The cell as luminance rows, sampled through `raw_cell()`.

        `vga.Frame.grid` addresses the file at `(r*ch+y)*w + c*cw+x` -- no phase, no
        relabelling, no mode -- and `Frame.plane()` and `Frame.ink_profile()` are both
        built on it, so an offset frame carried a second sampling path that ignored
        the correction it was created to apply. Deriving the rows from `raw_cell()`
        leaves one rule again: the same bytes `plane()` sees, and a clamped cell that
        is the sentinel rather than the opposite edge of the capture.
        """
        flat = self.raw_cell(r, c)
        return [[sum(px) for px in flat[y * self.cw:(y + 1) * self.cw]]
                for y in range(self.ch)]

    def lum(self, r, c, x, y):
        """One pixel's luminance, taken out of `rgb()` so the two cannot disagree.

        B8's row read `NO (wraps)` here: the body used to be its own `% h` / `% w`
        arithmetic and a `self.pixels` slice, so under `clamp` it returned the opposite
        edge for the cells `plane()` refuses to sample. Routing through `rgb()` puts the
        `drops()` gate on the single-pixel path too, and a dropped pixel is then
        `sum(SENTINEL)`, which is the zero `raw_cell()`, `grid()` and `plane()` already
        return for it -- the same equality B9 measured for `OriginFrame.lum`.
        """
        return sum(self.rgb(r, c, x, y))


def edge_invented(frame, cells):
    """Cells `frame` would sample through an edge: bytes of the file, not of the scene."""
    return [rc for rc in cells if not frame.in_frame(*rc)]


class OriginFrame(vga.Frame):
    """A Frame that reads LOGICAL cell (r, c) from PHYSICAL cell (r+ko, c+jo).

    A capture displaced by whole cells needs relabelling, not just a sub-pixel
    phase: shifting the carve by 8 px realigns the grid but slides every glyph
    one column left, so the block's own entries come out mislabelled and the
    message reads as garbage with distance 0. This frame applies both, and the
    block origin is found from the sector's fill rather than assumed.
    """

    def __init__(self, base, dx=0, dy=0, ko=0, jo=0, mode='wrap'):
        self.path, self.w, self.h, self.pixels = base.path, base.w, base.h, base.pixels
        self.cw, self.ch = base.cw, base.ch
        self.dx, self.dy, self.ko, self.jo = dx, dy, ko, jo
        self.mode = mode
        self._off = OffsetFrame(base, dx, dy, mode)

    def physical(self, r, c):
        return (r + self.ko) % vga.ROWS, (c + self.jo) % vga.COLS

    def in_frame(self, r, c):
        return self._off.in_frame(*self.physical(r, c))

    def plane(self, r, c):
        return self._off.plane(*self.physical(r, c))

    def drops(self, r, c):
        return self._off.drops(*self.physical(r, c))

    def raw_cell(self, r, c):
        return self._off.raw_cell(*self.physical(r, c))

    def lum(self, r, c, x, y):
        """One pixel of the cell this frame samples: relabelled, phase-shifted, mode-aware.

        Until B9 this was `vga.Frame.lum` untouched, indexing `self.pixels` at
        `(r*ch+y)*w + c*cw+x` -- no `dx`, no `dy`, no `ko`, no `jo`, no mode -- which is
        what B8's table measured as `NO (blind)` on all four offsets and `NO (wraps)`
        under `clamp`. Taking the byte out of `raw_cell()` leaves one sampling rule on
        this class: the same bytes `plane()` and `grid()` see, sentinel row included.
        The cost is a whole cell carve per pixel, and it is nobody's hot path -- both
        classes override `grid()`, so nothing in the reader calls `lum()` any more.
        """
        return sum(self.raw_cell(r, c)[y * self.cw + x])

    def grid(self, r, c):
        return self._off.grid(*self.physical(r, c))

    def pitch_is_exact(self):
        return self._off.pitch_is_exact()


def fill_grid(fr, cells):
    """Per-cell: is this the sector's repeated fill glyph (or blank)?

    Cells the frame cannot sample at all are left out rather than counted as
    blank: under `clamp` a dropped cell and an empty cell are different facts,
    and calling one the other is the invention this mode exists to avoid.
    """
    in_frame = getattr(fr, 'in_frame', None)
    if in_frame:
        cells = [rc for rc in cells if in_frame(*rc)]
    planes = [fr.plane(r, c) for r, c in cells]
    counts = {}
    for p, (_r, _c) in zip(planes, cells):
        counts[p] = counts.get(p, 0) + 1
    modal = max(counts, key=lambda k: counts[k])
    grid = {}
    for p, (r, c) in zip(planes, cells):
        grid[(r, c)] = 1 if p == modal else 0
    return grid, counts[modal], len(cells)


def find_block_origin(fr):
    """The 16x16 window with the least fill: the calibration block, wherever it landed."""
    grid, n_fill, n_cells = fill_grid(fr, [(r, c) for r in range(vga.ROWS)
                                           for c in range(vga.COLS)])
    best = None
    for ko in range(vga.ROWS):
        for jo in range(vga.COLS):
            inside = sum(grid.get(((ko + r) % vga.ROWS, (jo + c) % vga.COLS), 0)
                         for r in range(vga.ATLAS_SIDE) for c in range(vga.ATLAS_SIDE))
            if best is None or inside < best[0]:
                best = (inside, ko, jo)
    return {'origin': (best[1], best[2]), 'fill_cells_in_window': best[0],
            'fill_cells_total': n_fill, 'cells': n_cells}


def exact_matches(frame, cells):
    """How many of `cells` carve to a plane that some calibration-block entry has."""
    atlas = vga.build_atlas(frame)
    refs = set(p for p, flat in atlas.values() if not flat)
    n = 0
    for r, c in cells:
        plane, flat = frame.plane(r, c)
        if not flat and plane in refs:
            n += 1
    return n


def search(base, cells, mode='wrap'):
    """Rank every sub-cell phase by exact matches, best first (ties: smallest phase)."""
    scored = [(exact_matches(OffsetFrame(base, dx, dy, mode), cells), dx, dy)
              for dy in range(base.ch) for dx in range(base.cw)]
    scored.sort(key=lambda t: (-t[0], t[1], t[2]))
    return scored


def read_distance0(fr, row=vga.MSG_ROW, msg=MSG):
    """What the unmodified reader sees from this frame view: exact cells, and the string."""
    atlas = vga.build_atlas(fr)
    got, cells = vga.read_line(fr, atlas, row, len(msg))
    return sum(1 for c in cells if c and c['dist'] == 0), got


def corrected(path, msg=MSG, row=vga.MSG_ROW, mode='wrap'):
    """Phase search + block registration in one shot. Returns (report, view or None)."""
    base = vga.Frame(path)
    if not base.pitch_is_exact():
        return {'refused': 'pitch: %dx%d is not divisible by %dx%d'
                % (base.w, base.h, vga.COLS, vga.ROWS), 'mode': mode}, None
    cells = sample_cells()
    scored = search(base, cells, mode)
    best, bx, by = scored[0]
    at_zero = next((s for s, dx, dy in scored if (dx, dy) == (0, 0)), -1)
    tied = sum(1 for s, _x, _y in scored if s == best)
    naive_n, naive_got = read_distance0(OffsetFrame(base, 0, 0, mode), row=row, msg=msg)
    phase_n, phase_got = read_distance0(OffsetFrame(base, bx, by, mode), row=row, msg=msg)
    reg = find_block_origin(OffsetFrame(base, bx, by, mode))
    ko, jo = reg['origin']
    view = OriginFrame(base, bx, by, ko, jo, mode)
    full_n, full_got = read_distance0(view, row=row, msg=msg)
    # Sampled at (dx, dy) with the mode-independent geometry, so the count means
    # the same thing whether the caller is scoring or clamping.
    edge = OffsetFrame(base, bx, by)
    msg_edge = edge_invented(view, [(row, c) for c in range(len(msg))])
    return {
        'refused': None,
        'mode': mode,
        'size': '%dx%d' % (base.w, base.h),
        'cell': '%dx%d' % (base.cw, base.ch),
        'phase': (bx, by),
        'exact_offblock': best,
        'exact_offblock_total': len(cells),
        'exact_offblock_at_zero': at_zero,
        'phases_tied_best': tied,
        'phases_searched': len(scored),
        'block_origin': (ko, jo),
        'fill_cells_in_window': reg['fill_cells_in_window'],
        'fill_cells_total': reg['fill_cells_total'],
        'cells_scored': reg['cells'],
        'cells_edge_invented': len(edge_invented(edge, cells)),
        'msg_cells_edge_invented': len(msg_edge),
        'distance0_naive': naive_n,
        'distance0_phase_only': phase_n,
        'distance0_corrected': full_n,
        'read_naive': naive_got,
        'read_corrected': full_got,
    }, view


def materialize(view, dst):
    """Write the view out as a real PPM, so a plain Frame can confirm it.

    An in-memory view proves the aligner can read; only a written file proves the
    correction is a fact about the pixels and not a story the report tells.

    The bytes come from `view.raw_cell()`, the same accessor `plane()` samples
    through, so the mode that decided the report is the mode of the file: a clamped
    view writes its out-of-frame cells as SENTINEL instead of reaching round the
    edge for them, and says how many it did. Refusing to write at all is the wrong
    shape -- a file that says nothing is how this hole stayed open. When anything was
    sentinelled the PPM header carries that count too, so the artifact cannot be
    separated from the claim that produced it. Returns a small report; callers that
    only wanted the path can ignore it.
    """
    bands = [[view.raw_cell(r, c) for c in range(vga.COLS)] for r in range(vga.ROWS)]
    sentinelled = sum(1 for r in range(vga.ROWS) for c in range(vga.COLS) if view.drops(r, c))
    with open(dst, 'wb') as fh:
        fh.write(b'P6\n%d %d\n' % (view.w, view.h))
        if sentinelled:
            fh.write(b'# bm801 materialize: mode=%s sentinelled=%d of %d cells\n'
                     % (view.mode.encode(), sentinelled, vga.ROWS * vga.COLS))
        fh.write(b'255\n')
        for r in range(vga.ROWS):
            for y in range(view.ch):
                for cell in bands[r]:
                    for px in cell[y * view.cw:(y + 1) * view.cw]:
                        fh.write(bytes(px))
    return {'dst': dst, 'mode': view.mode, 'cells': vga.ROWS * vga.COLS,
            'sentinelled': sentinelled}


def align(path, msg=MSG, row=vga.MSG_ROW, mode='wrap'):
    """Decide whether to correct, under the increase-only rule. Never mutates the frame.

    The report is the product: the winning phase, where the calibration block
    turned out to sit, what the reader saw before and after, and whether
    anything was applied at all. `declined` names the rule that stopped it, so a
    real capture's misalignment still reaches the operator instead of being
    quietly optimised away.

    Under `mode='clamp'` one more rule binds, and it binds before the score: if
    a message-row cell of the chosen view sits where the capture has no pixels,
    the read is refused and the reason says so -- a distance-0 count earned from
    an edge the camera never showed is not a receipt, whatever else is also true
    of that phase.
    """
    t0 = time.time()
    try:
        rep, view = corrected(path, msg=msg, row=row, mode=mode)
    except Exception as exc:                        # noqa: BLE001 - refusing IS a result
        return {'refused': 'parse: %s' % str(exc)[:90], 'applied': False, 'phase': None,
                'mode': mode}
    if rep['refused']:
        rep['applied'] = False
        rep['seconds'] = round(time.time() - t0, 1)
        return rep
    # The edge rule is judged before the score, not as a veto on an otherwise
    # accepted phase: run 3 measured a clamped view with the whole message row
    # off-capture whose score ALSO failed, and increase-only named itself first,
    # hiding the more important reason.
    rep['declined_by_edge'] = bool(mode == 'clamp' and rep['msg_cells_edge_invented'])
    rep['applied'] = (not rep['declined_by_edge']
                      and rep['distance0_corrected'] > rep['distance0_naive']
                      and (rep['phase'], rep['block_origin']) != ((0, 0), (0, 0)))
    if not rep['applied']:
        rep['declined'] = (
            'clamp: %d of the %d message-row cells fall where this capture has no '
            'pixels, so the (%s,%s) phase is not confirmable'
            % (rep['msg_cells_edge_invented'], len(msg), rep['phase'][0], rep['phase'][1])
            if rep.get('declined_by_edge') else
            'no correction needed: the uncorrected read already has every cell '
            'at distance 0' if rep['distance0_naive'] == len(msg) else
            'increase-only: the (%s,%s) phase with block at %s yields %d '
            'distance-0 cells, no better than %d uncorrected'
            % (rep['phase'][0], rep['phase'][1], rep['block_origin'],
               rep['distance0_corrected'], rep['distance0_naive']))
    else:
        rep['declined'] = None
    rep['seconds'] = round(time.time() - t0, 1)
    return rep


REPORT_KEYS = ('mode', 'size', 'cell', 'phase', 'block_origin', 'exact_offblock',
               'exact_offblock_total', 'exact_offblock_at_zero', 'phases_tied_best',
               'fill_cells_in_window', 'fill_cells_total', 'cells_edge_invented',
               'msg_cells_edge_invented', 'distance0_naive',
               'distance0_phase_only', 'distance0_corrected', 'applied')


def report(rep):
    if rep.get('refused'):
        return 'refused=<%s> applied=False' % rep['refused']
    line = ' '.join('%s=%s' % (k, rep[k]) for k in REPORT_KEYS)
    line += ' read_corrected=%r' % rep['read_corrected']
    if rep['declined']:
        line += ' declined=<%s>' % rep['declined']
    return line + ' seconds=%s' % rep['seconds']


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    mode = sys.argv[2] if len(sys.argv) > 2 else 'wrap'
    if mode not in ('wrap', 'clamp'):
        print('mode must be wrap or clamp, got %r' % mode)
        sys.exit(2)
    print(report(align(sys.argv[1], mode=mode)))
    sys.exit(0)
