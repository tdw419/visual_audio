"""Glyph in-image text console (DTF-2, claim-queue round-5 item 10).

Renders a PRT byte stream (GlyphCPUv2.output — glyph_isa_v2.py:586/1075 —
collected by the shell each turn) into a reserved pixel band using the
existing IBM VGA 8x16 font (tools/vga_font_8x16.py). The band is a
glass-TTY: a bounded row-ring of text rows rendered host-side from the
glyph-side output stream. No blitter, no hardware-scroll claims — the
ring is a renderer concern, per the DTF amendment's glass-TTY boundary.

Decode is glyph-side: every 8x16 cell of the band is XOR/exact-matched
against the font bitmaps themselves (never against a stored copy of the
input), so a pixel-region read recovers the exact string or fails.

Layout contract:
  - one text cell = 8x16 px (the VGA font cell)
  - band = rows*16 px tall, cols*8 px wide
  - lit pixel = `on` RGB, unlit = `off` RGB; nothing else is legal in a
    well-formed band (strict decode raises on any third color)
  - chars missing from the font render as '?' (the font's coverage is
    95 glyphs — all printable ASCII since BK-19, 2026-09-23; chars
    missing before that, the bracket/brace family, used to be
    replaced by '?', never silently blanked)

Batch invariant: this module never touches stdin/stdout — it is pure
bytes-in, pixels-out.
"""
from __future__ import annotations

from collections import deque

import numpy as np

from tools.vga_font_8x16 import VGA_FONT_8X16, get_vga_bitmap

CELL_W = 8
CELL_H = 16

DEFAULT_ROWS = 8
DEFAULT_COLS = 40
DEFAULT_ON = (255, 255, 255)
DEFAULT_OFF = (0, 0, 0)

# Reverse map: glyph bitmap bits (16 tuples of 8 bits, row-major) -> char.
# Built once from the font itself; the space glyph is all-zero bits, so an
# all-zero cell decodes to ' ' by construction.
_BITS_TO_CHAR: dict[tuple[tuple[int, ...], ...], str] = {}
_ZERO_BITS = tuple((0,) * CELL_W for _ in range(CELL_H))
for _ch, _rows in VGA_FONT_8X16.items():
    _bits = tuple(
        tuple((row >> bit) & 1 for bit in range(7, -1, -1)) for row in _rows
    )
    _BITS_TO_CHAR[_bits] = _ch


def _cell_bits(band: np.ndarray, row: int, col: int, on, off) -> tuple[tuple[int, ...], ...]:
    """Extract the 16x8 bit pattern of one cell from an RGB band."""
    y0, x0 = row * CELL_H, col * CELL_W
    cell = band[y0:y0 + CELL_H, x0:x0 + CELL_W, :]
    bits = []
    for r in range(CELL_H):
        row_bits = []
        for c in range(CELL_W):
            px = tuple(int(v) for v in cell[r, c])
            if px == on:
                row_bits.append(1)
            elif px == off:
                row_bits.append(0)
            else:
                raise ValueError(
                    f"non-{off}/{on} pixel {px} at band ({y0 + r},{x0 + c}) — "
                    "corrupt or foreign band"
                )
        bits.append(tuple(row_bits))
    return tuple(bits)


