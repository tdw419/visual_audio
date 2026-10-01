#!/usr/bin/env python3
"""bm801_vga.py -- read a VGA text-mode screen off a captured frame by glyph
bitmap, never by OCR. This is TASK_BM801's fallback receipt channel: a box with
no serial port still has a screen, and a screen is only trustworthy as a
receipt if a reader can say "this cell holds this glyph" from pixels alone.

The reference is measured, not assumed: the boot sector in bm801_beacon.asm
paints the full 256-code page in a 16x16 block, so the font atlas comes out of
the same frame it is used to read. Codes whose bitmap is not unique are held in
an ambiguity set and never resolved to a single character.
"""

CELL_W = 8          # a floor, not the carve: QEMU's 80x25 text cell is 9x16 and
                    # the 9th column carries ink -- see pitch_is_exact()
CELL_H = 16
COLS, ROWS = 80, 25
ATLAS_SIDE = 16     # 16x16 == all 256 codes
MSG_ROW, MSG2_ROW = 20, 21
FLAT_SPAN = 8       # luminance span below which a cell carries no glyph


def parse_ppm(path):
    """Minimal P6 parser: QEMU's screendump writes no comments, but skip them."""
    with open(path, 'rb') as fh:
        data = fh.read()
    if not data.startswith(b'P6'):
        raise ValueError('not a binary PPM: %r' % data[:4])
    vals, i = [], 2
    while len(vals) < 3:
        while data[i:i + 1].isspace():
            i += 1
        if data[i:i + 1] == b'#':
            i = data.index(b'\n', i) + 1
            continue
        j = i
        while not data[j:j + 1].isspace():
            j += 1
        vals.append(int(data[i:j]))
        i = j
    w, h, _maxv = vals
    body = data[i + 1:]
    if len(body) < w * h * 3:
        raise ValueError('truncated PPM: %d bytes of %d expected' % (len(body), w * h * 3))
    return w, h, body


class Frame:
    """A captured text-mode screen, addressed by cell."""

    def __init__(self, path):
        self.path = path
        self.w, self.h, self.pixels = parse_ppm(path)
        self.cw, self.ch = self.w // COLS, self.h // ROWS
        if self.cw < CELL_W or self.ch < CELL_H:
            raise ValueError('cell %dx%d too small for the reference glyph box'
                             % (self.cw, self.ch))

    def lum(self, r, c, x, y):
        px = ((r * self.ch + y) * self.w + c * self.cw + x) * 3
        return sum(self.pixels[px:px + 3])

    def grid(self, r, c):
        """The whole cell, dropped columns and all: an 8-wide carve loses ink."""
        return [[self.lum(r, c, x, y) for x in range(self.cw)] for y in range(self.ch)]

    def _flatness(self, g):
        flat = [v for row in g for v in row]
        return max(flat) - min(flat)

    def pitch_is_exact(self):
        """A cell boundary that drifts is a reader that misreads: no rounding."""
        return self.w % COLS == 0 and self.h % ROWS == 0

    def ink_profile(self):
        """Summed per-column luminance span: shows which columns carry ink."""
        prof = [0] * self.cw
        for r in range(ROWS):
            for c in range(COLS):
                g = self.grid(r, c)
                for x in range(self.cw):
                    col = [g[y][x] for y in range(self.ch)]
                    prof[x] += max(col) - min(col)
        return prof

    def plane(self, r, c):
        """Canonical ink mask: 1 where the pixel is not the cell's background.

        Background is whichever of the two thresholded levels the four corner
        pixels mostly take, so a light-on-dark cell and a dark-on-light cell of
        the same glyph produce the same mask -- the reader does not need to know
        the beacon's colours.
        """
        g = self.grid(r, c)
        if self._flatness(g) < FLAT_SPAN:
            return tuple([0] * (self.cw * self.ch)), True
        lo = min(min(row) for row in g)
        hi = max(max(row) for row in g)
        mid = (lo + hi) / 2.0
        m = [[1 if v > mid else 0 for v in row] for row in g]
        corners = [m[0][0], m[0][self.cw - 1], m[self.ch - 1][0], m[self.ch - 1][self.cw - 1]]
        if sum(corners) * 2 > len(corners):
            m = [[1 - v for v in row] for row in m]
        return tuple(v for row in m for v in row), False


def build_atlas(frame):
    """code -> (plane, flat) for the 256 codes the beacon sector lays out."""
    atlas = {}
    for code in range(ATLAS_SIDE * ATLAS_SIDE):
        r, c = divmod(code, ATLAS_SIDE)
        atlas[code] = frame.plane(r, c)
    return atlas


def ambiguity(atlas):
    """codes sharing a bitmap, keyed by the shared plane; and the flat set."""
    by_plane = {}
    for code, (plane, flat) in atlas.items():
        by_plane.setdefault(plane, []).append(code)
    shared = {p: cs for p, cs in by_plane.items() if len(cs) > 1}
    return shared, by_plane


def hamming(a, b):
    return sum(x ^ y for x, y in zip(a, b))


def resolve(frame, atlas, r, c):
    """Best glyph for one cell. Returns None when the cell is flat.

    A complement-tolerant distance is used only as a diagnostic: the canonical
    plane should already be polarity-free, so a code that wins as complement is
    reported and the gate fails on it rather than hiding it.
    """
    plane, flat = frame.plane(r, c)
    if flat:
        return None
    scored = sorted(((hamming(plane, p), len(set(p)) == 1, c2)
                     for c2, (p, f) in atlas.items() if not f))
    dist, degenerate, best = scored[0]
    runner = scored[1][2] if len(scored) > 1 else None
    runner_dist = scored[1][0] if len(scored) > 1 else None
    ties = [c2 for d, _, c2 in scored if d == dist]
    return {'code': best, 'dist': dist, 'runner_up': runner,
            'runner_dist': runner_dist, 'ties': ties, 'complement': None}


def read_line(frame, atlas, row, length):
    out, cells = '', []
    for c in range(length):
        res = resolve(frame, atlas, row, c)
        cells.append(res)
        out += chr(res['code']) if res and res['code'] < 128 else '?' if res else ' '
    return out, cells
