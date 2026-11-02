"""h3 ground-truth poster encoder (fixture generator, NOT the decoder).

Encodes a payload into a poster image using Hilbert-mapped glyph cells in ONE
canonical spatial frame, and emits the matching SAM-3.1-shaped segmentation
response (same wire shape as the 2026-10-26 live probe recorded in
sam_response_red_rect.json) so the offline decoder has a recorded fixture.

Canonical spatial frame (v1 contract, shared with glyph_decoder.py):
  - origin top-left, width=height=512 px
  - glyph cell grid: 64x64 cells, each cell 8x8 px (Hilbert order 6)
  - bit mapping: cell filled (ink) = 1, empty (background) = 0
  - bit order: framed bytes, MSB first, cells visited in Hilbert-curve order
    d = 0 .. 4095 (d2xy)
  - framing: b"GLY1" + 2-byte big-endian payload length + payload + zero pad

The mask wire format in the recorded response is RLE pairs "run,bit" (comma
separated), row-major over the 64x64 cell grid. Live SAM masks are pixel-space;
pixel-space handling is an h4 concern — v1 pins the recorded-shape contract.

Deterministic: pure stdlib, fixed zlib level, no randomness.
"""
import hashlib
import json
import struct
import zlib

MAGIC = b"GLY1"
HILBERT_ORDER = 6
GRID = 1 << HILBERT_ORDER            # 64 cells per axis
CELL_PX = 8
FRAME_W = FRAME_H = GRID * CELL_PX   # 512x512 canonical frame
TOTAL_CELLS = GRID * GRID            # 4096 bits = 512 bytes capacity
PAYLOAD_MAX = TOTAL_CELLS // 8 - len(MAGIC) - 2

INK = 0x00
BACKGROUND = 0xFF


def hilbert_d2xy(order, d):
    """Hilbert curve index d -> (x, y) on the order-th (n=2**order) grid."""
    n = 1 << order
    x = y = 0
    t = d
    s = 1
    while s < n:
        rx = 1 & (t // 2)
        ry = 1 & (t ^ rx)
        if ry == 0:
            if rx == 1:
                x = s - 1 - x
                y = s - 1 - y
            x, y = y, x
        x += s * rx
        y += s * ry
        t //= 4
        s *= 2
    return x, y


def frame_payload(payload):
    if len(payload) > PAYLOAD_MAX:
        raise ValueError(f"payload {len(payload)}B exceeds v1 capacity {PAYLOAD_MAX}B")
    return MAGIC + struct.pack(">H", len(payload)) + payload


def payload_to_cells(payload):
    """Framed payload bytes -> 64x64 cell grid (list of rows, 1=filled).

    Bit i (MSB-first over framed bytes) lands on the cell at
    hilbert_d2xy(HILBERT_ORDER, i).
    """
    framed = frame_payload(payload)
    bits = [(b >> (7 - j)) & 1 for b in framed for j in range(8)]
    if len(bits) > TOTAL_CELLS:
        raise ValueError("framed payload overflows the cell grid")
    grid = [[0] * GRID for _ in range(GRID)]
    for d, bit in enumerate(bits):
        x, y = hilbert_d2xy(HILBERT_ORDER, d)
        grid[y][x] = bit
    return grid


def grid_to_pixels(grid):
    """Cell grid -> FRAME_H rows of FRAME_W grayscale bytes."""
    rows = []
    for crow in grid:
        band = bytes(INK if cell else BACKGROUND for cell in crow for _ in range(CELL_PX))
        for _ in range(CELL_PX):
            rows.append(band)
    return rows


def png_bytes_rows(rows):
    """Arbitrary grayscale-8 rows -> minimal deterministic PNG (stdlib only)."""
    h = len(rows)
    w = len(rows[0]) if h else 0
    raw = b"".join(b"\x00" + bytes(r) for r in rows)
    idat = zlib.compress(raw, 9)

    def chunk(tag, data):
        return (
            struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", idat) + chunk(b"IEND", b""))


def png_bytes(grid):
    """Cell grid -> FRAME_H rows of FRAME_W grayscale bytes -> PNG."""
    return png_bytes_rows(grid_to_pixels(grid))


def stylized_rows(grid, border=48, bg=0xF4, ink=0x08):
    """Cell grid -> rows of a LARGER stylized canvas (h4 unseen-input shape).

    The canonical 512x512 frame sits inset by `border` px inside a decorative
    stripe field; ink/background are non-pure grays so neither a naive 0/255
    assumption nor a naive full-image crop decodes it.
    """
    w = FRAME_W + 2 * border
    h = FRAME_H + 2 * border
    rows = []
    for y in range(h):
        row = bytearray(w)
        inner_y = border <= y < h - border
        gy = (y - border) // CELL_PX if inner_y else -1
        for x in range(w):
            if inner_y and border <= x < w - border:
                gx = (x - border) // CELL_PX
                row[x] = ink if grid[gy][gx] else bg
            else:
                row[x] = 0x33 if ((x ^ y) >> 3) & 1 else 0xEE
        rows.append(bytes(row))
    return rows


def prng_bytes(seed, n):
    """Deterministic stdlib-only byte stream (SHA-256 counter mode)."""
    out = bytearray()
    counter = 0
    while len(out) < n:
        out += hashlib.sha256(f"{seed}:{counter}".encode()).digest()
        counter += 1
    return bytes(out[:n])


def degrade_rows(rows, seed, level):
    """Deterministic uniform-noise degradation (h4 low-confidence shape).

    Each pixel consumes two PRNG bytes: when the first < `level` (prob
    level/256) the pixel is replaced by the second byte (uniform 0-255).
    Uniform noise fills the histogram valley between ink and background, so
    the measured Otsu separability (eta — the quantity the confidence gate
    reads) drops quickly, while the per-cell mean vote survives far past the
    gate — exactly the regime where the fallback must still decode
    byte-identically.
    """
    rnd = prng_bytes(seed, 2 * sum(len(r) for r in rows))
    k = 0
    out = []
    for r in rows:
        nr = bytearray(len(r))
        for i, v in enumerate(r):
            if rnd[k] < level:
                nr[i] = rnd[k + 1]
            else:
                nr[i] = v
            k += 2
        out.append(bytes(nr))
    return out


def cells_to_rle(grid):
    """Cell grid -> mask wire data: comma-separated 'run,bit' pairs, row-major."""
    flat = [cell for row in grid for cell in row]
    pairs = []
    i = 0
    while i < len(flat):
        bit = flat[i]
        run = 1
        while i + run < len(flat) and flat[i + run] == bit:
            run += 1
        pairs.append(f"{run},{bit}")
        i += run
    return ",".join(pairs)


def sam_response(payload):
    """SAM-3.1-shaped recorded response for the poster (live wire shape).

    Shape mirrors sam_response_red_rect.json: output[0].content[0].text is the
    special-token stream "<0f>0" + one <|box;...|> + one <|mask;...|> per match.
    Box carries the matched region (the full poster here) plus frame w/h.
    """
    text = (
        "<0f>0"
        f"<|box;x1=0;y1=0;x2={FRAME_W};y2={FRAME_H};w={FRAME_W};h={FRAME_H}|>"
        f"<|mask;x=0;y=0;data={cells_to_rle(payload_to_cells(payload))}|>"
    )
    return {
        "model": "sam-3.1",
        "status": "completed",
        "object": "response",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            }
        ],
    }


