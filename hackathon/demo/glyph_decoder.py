"""h3 — SAM 3.1 glyph decoder v1 (pure, offline, deterministic).

Consumes a SAM-3.1-shaped response (the recorded wire shape of the 2026-10-26
live probe in sam_response_red_rect.json) and recovers the payload encoded in
Hilbert-mapped glyph cells of ONE canonical spatial frame:

  - special-token stream "<0f>0" + <|box;x1;y1;x2;y2;w;h|> + <|mask;x;y;data|>
  - canonical frame (shared contract with glyph_poster.py): top-left origin,
    512x512 px, 64x64 glyph cells of 8x8 px, Hilbert order 6
  - mask data: RLE pairs "run,bit" row-major over the cell grid
  - bit d of the framed byte stream lives at cell hilbert_d2xy(6, d)
  - framing: b"GLY1" + 2-byte big-endian payload length + payload

v2 (h4) adds: promptable-point tokens (<|point;x=;y=;label=|>) and a
confidence score token (<|score;v=|>); multi-box streams where a point
selects WHICH box decodes; and a CLASSICAL (non-SAM) fallback that decodes
the poster PNG pixels directly (pure-stdlib gray-8 PNG reader + Otsu
threshold + per-cell mean vote) whenever the wire score is below
CONF_THRESHOLD. v1 decode paths are byte-identical (h3 fixtures unchanged).
"""
import re
import struct
import zlib

MAGIC = b"GLY1"
HILBERT_ORDER = 6
GRID = 1 << HILBERT_ORDER            # 64 cells per axis
CELL_PX = 8
FRAME_W = FRAME_H = GRID * CELL_PX   # 512x512 canonical frame
TOTAL_CELLS = GRID * GRID

_BOX_RE = re.compile(
    r"<\|box;x1=(\d+);y1=(\d+);x2=(\d+);y2=(\d+);w=(\d+);h=(\d+)\|>"
)
_MASK_RE = re.compile(r"<\|mask;x=(\d+);y=(\d+);data=([^|>]+)\|>")
_POINT_RE = re.compile(r"<\|point;x=(\d+);y=(\d+);label=(\d+)\|>")
_SCORE_RE = re.compile(r"<\|score;v=([0-9.]+)\|>")
_PREFIX_RE = re.compile(r"^(<0f>\d+)")

# Classical-fallback gate: a wire score below this trips the pixel decode.
# Calibrated (measured, not vibes) in hackathon/tests/fixtures/h4_calibration.md:
# clean stylized poster measures eta=1.000000 (above the gate), the degraded
# low-conf fixture measures eta=0.897667 (below); the classical fallback
# stays byte-exact down to eta=0.844785, so 0.90 trips with margin on both
# sides. Regenerated deterministically by hackathon/demo/glyph_fixtures_h4.py.
CONF_THRESHOLD = 0.90


class DecodeError(RuntimeError):
    """Any structural or framing violation of the v1 decode contract."""


def parse_sam_stream(text):
    """Special-token stream -> {prefix, boxes, masks, points, score}."""
    boxes = [
        {
            "x1": int(m[0]), "y1": int(m[1]),
            "x2": int(m[2]), "y2": int(m[3]),
            "w": int(m[4]), "h": int(m[5]),
        }
        for m in _BOX_RE.findall(text)
    ]
    masks = [
        {"x": int(m[0]), "y": int(m[1]), "data": m[2]}
        for m in _MASK_RE.findall(text)
    ]
    points = [
        {"x": int(m[0]), "y": int(m[1]), "label": int(m[2])}
        for m in _POINT_RE.findall(text)
    ]
    scores = [float(m) for m in _SCORE_RE.findall(text)]
    prefix_m = _PREFIX_RE.match(text)
    return {
        "prefix": prefix_m.group(1) if prefix_m else None,
        "boxes": boxes,
        "masks": masks,
        "points": points,
        "score": scores[-1] if scores else None,
    }


def select_box(parsed, point):
    """Index of the box a promptable point selects; 0 for a single box."""
    boxes = parsed["boxes"]
    if len(boxes) == 1:
        return 0
    if point is None:
        raise DecodeError(f"{len(boxes)} boxes in stream and no promptable point")
    hits = [
        i for i, b in enumerate(boxes)
        if b["x1"] <= point["x"] < b["x2"] and b["y1"] <= point["y"] < b["y2"]
    ]
    if len(hits) != 1:
        raise DecodeError(f"point ({point['x']},{point['y']}) selects {len(hits)} boxes")
    return hits[0]