class TextConsole:
    """A bounded row-ring of text rows rendered into a pixel band."""

    def __init__(self, rows: int = DEFAULT_ROWS, cols: int = DEFAULT_COLS,
                 on=DEFAULT_ON, off=DEFAULT_OFF):
        self.rows = rows
        self.cols = cols
        self.on = tuple(on)
        self.off = tuple(off)
        self._lines: deque[str] = deque(maxlen=rows)

    # -- input (the PRT byte stream) ------------------------------------
    def feed_bytes(self, data: bytes) -> None:
        """Feed one turn's PRT byte stream (GlyphCPUv2.output as bytes)."""
        self.feed(data.decode("utf-8", errors="replace"))

    def feed(self, text: str) -> None:
        """Feed one line (or \\n-split text) into the ring."""
        for line in text.split("\n"):
            self._lines.append(line)

    # -- rendering -------------------------------------------------------
    def render_band(self) -> np.ndarray:
        """Render the ring into (rows*16, cols*8, 3) uint8. Rows beyond the
        ring render blank; lines are truncated to cols (glass-TTY width)."""
        band = np.empty((self.rows * CELL_H, self.cols * CELL_W, 3), dtype=np.uint8)
        band[:, :] = np.array(self.off, dtype=np.uint8)
        lines = list(self._lines)[-self.rows:]
        for i, line in enumerate(lines):
            band_row = self.rows - len(lines) + i  # bottom-anchored
            for j, ch in enumerate(line[:self.cols]):
                self._blit(band, band_row, j, ch)
        return band

    def _blit(self, band: np.ndarray, row: int, col: int, ch: str) -> None:
        if ch not in VGA_FONT_8X16:
            ch = "?"  # documented replacement — never a silent blank
        bitmap = get_vga_bitmap(ch)  # (16, 8) of 0/255
        y0, x0 = row * CELL_H, col * CELL_W
        on = np.array(self.on, dtype=np.uint8)
        mask = bitmap > 0
        region = band[y0:y0 + CELL_H, x0:x0 + CELL_W, :]
        region[mask] = on

    # -- glyph-side decode -----------------------------------------------
    def decode_band(self, band: np.ndarray) -> str:
        """Decode a band back to text by exact-matching every cell against
        the font bitmaps. Raises on any cell that matches no glyph (which
        is what makes this decode discriminating, not a host-side echo).
        Ring-padding rows (blank, above the bottom-anchored content) are
        dropped — decode returns exactly the retained lines."""
        self._check_shape(band)
        # First pass: find the first non-blank row (bottom-anchored content).
        first_content = self.rows
        for r in range(self.rows):
            row_has_content = False
            for c in range(self.cols):
                bits = _cell_bits(band, r, c, self.on, self.off)
                if bits != _ZERO_BITS:
                    row_has_content = True
                    break
            if row_has_content:
                first_content = r
                break
        out = []
        for r in range(first_content, self.rows):
            chars = []
            for c in range(self.cols):
                bits = _cell_bits(band, r, c, self.on, self.off)
                ch = _BITS_TO_CHAR.get(bits)
                if ch is None:
                    raise ValueError(
                        f"cell ({r},{c}) matches no VGA glyph — decode refused"
                    )
                chars.append(ch)
            out.append("".join(chars).rstrip())
        while out and out[-1] == "":
            out.pop()
        return "\n".join(out)

    def _check_shape(self, band: np.ndarray) -> None:
        want = (self.rows * CELL_H, self.cols * CELL_W, 3)
        if band.shape != want:
            raise ValueError(f"band shape {band.shape} != expected {want}")


def render_transcript(lines, rows: int = DEFAULT_ROWS,
                      cols: int = DEFAULT_COLS) -> np.ndarray:
    """Convenience: transcript -> band (bottom-anchored ring)."""
    con = TextConsole(rows=rows, cols=cols)
    for line in lines:
        con.feed(line)
    return con.render_band()


def decode_transcript_band(band: np.ndarray, cols: int = DEFAULT_COLS,
                           on=DEFAULT_ON, off=DEFAULT_OFF) -> str:
    """Decode a band rendered by render_transcript (strict, glyph-side)."""
    rows = band.shape[0] // CELL_H
    con = TextConsole(rows=rows, cols=cols, on=on, off=off)
    return con.decode_band(band)


def compose_observation(app_image: np.ndarray, band: np.ndarray) -> np.ndarray:
    """Place the console band BELOW the program region: the reserved band
    of the observation image. Widths are reconciled by right-padding the
    narrower part with `off` black — program pixels stay left-aligned and
    untouched (assembled images are black outside encoded pixels anyway)."""
    if app_image.ndim != 3 or app_image.shape[2] != 3:
        raise ValueError(f"app_image shape {app_image.shape} is not HxWx3")
    if app_image.dtype != np.uint8 or band.dtype != np.uint8:
        raise ValueError("compose_observation expects uint8 arrays")
    width = max(app_image.shape[1], band.shape[1])

    def _pad(img: np.ndarray) -> np.ndarray:
        if img.shape[1] == width:
            return img
        pad = np.zeros((img.shape[0], width - img.shape[1], 3), dtype=np.uint8)
        return np.hstack([img, pad])

    return np.vstack([_pad(app_image), _pad(band)])


def save_png(image: np.ndarray, path) -> None:
    """Persist a band / composed observation as PNG (existing container path)."""
    from PIL import Image
    Image.fromarray(image).save(str(path))


def load_png(path) -> np.ndarray:
    from PIL import Image
    return np.array(Image.open(str(path)).convert("RGB"), dtype=np.uint8)