def build_fixtures(payload):
    """Return the full ground-truth fixture dict (JSON-serializable)."""
    grid = payload_to_cells(payload)
    framed = frame_payload(payload)
    return {
        "canonical_frame": {
            "origin": "top-left",
            "width_px": FRAME_W,
            "height_px": FRAME_H,
            "cell_px": CELL_PX,
            "grid": GRID,
            "hilbert_order": HILBERT_ORDER,
        },
        "payload_hex": payload.hex(),
        "payload_md5": hashlib.md5(payload).hexdigest(),
        "framed_hex": framed.hex(),
        "framed_md5": hashlib.md5(framed).hexdigest(),
        "poster_png_md5": hashlib.md5(png_bytes(grid)).hexdigest(),
        "bit_encoding": (
            "framed bytes MSB-first; bit d -> cell hilbert_d2xy(order=6, d); "
            "cell filled=1 (ink 0x00), empty=0 (background 0xFF)"
        ),
        "framing": 'b"GLY1" + >H payload length + payload + zero pad to 4096 bits',
        "mask_wire": "RLE pairs 'run,bit' comma-separated, row-major over the 64x64 cell grid",
    }


if __name__ == "__main__":
    import pathlib
    import sys

    out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "hackathon/tests/fixtures")
    payload = b"hello from the glyph poster: SAM 3.1 decoded this payload\n"
    gt = build_fixtures(payload)
    (out / "glyph_poster_gt.png").write_bytes(png_bytes(payload_to_cells(payload)))
    (out / "glyph_response_gt.json").write_text(json.dumps(sam_response(payload), indent=1) + "\n")
    (out / "glyph_poster_gt.json").write_text(json.dumps(gt, indent=1) + "\n")
    print(json.dumps({k: v for k, v in gt.items() if k.endswith("md5")}, indent=1))
