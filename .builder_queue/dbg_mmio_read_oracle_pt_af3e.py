"""D5 oracle-parity control (dbg form): the D2 program (USER LD of word
8193 -> in-box ST of word 310) on GlyphCPUv2, config words seeded in
plain self.memory, cpu.running=True before stepping. The probe's baked
D2 image halts the run()-form with an opcode-None dead pixel at (28,0)
(after HALT's row; disclosed in the receipt) before the verdict read --
this harness steps manually and reads the conviction directly.
Conviction: memory[310] == 7, mode stays USER, faulted == False:
PARITY -- the oracle's USER LD reads its config block too.

Run: python3 .builder_queue/dbg_mmio_read_oracle_pt_af3e.py
"""
import sys
import tempfile
from pathlib import Path

REPO = Path("/home/jericho/projects/zion/projects/visual_audio")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from tools.glyph_isa_v2 import GlyphCPUv2, OpcodeMapV2  # noqa: E402
from tools.glyph_gpt.baker import bake_image  # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner  # noqa: E402

RESULT_WORD = 310
KFAULT_PC_WORD = 8193
prog = """
:__entry
LDI r6 %d
LD r5 r6
LDI r7 %d
ST r7 r5
HALT
""" % (KFAULT_PC_WORD, RESULT_WORD)

with tempfile.TemporaryDirectory() as td:
    png = Path(td) / "p.png"
    bake_image(prog, cols_instrs=8, out_path=png)
    img = GlyphRunner(png).image

cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=8)
cpu.memory = [0] * 16384
cpu.memory[KFAULT_PC_WORD] = 7
cpu.memory[8195] = 1200
cpu.memory[8196] = 1300
cpu.mode = 1  # MODE_USER, no page table
cpu.running = True
while cpu.running:
    cpu.step(img)
print("faulted:", cpu.faulted, "mode_final:", cpu.mode,
      "word310:", cpu.memory[RESULT_WORD])
