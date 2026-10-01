#!/usr/bin/env python3
"""BK-41 RED probe (af3e) — measure TODAY's posture of every guest-reachable
write arm against the BOX_MMIO CONFIG words (the directive's scope):
  C1  USER unpaged ST to 8194 (KSYS_PC)  — out-of-box? in-box? E-K1 vs lands
  C2  USER PARALLEL_ST to 8194 (BK-39 gate live? expect refusal now)
  C3  USER unpaged ST to 8195 (BOX0_LO)
  C4  USER PARALLEL_ST to 8208 (TIMER_COUNT self-arm)
  C5  USER unpaged ST to 8282 (TILE_H disarm) then out-of-tile ST
  C6  SUPER post-SYSCALL handler ST to 8208 (exemption arm, not BK76-locked)
  C7  SUPER post-SYSCALL handler ST to 8195 (BOX0_LO)
Harness = the landed GlyphProcessTable.spawn(tile=...) path (item-29).
"""
import os
import sys

REPO = "/home/jericho/projects/zion/worktrees/bk41-config"
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))

import numpy as np  # noqa: E402
from tools.glyph_isa_v2 import (  # noqa: E402
    GlyphAssemblerV2, OpcodeMapV2,
    KSYS_PC_ADDR, KTICK_PC_ADDR, TIMER_COUNT_ADDR,
    TILE_H_ADDR, TILE_ROW_ADDR, BOX0_LO_ADDR,
    KFAULT_PC_ADDR, SYS_A0_ADDR,
)
from tools.glyph_process import GlyphProcessTable  # noqa: E402

OM = OpcodeMapV2()
KSYS_W, KTICK_W, TCOUNT_W = KSYS_PC_ADDR >> 2, KTICK_PC_ADDR >> 2, TIMER_COUNT_ADDR >> 2
TILEH_W, TILE_ROW_W, BOX0LO_W = TILE_H_ADDR >> 2, TILE_ROW_ADDR >> 2, BOX0_LO_ADDR >> 2
KFAULT_W = KFAULT_PC_ADDR >> 2
SYS_A0_W = SYS_A0_ADDR >> 2
TILE = (5, 0, 8, 8)
REAPER_ROW = 30

print("config words:", {"ksys": KSYS_W, "tcount": TCOUNT_W, "tile_h": TILEH_W,
                         "box0_lo": BOX0LO_W})


def bake(lines, canvas_rows=32):
    img = GlyphAssemblerV2(OM).assemble(lines, width_instrs=8)
    canvas = np.zeros((canvas_rows, 32, 3), dtype=np.uint8)
    canvas[0:img.shape[0]] = img
    return canvas


def spawn_and_run(canvas, pre=None):
    table = GlyphProcessTable()
    pid = table.spawn(image=canvas.copy(), tile=TILE, reaper_row=REAPER_ROW)
    cpu = table.tasks[pid]["cpu"]
    if pre:
        pre(cpu)
    table._run_task(pid)
    task = table.tasks[pid]
    return {
        "exit": task["exit_status"],
        "faulted": bool(cpu.faulted),
        "reason": (cpu.fault_reason or "")[:70],
        "mode": "USER" if cpu.mode == 1 else "SUPER",
        "ksys": int(cpu.memory[KSYS_W]),
        "box0lo": int(cpu.memory[BOX0LO_W]),
        "tcount": int(cpu.memory[TCOUNT_W]),
        "tile_h": int(cpu.memory[TILEH_W]),
        "sys_a0": int(cpu.memory[SYS_A0_W]),
    }


GADGET_PACKED = (6 << 16) | 0   # pixel row 6, col 0

results = []

# C1: USER unpaged ST to 8194
canvas = bake(["LDI r2 %d" % KSYS_W, "LDI r3 424242", "ST r2 r3", "HALT"])
results.append(("C1 user_st_ksys", spawn_and_run(canvas)))

# C2: USER PARALLEL_ST 0 into 8194 (disarm attempt; BK-39 fence should refuse)
canvas = bake(["LDI r2 %d" % KSYS_W, "LDI r3 0", "PARALLEL_ST r2 r3 1",
               "LDI r17 2", "SYSCALL r10 2", "HALT"],
              canvas_rows=32)
canvas[6, 0] = (1, 2, 3)  # gadget target pixel (dispatch would land in SUPER)
results.append(("C2 pst_disarm_ksys", spawn_and_run(canvas)))

# C3: USER unpaged ST to 8195 (BOX0_LO rewrite)
canvas = bake(["LDI r2 %d" % BOX0LO_W, "LDI r3 0", "ST r2 r3", "HALT"])
results.append(("C3 user_st_box0lo", spawn_and_run(canvas)))

# C4: USER PARALLEL_ST into TIMER_COUNT (tick self-arm)
canvas = bake(["LDI r2 %d" % TCOUNT_W, "LDI r3 2", "PARALLEL_ST r2 r3 1",
               "HALT"])
results.append(("C4 pst_tcount", spawn_and_run(canvas)))

# C5: USER unpaged ST to TILE_H (disarm tile) then out-of-tile ST
canvas = bake(["LDI r2 %d" % TILEH_W, "LDI r3 0", "ST r2 r3",
               "LDI r2 300", "LDI r3 31337", "ST r2 r3", "HALT"])
results.append(("C5 user_st_tileh", spawn_and_run(canvas)))

# C6/C7: KSYS-armed SUPER handler (gadget at pixel row 6) STs to
# TIMER_COUNT / BOX0_LO — the :968 exemption arm, words NOT BK-76-locked.
def super_case(gadget_lines, label):
    gadget = GlyphAssemblerV2(OM).assemble(gadget_lines, width_instrs=8)
    canvas = np.zeros((32, 32, 3), dtype=np.uint8)
    canvas[0:2] = GlyphAssemblerV2(OM).assemble(
        ["LDI r17 2", "SYSCALL r10 2", "HALT"], width_instrs=8)[0:2]
    canvas[6:6 + gadget.shape[0]] = gadget
    def pre(cpu):
        cpu.memory[KSYS_W] = GADGET_PACKED
        cpu.memory[KFAULT_W] = REAPER_ROW << 16
    r = spawn_and_run(canvas, pre=pre)
    results.append((label, r))

super_case(["LDI r2 %d" % TCOUNT_W, "LDI r3 4242", "ST r2 r3", "HALT"],
           "C6 super_st_tcount")
super_case(["LDI r2 %d" % BOX0LO_W, "LDI r3 0", "ST r2 r3", "HALT"],
           "C7 super_st_box0lo")

for name, r in results:
    print(name, "->", r)
