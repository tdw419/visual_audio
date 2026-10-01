"""KFAULT_PC=0 continuation quirk — root-cause probe, leg C/D (builder af3e62239ce2).

Hypothesis (from source read of tools/glyph_isa_v2.py:1049-1069): the E-K1
out-of-box USER ST branch vectors to KFAULT_PC with NO `kf != 0` guard (every
other fault site has an `else: self.running = False` arm). With KFAULT_PC == 0:
  next_pc = (0 * INSTR_WIDTH, 0) = (0, 0)  → the trap re-enters the program
  at word 0, mode already switched to SUPER.
Replay as SUPER: same ST passes (E-K1 consult only fires in USER), store LANDS.
Determinism check then runs the SAME replay to completion; `running` at the end
names the final semantics.

Leg C pins the mid-replay machine state (step-by-step). Leg D pins the
replay end-state + word8196 (store landed vs refused) — the falsifier for the
branch docstring's "do NOT perform the store" semantics at kf=0.
"""
import sys
import tempfile
from pathlib import Path

REPO = Path("/home/jericho/projects/zion/projects/visual_audio")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

import numpy as np  # noqa: E402

from tools.glyph_isa_v2 import GlyphCPUv2, OpcodeMapV2, MODE_USER  # noqa: E402
from tools.glyph_gpt.baker import bake_image  # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner  # noqa: E402

prog = """
:__entry
LDI r5 11399181
LDI r6 8196
ST r6 r5
HALT
"""


def fresh_cpu():
    with tempfile.TemporaryDirectory() as td:
        png = Path(td) / "p.png"
        bake_image(prog, cols_instrs=8, out_path=png)
        img = GlyphRunner(png).image
    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=8)
    cpu.memory = np.zeros(16384, dtype=np.uint64).tolist()
    cpu.memory[8195] = 1200
    cpu.memory[8196] = 1300
    cpu.mode = MODE_USER
    return img, cpu


# ---- Leg C: step-by-step trace of the trap + replay (KFAULT_PC = 0) ----
img, cpu = fresh_cpu()
cpu.running = True  # run() sets this; the manual loop must too (probe-defect fixed before any conclusion)
print("=== leg C: step trace, KFAULT_PC=0 ===")
steps = 0
while cpu.running and steps < 10:
    px, py = cpu.pc
    print(f"pre-step{steps}: pc=({px},{py}) mode={int(cpu.mode)} "
          f"faulted={cpu.faulted} fault_addr={hex(cpu.fault_addr) if cpu.fault_addr else 0}")
    cpu.step(img)
    steps += 1
print(f"post-final: pc={cpu.pc} mode={int(cpu.mode)} running={cpu.running} steps={steps}")

# ---- Leg D: full replay via cpu.run() — end-state semantics ----
img2, cpu2 = fresh_cpu()
n = cpu2.run(img2, max_instructions=50)
print("=== leg D: run() to completion, KFAULT_PC=0 ===")
print("steps:", n, "running:", cpu2.running, "halt_reason:", cpu2.halt_reason,
      "mode_final:", int(cpu2.mode), "word8196:", int(cpu2.memory[8196]))
print("(11399181 = store LANDED through the kf=0 replay; 1300 = refused)")

# ---- Leg E: contrast — same program, KFAULT_PC = valid handler at word 4 (px 16, row 0)? ----
# No real handler baked; instead contrast the guard presence structurally:
img3, cpu3 = fresh_cpu()
cpu3.memory[1024 + 0] = (0 << 16) | 0  # explicit 0 — same as unset
cpu3.run(img3, max_instructions=50)
print("=== leg E: explicit KFAULT_PC=0 (identical to default) ===")
print("word8196:", int(cpu3.memory[8196]), "running:", cpu3.running)
