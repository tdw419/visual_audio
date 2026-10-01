"""GH-28: Spatial Build Map as Writable Glyph Substrate — smoke gate.

L1 addressability:   the live map is a real Glyph container, pixels == JSON schema.
L2 confinement:      a scratch stamp touches exactly its 8x8 cell, zero bleed.
L3 execution:        a Glyph program stamped into a scratch cell executes on GlyphCPUv2.
L4 persistence:      scratch-window payloads SURVIVE render() (ruled posture:
                     reserved scratch window, tools/map_scratch.py); a stamp OUTSIDE
                     the window still gets clobbered — the old measured behavior,
                     pinned as the falsifier.

Probe discipline: legs L2-L4 run against COPIES (tmp files), never the live
build_map.png. Only L1 reads the live artifact.
"""
import sys
import shutil
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from tools.spatial_build_map import render
from tools.map_scratch import (
    SIDE, SCRATCH_SIDE, SCRATCH_START, scratch_is_cell, scratch_idx_to_xy,
    stamp_scratch, read_scratch,
)
from tools.glyph_isa_v2 import OpcodeMapV2, GlyphAssemblerV2, GlyphCPUv2

COMMIT_BLUE = (55, 110, 220)
SCALE = 8
HISTORY_IDX = 0            # cell (0,0): commit blue, history territory
SCRATCH_IDX = SCRATCH_START + 5   # first interior scratch cell (not the border)


def _as_array(png: Path) -> np.ndarray:
    return np.array(Image.open(png))


def _px(arr: np.ndarray, x: int, y: int) -> tuple:
    return tuple(int(v) for v in arr[y * SCALE, x * SCALE][:3])


def test_l1_addressability_live_map_matches_schema():
    """L1: live map loads as a Glyph container; cell (0,0) is commit blue and
    agrees with build_map_data.json."""
    arr = _as_array(REPO / "build_map.png")
    assert arr.shape == (1024, 1024, 3) and arr.dtype == np.uint8
    data = __import__("json").loads((REPO / "build_map_data.json").read_text())
    assert len(data["cells"]) == data["meta"]["cells_used"]
    c0 = next(c for c in data["cells"] if c["idx"] == HISTORY_IDX)
    assert c0["type"] == "commit"
    x, y = c0["x"], c0["y"]
    assert _px(arr, x, y) == COMMIT_BLUE == tuple(int(c0["color"][i:i + 2], 16)
                                                  for i in (1, 3, 5))


def test_l2_confinement_scratch_stamp_exact_64px():
    """L2: stamping a scratch cell changes exactly 64 pixels, all inside its box."""
    img = Image.new("RGB", (1024, 1024), (8, 10, 14))
    before = np.array(img).copy()
    stamp_scratch(img, SCRATCH_IDX, (236, 80, 80))
    after = np.array(img)
    changed = np.argwhere(np.any(before != after, axis=2))
    assert len(changed) == 64
    sx, sy = scratch_idx_to_xy(SCRATCH_IDX)
    assert np.all(changed[:, 1] // SCALE == sx) and np.all(changed[:, 0] // SCALE == sy)


def test_l3_scratch_cell_executes_glyph_program():
    """L3: LDI r3 42 / HALT stamped into a scratch cell runs on GlyphCPUv2, r3 == 42."""
    op = OpcodeMapV2(); asm = GlyphAssemblerV2(op)
    prog = asm.assemble(["LDI r3 42", "HALT"], width_instrs=SCRATCH_SIDE)  # (1, 32, 3)
    img = Image.new("RGB", (1024, 1024), (8, 10, 14))
    stamp_scratch(img, SCRATCH_IDX, (236, 80, 80))          # mark the cell like real use
    arr = np.array(img)
    sx, sy = scratch_idx_to_xy(SCRATCH_IDX)
    # write the program INTO the map at the scratch cell, then read it back out —
    # the map is the instruction source, not the assembler
    arr[sy * SCALE:(sy + 1) * SCALE, sx * SCALE:sx * SCALE + prog.shape[1]] = prog[0]
    scanline = np.ascontiguousarray(
        arr[sy * SCALE, sx * SCALE:sx * SCALE + 32][None])  # (1, 32, 3)
    cpu = GlyphCPUv2(op, cols_instrs=SCRATCH_SIDE)
    cpu.pc = (0, 0)
    n = cpu.run(scanline, max_instructions=8)
    assert n == 2 and not cpu.running
    assert cpu.registers[3] == 42, f"r3={cpu.registers[3]}"


def test_l4_scratch_survives_render_history_still_clobbers():
    """L4 (the rewritten clobber pin): payloads in the scratch window SURVIVE
    render(); stamps in history territory are still wiped — the old measured
    behavior, retained as the falsifier of the boundary itself."""
    tmp_png = Path("/tmp/gh28_l4_probe.png")
    tmp_json = Path("/tmp/gh28_l4_probe.json")
    shutil.copy(REPO / "build_map.png", tmp_png)
    img = Image.open(tmp_png)
    stamp_scratch(img, SCRATCH_IDX, (236, 80, 80))          # payload INSIDE window
    # payload OUTSIDE window: paint history cell (0,0) over with an alien color
    arr0 = np.array(img)
    arr0[0:SCALE, 0:SCALE] = (236, 80, 80)
    Image.fromarray(arr0).save(tmp_png)

    render(side=SIDE, out=tmp_png, data_out=tmp_json)
    arr = _as_array(tmp_png)

    # scratch payload SURVIVED (the new ruled guarantee)
    assert read_scratch(arr, SCRATCH_IDX) == (236, 80, 80), "scratch payload clobbered"
    # history stamp CLOBBERED back to commit blue (boundary enforcement)
    assert _px(arr, 0, 0) == COMMIT_BLUE, "history territory was NOT restored"

    # and render() itself never paints scratch: force it to try
    r = render(side=SIDE, out=tmp_png, data_out=tmp_json)
    assert r["cells_used"] <= SCRATCH_START, "history overflowed scratch window"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