def _decode_sam(parsed):
    """SAM mask path: grid-space RLE mask -> Hilbert walk -> framed payload."""
    if len(parsed["boxes"]) < 1:
        raise DecodeError("no box in stream")
    if len(parsed["masks"]) < 1:
        raise DecodeError("expects at least 1 mask")
    idx = select_box(parsed, parsed["points"][0] if parsed["points"] else None)
    if len(parsed["boxes"]) > 1 and len(parsed["masks"]) != len(parsed["boxes"]):
        raise DecodeError(
            f"{len(parsed['boxes'])} boxes but {len(parsed['masks'])} masks"
        )
    box = parsed["boxes"][idx]
    mask = parsed["masks"][idx] if len(parsed["boxes"]) > 1 else parsed["masks"][0]
    # One canonical spatial frame: the box frame dims must equal the canonical
    # frame; every cell coordinate below is resolved in that same frame.
    if (box["w"], box["h"]) != (FRAME_W, FRAME_H):
        raise DecodeError(
            f"box frame {box['w']}x{box['h']} != canonical frame "
            f"{FRAME_W}x{FRAME_H}"
        )
    if (mask["x"], mask["y"]) != (0, 0):
        raise DecodeError(
            f"v1 pins mask origin at canonical (0,0), got ({mask['x']},{mask['y']})"
        )

    bits = decode_rle(mask["data"], expected_len=TOTAL_CELLS)

    # Row-major grid -> Hilbert-order bit stream: bit d lives at cell (x, y).
    grid = [bits[y * GRID + x] for y in range(GRID) for x in range(GRID)]
    hilbert_bits = [grid[y * GRID + x] for x, y in
                    (hilbert_d2xy(HILBERT_ORDER, d) for d in range(TOTAL_CELLS))]

    return extract_framed(bits_to_framed_bytes(hilbert_bits))


def decode_poster_response(response):
    """SAM response dict -> decoded payload bytes (md5-able ground truth).

    v1 entry point, preserved byte-identically: always takes the SAM mask
    path. New code should prefer decode_poster_auto (h4 confidence gate).
    """
    try:
        text = response["output"][0]["content"][0]["text"]
    except (KeyError, IndexError, TypeError) as e:
        raise DecodeError(f"unrecognized response shape: {e}") from e
    return _decode_sam(parse_sam_stream(text))


def decode_rle(data, expected_len=TOTAL_CELLS):
    """RLE pairs 'run,bit' (comma separated) -> list of bits."""
    tokens = data.split(",")
    if len(tokens) % 2 != 0:
        raise DecodeError(f"RLE data has {len(tokens)} tokens; expected run,bit pairs")
    bits = []
    for i in range(0, len(tokens), 2):
        run = int(tokens[i])
        bit = int(tokens[i + 1])
        if bit not in (0, 1) or run <= 0:
            raise DecodeError(f"invalid RLE pair run={run} bit={bit}")
        bits.extend([bit] * run)
    if len(bits) != expected_len:
        raise DecodeError(f"RLE expands to {len(bits)} bits; expected {expected_len}")
    return bits


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


def bits_to_framed_bytes(bits):
    """Hilbert-order bits -> framed byte string (MSB-first)."""
    out = bytearray()
    for i in range(0, len(bits) - len(bits) % 8, 8):
        byte = 0
        for j in range(8):
            byte = (byte << 1) | bits[i + j]
        out.append(byte)
    return bytes(out)


def extract_framed(framed):
    """Validate GLY1 framing; return the payload bytes."""
    header = len(MAGIC) + 2
    if len(framed) < header or framed[:4] != MAGIC:
        raise DecodeError(f"bad magic: {framed[:4]!r}")
    (length,) = struct.unpack(">H", framed[4:6])
    payload = framed[header:header + length]
    if len(payload) != length:
        raise DecodeError(f"length {length} exceeds available {len(payload)} bytes")
    if any(framed[header + length:]):
        raise DecodeError("non-zero padding after payload")
    return payload


