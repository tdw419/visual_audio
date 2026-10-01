"""Single source of truth for Hilbert curve math used across tools/ and systems/.

Two incompatible variants exist in the codebase's history and are preserved
here under distinct names rather than unified, because unifying them would
silently corrupt already-encoded containers:

- hilbert_d2xy_true / hilbert_xy2d_true: the correct Hacker's Delight Hilbert
  curve (unit-step, used by vcc_engine_v2.py, spadsl.py, spadsl_semantic.py).
- hilbert_d2xy_legacy_qemu: a buggy variant that does NOT trace a valid
  Hilbert curve (it takes Chebyshev steps), but is baked into existing
  QEMU-captured MKV containers (qemu_capture_simple.py, qemu_to_mkv.py,
  vac3_demo.py). Do not "fix" this without a migration plan for existing data.
"""

from typing import Optional, Tuple


def hilbert_d2xy_true(n: int, d: int) -> Tuple[int, int]:
    x, y = 0, 0
    s = 1
    t = d
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


def hilbert_xy2d_true(n: int, x: int, y: int) -> int:
    d = 0
    s = n // 2
    while s > 0:
        rx = 1 & (x // s)
        ry = 1 & (y // s)
        d += s * s * ((3 * rx) ^ ry)
        if ry == 0:
            if rx == 1:
                x = s - 1 - x
                y = s - 1 - y
            x, y = y, x
        x %= s
        y %= s
        s //= 2
    return d


def hilbert_d2xy_legacy_qemu(n: int, d: int) -> Tuple[int, int]:
    x, y = 0, 0
    s = 1
    while s < n:
        rx = (d >> 1) & 1
        ry = d & 1
        if ry == 0:
            if rx == 1:
                x = s - 1 - x
                y = s - 1 - y
            x, y = y, x
        x += s * rx
        y += s * ry
        d >>= 2
        s <<= 1
    return x, y


# ── Reference-pixel sentinels ────────────────────────────────────────────
# A Hilbert-mapped canvas has no free orientation signal the way a raster
# does (index 0 = top-left, N-1 = end): the four corner WORDS are not
# contiguous (see the values below), so a flipped, rotated, or wrong-variant
# read of the same pixel buffer still "decodes" -- just to the wrong words,
# silently. stamp_reference_pixels()/verify_reference_pixels() give a
# single-read fault-localization check: measure the machine's own geometry
# instead of trusting a doc comment or a textbook curve convention (session
# 2026-09-11, docs/research/501_how_to_run_live_teleop_experiment.md
# verified this exact geometry live: corners 0/16383/5461/10922, center
# 8192 for n=128 -- reproduced independently against hilbert_xy2d_true
# above before this helper was written).
_REFERENCE_SENTINEL_VALUES = {
    "origin": 0xA5A500,   # word 0            = hilbert_xy2d_true(n, 0, 0)
    "x_max": 0x00FFA5,    #                    = hilbert_xy2d_true(n, n-1, 0)
    "y_max": 0xFFA500,    #                    = hilbert_xy2d_true(n, 0, n-1)
    "far": 0x00A5FF,      #                    = hilbert_xy2d_true(n, n-1, n-1)
    "center": 0xFF00A5,   # curve midpoint     = hilbert_xy2d_true(n, n/2, n/2)
}


def reference_pixel_coords(side: int) -> dict:
    """The four corner + curve-center (x, y) pixel coordinates for an
    n=side Hilbert-mapped canvas, keyed by the same names used by
    stamp/verify_reference_pixels()."""
    return {
        "origin": (0, 0),
        "x_max": (side - 1, 0),
        "y_max": (0, side - 1),
        "far": (side - 1, side - 1),
        "center": (side // 2, side // 2),
    }


def stamp_reference_pixels(image, n: Optional[int] = None,
                            values: Optional[dict] = None) -> dict:
    """Write a distinct 24-bit sentinel value at the four Hilbert-curve
    corner pixels and the curve-center pixel of `image` (an (H, W, 3)
    uint8-ish array), for later orientation/scale verification via
    verify_reference_pixels(). `n` defaults to the image's own width
    (square canvases only -- pass it explicitly for a padded/rectangular
    bake). Returns {name: {"x", "y", "hilbert_word", "value"}} for the
    caller to persist alongside the image if it wants an explicit
    expected-value record instead of relying on the module default.

    The stamp/verify MECHANIC (write/read raw pixels at these (x, y)
    positions, detect flip/rotate/rescale) is addressing-scheme-agnostic
    -- it works on any (H, W, 3) buffer, Hilbert-mapped or not.
    `hilbert_word`, however, is NOT: it is always computed via
    hilbert_xy2d_true and is only a real memory-word index on a
    genuinely Hilbert-addressed image (e.g. the geo-obs observation
    channel, or a GH-25 PTE_HILB paged frame). On a scanline-addressed
    image (GlyphCPUv2's default `_addr_to_xy`, e.g. agent_resident.py's
    non-paged bakes) it is an opaque curve index with no relationship to
    that engine's actual word address at (x, y) -- do not read it as one
    (session 2026-09-11 caught exactly this mistake: an agent computed
    "scanline" word->pixel pairs by importing the Hilbert channel's
    N=128 into a scanline calculation; the fix was to rebuild the image
    and measure its real width instead of assuming one).

    Silently skips a marker whose (x, y) falls outside `image`'s actual
    shape (e.g. a bake padded narrower than the logical Hilbert side) --
    it stamps what it can rather than raising, since a partial-canvas bake
    is a legitimate caller shape, not a caller error.
    """
    h, w = image.shape[:2]
    side = n or w
    coords = reference_pixel_coords(side)
    vals = values or dict(_REFERENCE_SENTINEL_VALUES)
    out = {}
    for name, (x, y) in coords.items():
        if x >= w or y >= h:
            continue
        v = vals[name] & 0xFFFFFF
        image[y, x] = ((v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF)
        out[name] = {"x": x, "y": y, "hilbert_word": hilbert_xy2d_true(side, x, y), "value": v}
    return out


def verify_reference_pixels(image, n: Optional[int] = None,
                             expected: Optional[dict] = None) -> dict:
    """Read back the sentinels stamp_reference_pixels() wrote and report a
    fault-localization diagnosis, not just pass/fail:

      - a CORNER sentinel mismatches  -> orientation / axis-flip error
      - only the CENTER mismatches    -> curve variant / scale distortion
        (corners can coincidentally still land right under some wrong
        variants; the center is the position where a variant/scale error
        is maximally visible from a single value)
      - all match                     -> the mapping is sound

    This checks pixel-buffer geometry (raw RGB at fixed (x, y) positions)
    -- it is valid on ANY image, scanline- or Hilbert-addressed, and says
    nothing about whether the image's *engine* addresses words via
    Hilbert math (see stamp_reference_pixels()'s docstring for the
    corresponding caveat on that function's "hilbert_word" field, which
    this function does not return at all -- verify only reports pixel
    values, never word indices, precisely to avoid that ambiguity).

    Returns {"ok": bool, "markers": {name: {"expected", "actual", "ok"}},
    "diagnosis": str}. A marker outside the image's actual shape reports
    ok=False with actual=None rather than raising (mirrors
    stamp_reference_pixels()'s skip-don't-raise choice).
    """
    h, w = image.shape[:2]
    side = n or w
    coords = reference_pixel_coords(side)
    vals = expected or dict(_REFERENCE_SENTINEL_VALUES)
    markers = {}
    for name, (x, y) in coords.items():
        want = vals[name] & 0xFFFFFF
        if x >= w or y >= h:
            markers[name] = {"expected": want, "actual": None, "ok": False}
            continue
        r, g, b = image[y, x]
        actual = (int(r) << 16) | (int(g) << 8) | int(b)
        markers[name] = {"expected": want, "actual": actual, "ok": actual == want}
    corner_names = ("origin", "x_max", "y_max", "far")
    corners_ok = all(markers[c]["ok"] for c in corner_names if c in markers)
    center_ok = markers.get("center", {}).get("ok", False)
    ok = corners_ok and center_ok
    if ok:
        diagnosis = "mapping sound: all reference pixels match"
    elif not corners_ok:
        diagnosis = "orientation / axis-flip error (a corner sentinel mismatched)"
    else:
        diagnosis = "curve variant / scale distortion (corners OK, center mismatched)"
    return {"ok": ok, "markers": markers, "diagnosis": diagnosis}
