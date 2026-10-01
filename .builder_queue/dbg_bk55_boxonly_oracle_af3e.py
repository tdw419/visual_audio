"""BK-55-remaining posture check (af3e, 2026-10-01): oracle control for
the box-confined-only (NO tile) arming store ST -> KFAULT_PC (8193).
Same shape as dbg_mmio_door_oracle_af3e but aimed at 8193 with canary.
Question: does the oracle E-K1 refuse the arming store where the twin
door takes it (bk50 twin lock is TILE_H-gated, so no-tile = no lock)?
"""
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

CANARY = 0x0ADF00D
prog = """
:__entry
LDI r7 8193
LDI r5 %d
ST r7 r5
HALT
""" % CANARY

with tempfile.TemporaryDirectory() as td:
    png = Path(td) / "p.png"
    bake_image(prog, cols_instrs=8, out_path=png)
    img = GlyphRunner(png).image

cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=8)
cpu.memory = np.zeros(16384, dtype=np.uint64).tolist()
cpu.memory[8195] = 1200
cpu.memory[8196] = 1300
cpu.mode = 1  # MODE_USER
cpu.running = True
steps = 0
while cpu.running and steps < 40:
    cpu.step(img)
    steps += 1
print("oracle box-only USER ST->8193: faulted:", cpu.faulted,
      "fault_addr:", cpu.fault_addr,
      "mode_final:", cpu.mode,
      "word8193:", cpu.memory[8193],
      "canary_landed:", cpu.memory[8193] == CANARY,
      "steps:", steps)
