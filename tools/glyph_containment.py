"""glyph_containment.py — item-29 per-process spatial containment.

CLAIM QUEUE round-13 item 29 (operator sign-off ec5fea0f): "bind GO-1/GO-2
box enforcement to spawn-allocated tiles".

Landscape (grounded in landed artifacts):
  - GO-1 (engine, landed): GlyphCPUv2 already enforces spatial boxes. A
    USER-mode store outside every armed range traps: FAULT_ADDR/FAULT_PC
    are recorded, the store does NOT land, mode drops to SUPER, and the
    PC vectors to KFAULT_PC (glyph_isa_v2.py:1041-1056). SUPER mode is
    never checked (kernel immunity).
  - GO-2 (engine, landed): one of those ranges is a 2D TILE — words
    TILE_ROW/COL/H/W at BOX_MMIO_BASE+0x160..0x16C; the predicate maps a
    byte address to grid (row, col) via W_MEM=32 words/row and admits
    [row, row+h) x [col, col+w) (glyph_isa_v2.py:734-747).
  - item-26 (host, landed): GlyphProcessTable spawns each task as a fresh
    GlyphCPUv2 — but every engine ran in MODE_SUPER with no box armed:
    process isolation was RAM-copy isolation, not CONTAINMENT. A runaway
    task could write anywhere in its own RAM, including the MMIO box
    words themselves.

item-29 closes that: spawn(tile=...) arms the tile words in the task's
own RAM BEFORE the program runs and drops the engine to MODE_USER, so
the engine's EXISTING box check fences the task to its tile. spawn
also arms KFAULT_PC (reaper_pc=) to a one-instruction reaper trampoline
the table plants in a tall copy of the program image; after the trap the
offending task HALTs parked on the trampoline in SUPER mode, and the
table's existing fault mapping (glyph_process.py _run_task) reaps it as
EXIT_FAULT. A second COPY of the tile words is kept OUTSIDE the task's
reachable RAM plane is NOT possible — the tile words live in task RAM by
GO-1 design — so the honest containment statement is: the fence the
task cannot cross is its own tile; the words ARMING the fence are
writable by a SUPER-mode store, and USER mode cannot store anywhere
outside the tile, INCLUDING the box words. Arming happens before the
first instruction executes, so a task can never re-arm or disarm its
own fence from USER mode. (A task that never exits USER mode cannot
reach SUPER: mode changes only via the E-K1 trap, KJMP, SYSRET, tick —
none of which the fence-crossing store itself can trigger except the
trap that catches it.)

What this is NOT: no new syscall numbers, no engine change (the gate
asserts the engine file is byte-identical to HEAD), no preemption, no
kernel image — the reaper trampoline is a table-owned HALT row, not a
guest kernel.
"""
from __future__ import annotations

import numpy as np

from tools.glyph_isa_v2 import (  # noqa: F401
    FAULT_ADDR_ADDR,
    FAULT_PC_ADDR,
    GlyphAssemblerV2,
    GlyphCPUv2,
    INSTR_WIDTH,
    KFAULT_PC_ADDR,
    OpcodeMapV2,
    TILE_COL_ADDR,
    TILE_H_ADDR,
    TILE_ROW_ADDR,
    TILE_W_ADDR,
    W_MEM,
)

# Default reaper row: tall enough to sit above any realistic program image
# assembled at width_instrs=8 (a 30-row program is 240 instructions).
DEFAULT_REAPER_ROW = 30


class ContainmentError(Exception):
    pass


def arm_tile(cpu: GlyphCPUv2, tile: tuple[int, int, int, int]) -> None:
    """Arm the GO-2 tile words in `cpu`'s RAM and drop the engine to USER.

    tile = (row, col, height, width) in W_MEM-word grid cells. Called by
    the table at spawn time, BEFORE the task's first instruction — the
    arming stores happen in HOST Python (memory list assignment), never
    through the engine's own checked store path, so no ordering hazard
    exists: the first instruction the task executes already runs fenced.
    """
    r, c, h, w = tile
    if not all(isinstance(v, int) and v >= 0 for v in (r, c, h, w)):
        raise ContainmentError(f"tile must be 4 non-negative ints, got {tile!r}")
    if h == 0 or w == 0:
        # TILE_H==0 means "tile unset / inert" in the engine predicate; a
        # caller asking for a zero-extent tile is asking for NO containment
        # while getting USER-mode noise. Refuse rather than silently unfence.
        raise ContainmentError("tile height and width must be nonzero (use tile=None for an unfenced task)")
    cpu.memory[TILE_ROW_ADDR >> 2] = r
    cpu.memory[TILE_COL_ADDR >> 2] = c
    cpu.memory[TILE_H_ADDR >> 2] = h
    cpu.memory[TILE_W_ADDR >> 2] = w
    from tools.glyph_isa_v2 import MODE_USER  # local import: constant only
    cpu.mode = MODE_USER


def default_reaper_pc(reaper_row: int = DEFAULT_REAPER_ROW) -> int:
    """The packed KFAULT_PC vector to the default reaper trampoline row."""
    return reaper_row << 16


def wrap_with_reaper(image: np.ndarray, reaper_row: int,
                     opcode_map: OpcodeMapV2) -> np.ndarray:
    """Return a TALL COPY of `image` with a HALT planted at (col 0,
    reaper_row). The copy is deliberate: callers must never mutate the
    image a task was spawned with in place (the table treats the image as
    the task's program ROM)."""
    need_cols = image.shape[1]
    need_rows = reaper_row + 1
    if image.shape[0] >= need_rows:
        img = image.copy()
    else:
        img = np.zeros((need_rows, need_cols, 3), dtype=np.uint8)
        img[: image.shape[0]] = image
    halt_rgb = opcode_map.opcode_to_rgb("HALT")
    img[reaper_row, 0] = halt_rgb
    return img
