#!/usr/bin/env python3
"""dbg_bk40_stage_af3e — trace the L5 FILE_READ staging program instruction
by instruction to find which PARALLEL_ST hits word 168."""
import sys
sys.path.insert(0, "/home/jericho/projects/zion/worktrees/bk40-syscall")
sys.path.insert(0, "/home/jericho/projects/zion/worktrees/bk40-syscall/tools")

import numpy as np
from tools.glyph_isa_v2 import (
    GlyphAssemblerV2, INPUT_DATA_ADDR, INPUT_LEN_ADDR, OpcodeMapV2, W_MEM,
)
from tools.glyph_process import GlyphProcessTable

OM = OpcodeMapV2()
FIXTURE = "/tmp/bk40_gate_fixture"
FIXTURE_BYTES = b"KFENCE"
FR_IN_DEST = 176

path_bytes = FIXTURE_BYTES
out = []
for i, b in enumerate(path_bytes):
    out += ["LDI r5 %d" % (160 + i), "LDI r6 %d" % b, "PARALLEL_ST r5 r6 1"]
out += ["LDI r5 %d" % (160 + len(path_bytes)), "LDI r6 0", "PARALLEL_ST r5 r6 1"]
out += ["LDI r1 160", "LDI r2 %d" % FR_IN_DEST, "LDI r3 64",
        "SYSCALL r10 4", "HALT"]
print("instr count:", len(out))
for n, l in enumerate(out):
    print(n, l)

img = GlyphAssemblerV2(OM).assemble(out, width_instrs=8)
print("img shape:", img.shape)
table = GlyphProcessTable()
pid = table.spawn(img, name="dbg", tile=(5, 0, 8, 8))
cpu = table.tasks[pid]["cpu"]
cpu.memory[INPUT_DATA_ADDR >> 2] = ord("K")
cpu.memory[(INPUT_DATA_ADDR >> 2) + 1] = ord("F")
cpu.memory[INPUT_LEN_ADDR >> 2] = 2
rc = table.wait(pid)
print("rc:", rc, "faulted:", cpu.faulted, getattr(cpu, "fault_reason", ""))
print("mem[160..190]:", [int(v) for v in cpu.memory[160:191]])
print("img pix 176/32=5r16c:",
      table.tasks[pid]["image"][176 // W_MEM, 176 % W_MEM].tolist())
