import sys
import tempfile
from pathlib import Path

REPO = Path("/home/jericho/projects/zion/projects/visual_audio")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

import numpy as np
from tools.glyph_isa_v2 import GlyphCPUv2, OpcodeMapV2
from tools.glyph_gpt.baker import bake_image
from tools.glyph_gpt.runner import GlyphRunner

prog = """
:__entry
LDI r6 8193
LD r5 r6
LDI r7 1250
ST r7 r5
HALT
"""
with tempfile.TemporaryDirectory() as td:
    png = Path(td) / "p.png"
    bake_image(prog, cols_instrs=8, out_path=png)
    img = GlyphRunner(png).image

cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=8)
cpu.memory = [0] * 16384
cpu.memory[8193] = 7
cpu.memory[8195] = 1200
cpu.memory[8196] = 1300
cpu.mode = 1
cpu.running = True
print("initial running:", cpu.running)
for n in range(1, 9):
    if not cpu.running:
        break
    cpu.step(img)
    x, y = cpu.pc
    print("step", n, "pc", (x, y), "r5", cpu.registers[5],
          "r7", cpu.registers[7], "w1250", cpu.memory[1250],
          "faulted", cpu.faulted, "mode", cpu.mode,
          "halt", repr(cpu.halt_reason))
