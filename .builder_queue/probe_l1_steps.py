#!/usr/bin/env python3
"""L1 pre-landing measurement: steps budget probe for the LONGEST planned L1
turn (echo of a full 62-byte line ≈ the longest collect loop)."""
import sys, tempfile
from pathlib import Path
sys.path[:0] = [".", "tools", "experiments"]

import numpy as np
from glyph_interactive_shell import build_dispatch_shell, run_turn
from tools.glyph_isa_v2 import GlyphCPUv2, OpcodeMapV2

d = Path(tempfile.mkdtemp())
image = build_dispatch_shell(str(d / "w.dat"), str(d / "a.wav"))
cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=8, fs_pix_enabled=True)
cpu.memory = [0] * 16384

line = "e " + "y" * 60
data = line.encode()
cpu.memory[7900] = len(data)
cpu.memory[7904] = 0
for i, b in enumerate(data):
    cpu.memory[7908 + i] = b
cpu.pc = (0, 0)
cpu.registers = [0] * 32
cpu.output = []
cpu.running = True
cpu.halted = False
cpu.faulted = False

# manual run with huge budget, counting steps by patching run()
n = cpu.run(image, max_instructions=100000)
print("longest-turn steps measured:", n, "halted:", cpu.halted, "faulted:", cpu.faulted)
print("turn budget in run_turn: max(2048, len*16+512) =", max(2048, len(data) * 16 + 512))
