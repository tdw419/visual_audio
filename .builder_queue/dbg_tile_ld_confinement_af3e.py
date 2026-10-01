#!/usr/bin/env python3
"""L3 leg failure diagnosis (af3e, tick 3): tile-armed USER LD of word 4000
ran 21 steps and halted with faulted=False, fault_addr=0, mode USER — but
the same tile-arm posture + an out-of-tile ST traps (BK-51 oracle control).
Why did the LD not trap at :932?

Suspect: `:__kmain`'s tile+MMIO prologue stores happen in SUPER BEFORE the
MODE_LATCH/KJMP — fine. But the LD leg's :__task reads r15=4000 → LD r10.
Branch order at glyph :834: `if pt_base != 0 and not (SUPER and MMIO)`.
TILE words at 8280..8283 sit INSIDE the MMIO window (BOX_MMIO_BASE=0x8000 →
words 8192..8447). PAGE_TABLE_ADDR is word 8211; I did NOT arm it (arm=False)
so pt_base==0 → the paged branch is skipped. Then `elif USER and
_tile_confinement` at :917 — but this probe drives GlyphCPUv2 DIRECTLY
(no GlyphProcessTable.spawn), and _tile_confinement is set ONLY by
glyph_process.py:166 (`cpu._tile_confinement = True` on spawn(tile=...)).
My leg never sets it → the tile branch is dead → the LD falls through to
the plain read and word 4000 reads as... seeded canary, then HALT.
BUT fault_addr=0 + 21 steps + running_after=False means the program just
completed. Hypothesis: the harness gap is _tile_confinement, not the fence.
This script arms _tile_confinement=True directly (spawn-equivalent posture)
and re-runs the SAME program. Prediction: faulted=True, fault_addr=16000
(word 4000 << 2), reason None — S3 confirmed silent.

Run: python3 .builder_queue/dbg_tile_ld_confinement_af3e.py
"""
import sys
from pathlib import Path

REPO = Path("/home/jericho/projects/zion/projects/visual_audio")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from tools.glyph_isa_v2 import (  # noqa: E402
    TILE_COL_ADDR, TILE_H_ADDR, TILE_ROW_ADDR, TILE_W_ADDR,
    GlyphCPUv2, OpcodeMapV2,
)
from tools.glyph_gpt.baker import bake_image  # noqa: E402

CANARY = 0x0ADF00D


def run(label, target_word, seed):
    prog = f"""
:__entry
LDI r15 {target_word}
LD r10 r15
HALT
"""
    img = bake_image(prog, cols_instrs=8)
    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=8)
    cpu.memory = [0] * 16384
    cpu.memory[target_word] = seed
    # arm_tile semantics + spawn(tile=...)'s confinement flag (glyph_process.py:166)
    cpu.memory[TILE_ROW_ADDR >> 2] = 5
    cpu.memory[TILE_COL_ADDR >> 2] = 0
    cpu.memory[TILE_H_ADDR >> 2] = 2
    cpu.memory[TILE_W_ADDR >> 2] = 4
    cpu.mode = 1  # MODE_USER
    cpu._tile_confinement = True
    steps = 0
    cpu.running = True
    while cpu.running and steps < 200:
        cpu.step(img)
        steps += 1
        if cpu.faulted:
            break
    print(label, "->", "faulted:", cpu.faulted,
          "fault_addr:", cpu.fault_addr,
          "fault_reason:", cpu.fault_reason,
          "r10:", cpu.registers[10],
          "mode_final:", cpu.mode, "steps:", steps)


# Out-of-tile LD (word 4000): S3 — does it trap and is reason silent?
run("tile_ld_out_of_tile_4000", 4000, CANARY)
# In-tile control (word 160 = row 5, col 0): must read clean, no fault.
run("tile_ld_in_tile_160_control", 160, 4660)
