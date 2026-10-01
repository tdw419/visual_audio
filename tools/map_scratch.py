#!/usr/bin/env python3
"""
tools/map_scratch.py — reserved scratch window on the spatial build map.

RULING (GH-28 persistence posture, ruled 2026-09-28 by Hermes on Jericho's
"you lead" delegation, following the 9714a363 vaddr-vs-paddr decision shape):

  POSTURE = RESERVED SCRATCH WINDOW (partition), not sidecar registry.

  Rationale (same auditable-invariant argument that won the paddr ruling):
  - A sidecar registry adds a second on-disk artifact whose sync discipline
    (who re-stamps, when, failure handling) is a new protocol to audit.
  - A reserved interval keeps the map self-contained: exactly one invariant —
    render() must never paint cells in SCRATCH_IDXS — and the invariant is a
    single integer range check, trivially auditable, mirroring the fence's
    pmin <= p < pmax shape. scratch_is_cell() is the fence consult of the map.

  OWNERSHIP: any lane may WRITE scratch cells via stamp_scratch(); the map lane
  (render) must PRESERVE them. History territory (idx < SCRATCH_START) remains
  map-lane-owned, read-only for payloads.

  GEOMETRY (measured, k=1024 tail of the Hilbert curve is exactly the rect
  x[96,128) x y[0,32)): the window sits TOP-RIGHT of the map. Using the curve's
  own final indices (not a detached row-major rect) makes the consult EXACT:
  idx >= SCRATCH_START <=> the cell is inside the window, so render()'s guard
  (skip painting when scratch_is_cell(idx)) can never clip history territory,
  and history can never be painted into the window.
"""
from PIL import Image, ImageDraw

from tools.geos_hilbert import hilbert_d2xy_true  # noqa: E402

SCRATCH_SIDE = 32          # 32x32 cells = 1024 scratch cells (~6.25% of map)
SIDE = 128                 # full map side (cells)
SCRATCH_START = SIDE * SIDE - SCRATCH_SIDE * SCRATCH_SIDE   # 15360
SCRATCH_END = SIDE * SIDE - 1               # 16383 (inclusive)

SCRATCH_BORDER = (60, 60, 70)   # dim outline so the window is visible


def scratch_is_cell(idx: int) -> bool:
    """The one-invariant consult: is this cell index inside the reserved window?"""
    return SCRATCH_START <= idx <= SCRATCH_END


def scratch_idx_to_xy(idx: int, side: int = SIDE) -> tuple:
    """Hilbert-index based: scratch cell idx -> (x, y). The window is the FINAL
    SCRATCH_SIDE*SCRATCH_SIDE Hilbert indices, which land exactly on the TOP-RIGHT
    rect x in [SIDE-32, SIDE), y in [0, 32) (measured: k=1024 tail of the curve is
    a contiguous rect). Using Hilbert indices keeps one coordinate system for the
    whole map and makes render()'s guard exact: idx >= SCRATCH_START <=> inside
    the rect, no low-idx history cells ever fall inside the window."""
    assert scratch_is_cell(idx), f"idx {idx} outside scratch window"
    return hilbert_d2xy_true(side, idx)


def stamp_scratch(img: Image.Image, idx: int, color, scale: int = 8,
                  side: int = SIDE) -> None:
    """Write one scratch cell. Any lane may call this; render() will preserve it."""
    x, y = scratch_idx_to_xy(idx, side)
    d = ImageDraw.Draw(img)
    d.rectangle([x * scale, y * scale, x * scale + scale - 1, y * scale + scale - 1],
                fill=color)


def paint_scratch_border(img: Image.Image, scale: int = 8, side: int = SIDE) -> None:
    """Dim outline marking the window's corner so it's visible on the map."""
    x0, y0 = scratch_idx_to_xy(SCRATCH_START, side)
    d = ImageDraw.Draw(img)
    d.rectangle([x0 * scale, y0 * scale, x0 * scale + 3, y0 * scale + 3],
                fill=SCRATCH_BORDER)


def read_scratch(img_array, idx: int, scale: int = 8, side: int = SIDE) -> tuple:
    """Read back one scratch cell's top-left pixel as an RGB tuple."""
    x, y = scratch_idx_to_xy(idx, side)
    px = img_array[y * scale, x * scale]
    return tuple(int(v) for v in px[:3])
