"""Oracle-twin control for the BK-50 WGSL MMIO-door probe: the SAME
program (USER ST of 0x0ADF00D to word 8196) on GlyphCPUv2.step. The
oracle's single consult at glyph_isa_v2.py:1041 should fire E-K1
(byte 32784 is outside box [1200,1300)), refuse the store, drop to
SUPER, and halt (KFAULT_PC==0)."""
import sys
import tempfile
from pathlib import Path

REPO = Path("/home/jericho/projects/zion/projects/visual_audio")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

import numpy as np  # noqa: E402

from tools.glyph_isa_v2 import GlyphCPUv2, OpcodeMapV2  # noqa: E402
from tools.glyph_gpt.baker import bake_image  # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner  # noqa: E402

prog = """
:__entry
LDI r5 11399181
LDI r6 8196
ST r6 r5
HALT
"""
with tempfile.TemporaryDirectory() as td:
    png = Path(td) / "p.png"
    bake_image(prog, cols_instrs=8, out_path=png)
    img = GlyphRunner(png).image

cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=8)
cpu.memory = np.zeros(16384, dtype=np.uint64).tolist()
cpu.memory[8195] = 1200
cpu.memory[8196] = 1300
cpu.mode = 1  # MODE_USER
steps = 0
while cpu.running and steps < 40:
    cpu.step(img)
    steps += 1
print("faulted:", cpu.faulted,
      "fault_addr:", hex(cpu.fault_addr) if cpu.fault_addr else 0,
      "mode_final:", cpu.mode,
      "word8196:", cpu.memory[8196],
      "steps:", steps)
