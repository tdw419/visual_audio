#!/usr/bin/env python3
"""
tools/spatial_devkit.py — Spatial DevKit Core Façade (GH-32).

Consolidates proven spatial-computing primitives into a single thin façade:
  (1) compile(src, width_instrs) -> np.ndarray
  (2) run(image, max_steps, cpu) -> GlyphCPUv2 (enforces fresh cpu.pc=(0,0))
  (3) save(slot_name, words, map_target) -> tuple[int, int]
  (4) load(slot_name, map_target) -> list[int]
  (5) verify_parity(band, expected_str, rows, cols) -> bool

HARD LINE: No execution surface beyond GlyphCPUv2's existing spawn posture.
Does not open, front-run, or bypass the BK-59 desktop gate.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Sequence

import numpy as np
from PIL import Image

from tools.glyph_isa_v2 import (
    GlyphAssemblerV2,
    GlyphCPUv2,
    OpcodeMapV2,
)
from tools.glyph_text_console import TextConsole
from tools.map_scratch import (
    SCRATCH_START,
    scratch_idx_to_xy,
)

REPO = Path(__file__).resolve().parent.parent
DEFAULT_MAP_PATH = REPO / "build_map.png"
SCALE = 8
MAGIC_SCRATCH = 0x53  # 'S'


def _get_slot_cell_idx(slot_name: str | int) -> int:
    if isinstance(slot_name, int):
        slot_num = slot_name % 64
    else:
        slot_num = int(hashlib.sha256(str(slot_name).encode()).hexdigest()[:8], 16) % 64
    # 64 slots of 16 cells each within the 1024-cell scratch window
    return SCRATCH_START + 1 + slot_num * 16


def compile(src: Sequence[str] | str, width_instrs: int = 8) -> np.ndarray:
    """Compile Glyph assembly source lines into a program image."""
    if isinstance(src, str):
        lines = [
            line.strip()
            for line in src.strip().splitlines()
            if line.strip() and not line.strip().startswith(";")
        ]
    else:
        lines = list(src)
    om = OpcodeMapV2()
    img = GlyphAssemblerV2(om).assemble(lines, width_instrs=width_instrs)
    om.close()
    return img


def run(
    image: np.ndarray,
    max_steps: int = 1000,
    cpu: GlyphCPUv2 | None = None,
    cols_instrs: int = 8,
) -> GlyphCPUv2:
    """Run a program image on GlyphCPUv2, enforcing fresh pc=(0,0) semantics."""
    if cpu is None:
        cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=cols_instrs)
    cpu.pc = (0, 0)
    cpu.run(image, max_instructions=max_steps)
    return cpu


def save(
    slot_name: str | int,
    words: Sequence[int],
    map_target: Path | str | Image.Image | None = None,
) -> tuple[int, int]:
    """Persist a word payload into the reserved scratch window.
    Returns (x, y) cell coordinates on the map."""
    cell_idx = _get_slot_cell_idx(slot_name)
    cx, cy = scratch_idx_to_xy(cell_idx)

    opened_here = False
    if isinstance(map_target, Image.Image):
        img = map_target
    else:
        path = DEFAULT_MAP_PATH if map_target is None else Path(map_target)
        if not path.exists():
            img = Image.new("RGB", (1024, 1024), (8, 10, 14))
        else:
            img = Image.open(path).convert("RGB")
        opened_here = True

    arr = np.array(img)
    n_words = len(words)
    payload_pixels = [(MAGIC_SCRATCH, (n_words >> 8) & 0xFF, n_words & 0xFF)]
    for w in words:
        payload_pixels.append(((w >> 16) & 0xFF, (w >> 8) & 0xFF, w & 0xFF))

    for p_idx, (r, g, b) in enumerate(payload_pixels):
        c_offset = p_idx // 64
        px_offset = p_idx % 64
        cur_cell = cell_idx + c_offset
        cur_cx, cur_cy = scratch_idx_to_xy(cur_cell)
        px_x = cur_cx * SCALE + (px_offset % SCALE)
        px_y = cur_cy * SCALE + (px_offset // SCALE)
        arr[px_y, px_x] = [r, g, b]

    res_img = Image.fromarray(arr)
    if opened_here:
        res_img.save(path)
    elif isinstance(map_target, Image.Image):
        map_target.paste(res_img)

    return cx, cy


def load(
    slot_name: str | int,
    map_target: Path | str | Image.Image | None = None,
) -> list[int]:
    """Read back a word payload from scratch pixels."""
    cell_idx = _get_slot_cell_idx(slot_name)
    if isinstance(map_target, Image.Image):
        arr = np.array(map_target)
    else:
        path = DEFAULT_MAP_PATH if map_target is None else Path(map_target)
        if not path.exists():
            return []
        arr = np.array(Image.open(path))

    cx, cy = scratch_idx_to_xy(cell_idx)
    h_px = arr[cy * SCALE, cx * SCALE]
    if h_px[0] != MAGIC_SCRATCH:
        return []
    n_words = (int(h_px[1]) << 8) | int(h_px[2])

    words = []
    for p_idx in range(1, n_words + 1):
        c_offset = p_idx // 64
        px_offset = p_idx % 64
        cur_cell = cell_idx + c_offset
        cur_cx, cur_cy = scratch_idx_to_xy(cur_cell)
        px_x = cur_cx * SCALE + (px_offset % SCALE)
        px_y = cur_cy * SCALE + (px_offset // SCALE)
        px = arr[px_y, px_x]
        w = (int(px[0]) << 16) | (int(px[1]) << 8) | int(px[2])
        words.append(w)

    return words


def verify_parity(
    band: np.ndarray,
    expected_str: str,
    rows: int = 8,
    cols: int = 40,
) -> bool:
    """Exact-match XOR decode via TextConsole. Returns True iff exact match."""
    try:
        con = TextConsole(rows=rows, cols=cols)
        decoded = con.decode_band(band)
        return decoded == expected_str
    except Exception:
        return False