def read_gray_png(data):
    """Minimal pure-stdlib grayscale-8 PNG reader (decoder-side twin of the
    poster writer). Supports color type 0, bit depth 8, non-interlaced, all
    five filter types. Returns a list of rows (bytes of w pixels)."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise DecodeError("not a PNG")
    pos = 8
    ihdr = None
    idat = bytearray()
    while pos + 8 <= len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        tag = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        if tag == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", chunk)
        elif tag == b"IDAT":
            idat += chunk
        elif tag == b"IEND":
            break
        pos += 12 + length
    if ihdr is None:
        raise DecodeError("PNG missing IHDR")
    w, h, depth, ctype, _comp, _filt, interlace = ihdr
    if depth != 8 or ctype != 0:
        raise DecodeError(f"unsupported PNG: depth={depth} color_type={ctype} (want 8-bit gray)")
    if interlace != 0:
        raise DecodeError("interlaced PNG unsupported")
    raw = zlib.decompress(bytes(idat))
    stride = w
    rows = []
    prev = bytes(stride)
    p = 0
    for _ in range(h):
        if p + 1 + stride > len(raw):
            raise DecodeError("PNG pixel data truncated")
        ftype = raw[p]
        line = bytearray(raw[p + 1:p + 1 + stride])
        p += 1 + stride
        bpp = 1
        if ftype == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif ftype == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ftype == 3:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                c = prev[i - bpp] if i >= bpp else 0
                b = prev[i]
                pp = a + b - c
                pa, pb, pc = abs(pp - a), abs(pp - b), abs(pp - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        elif ftype != 0:
            raise DecodeError(f"unsupported PNG filter {ftype}")
        rows.append(bytes(line))
        prev = line
    return rows


def otsu(rows):
    """Otsu threshold over grayscale rows -> (threshold, eta).

    eta = max between-class variance / total variance in [0, 1]: the measured
    bimodal separability of the pixels. This is the calibration quantity
    behind CONF_THRESHOLD (see h4_calibration.md).
    """
    hist = [0] * 256
    total = 0
    for r in rows:
        for v in r:
            hist[v] += 1
        total += len(r)
    if total == 0:
        raise DecodeError("empty crop")
    sum_all = sum(i * hist[i] for i in range(256))
    mean_all = sum_all / total
    var_total = sum(hist[i] * (i - mean_all) ** 2 for i in range(256)) / total
    if var_total == 0:
        return 0, 0.0  # flat image: no segmentation signal at all
    sum_b = 0
    w_b = 0
    best_t = 0
    max_sigma_b = 0.0
    for t in range(256):
        w_b += hist[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * hist[t]
        m_b = sum_b / w_b
        m_f = (sum_all - sum_b) / w_f
        sigma_b = (w_b / total) * (w_f / total) * (m_b - m_f) ** 2
        if sigma_b > max_sigma_b:
            max_sigma_b = sigma_b
            best_t = t
    return best_t, max_sigma_b / var_total


def decode_poster_pixels(png, box=None):
    """Classical (non-SAM) fallback: poster PNG pixels -> (payload, eta).

    Crops to the box region when given (the response box locates the frame in
    a larger stylized canvas), Otsu-thresholds the crop, classifies each
    glyph cell filled iff its mean luminance <= the Otsu threshold (ink is
    dark), then Hilbert-walks to the framed payload.
    Raises DecodeError on any framing violation — the fallback is held to the
    same byte-exact contract as the SAM path.
    """
    rows = read_gray_png(png)
    if box is not None:
        x1, y1, x2, y2 = box["x1"], box["y1"], box["x2"], box["y2"]
        if not (rows and 0 <= x1 < x2 <= len(rows[0]) and 0 <= y1 < y2 <= len(rows)):
            raise DecodeError(f"box {box} does not fit the poster")
        crop = [r[x1:x2] for r in rows[y1:y2]]
    else:
        crop = rows
    ch = len(crop)
    cw = len(crop[0]) if ch else 0
    if ch != cw or ch == 0 or ch % GRID != 0:
        raise DecodeError(f"crop {cw}x{ch} is not a {GRID}-divisible square frame")
    cell_px = ch // GRID
    if cw % GRID != 0 or cw // GRID != cell_px:
        raise DecodeError(f"crop {cw}x{ch} is not square-celled")
    thr, eta = otsu(crop)
    grid = [[0] * GRID for _ in range(GRID)]
    n = cell_px * cell_px
    for cy in range(GRID):
        for cx in range(GRID):
            s = 0
            for yy in range(cy * cell_px, (cy + 1) * cell_px):
                row = crop[yy]
                for xx in range(cx * cell_px, (cx + 1) * cell_px):
                    s += row[xx]
            grid[cy][cx] = 1 if (s / n) <= thr else 0
    hilbert_bits = [grid[y][x] for x, y in
                    (hilbert_d2xy(HILBERT_ORDER, d) for d in range(TOTAL_CELLS))]
    return extract_framed(bits_to_framed_bytes(hilbert_bits)), eta


def decode_poster_auto(response, poster_png=None):
    """Confidence-gated decode: SAM mask path when the wire score is at or
    above CONF_THRESHOLD, classical pixel fallback below it.

    Returns {"payload": bytes, "path": "sam"|"pixels", "confidence": float}
    (plus "otsu_eta" on the fallback path).
    """
    try:
        text = response["output"][0]["content"][0]["text"]
    except (KeyError, IndexError, TypeError) as e:
        raise DecodeError(f"unrecognized response shape: {e}") from e
    parsed = parse_sam_stream(text)
    score = parsed["score"] if parsed["score"] is not None else 1.0
    if score >= CONF_THRESHOLD:
        return {"payload": _decode_sam(parsed), "path": "sam", "confidence": score}
    if poster_png is None:
        raise DecodeError(
            f"low-confidence segmentation (score {score:.3f} < {CONF_THRESHOLD:.2f}) "
            "and no poster PNG available for the classical fallback"
        )
    point = parsed["points"][0] if parsed["points"] else None
    idx = select_box(parsed, point)
    payload, eta = decode_poster_pixels(poster_png, parsed["boxes"][idx])
    out = {"payload": payload, "path": "pixels", "confidence": score}
    out["otsu_eta"] = eta
    return out
