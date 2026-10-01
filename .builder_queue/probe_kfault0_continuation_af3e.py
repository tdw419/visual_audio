"""Oracle-side KFAULT_PC=0 continuation quirk — PC-trace probe (builder af3e62239ce2,
2026-09-27). Same program as dbg_mmio_door_oracle_af3e.py (USER ST to word 8196, an
out-of-box address under box [1200,1300)) but with a per-step PC/mode trace and a
KFAULT_PC=0 vs KFAULT_PC=handler contrast leg.

Hypothesis under test (from RESEARCH_wgsl_mmio_door_af3e.md disclosure): the E-K1 ST
trap branch (tools/glyph_isa_v2.py:1049-1069) vectors to KFAULT_PC WITHOUT the
kf != 0 guard that every other fault site has (:855-861, :889-895, ...). With
KFAULT_PC == 0 the trap becomes next_pc = (0, 0) — program entry, now in SUPER
mode — so the trapped task replays, re-executes the same ST as SUPER, and the
store LANDS. That would falsify the docstring's "do NOT perform the store"
semantics for the kf=0 case and explain the BK-50/BK-51 disclosed quirk.
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


def run_case(kfault_pc: int, label: str) -> dict:
    with tempfile.TemporaryDirectory() as td:
        png = Path(td) / "p.png"
        bake_image(prog, cols_instrs=8, out_path=png)
        img = GlyphRunner(png).image

    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=8)
    cpu.memory = np.zeros(16384, dtype=np.uint64).tolist()
    cpu.memory[8195] = 1200
    cpu.memory[8196] = 1300
    cpu.memory[1024 + 1] = 0  # keep FAULT words clear; KFAULT_PC stays 0 unless set
    if kfault_pc:
        # packed pixel PC for a handler: none installed in this probe; leg B
        # only checks that a nonzero kf is honored as a vector target shape.
        cpu.memory[1024 + 0] = kfault_pc
    cpu.mode = MODE_USER
    steps = 0
    trace = []
    while cpu.running and steps < 12:
        px, py = cpu.pc
        trace.append((steps, (px, py), int(cpu.mode), bool(cpu.faulted),
                      hex(cpu.fault_addr) if cpu.fault_addr else 0))
        cpu.step(img)
        steps += 1
    px, py = cpu.pc
    trace.append(("final", (px, py), int(cpu.mode), bool(cpu.faulted),
                  hex(cpu.fault_addr) if cpu.fault_addr else 0))
    out = {
        "label": label,
        "trace": trace,
        "word8196": int(cpu.memory[8196]),
        "fault_pc_packed": hex(cpu.fault_pc) if cpu.fault_pc else 0,
        "running": bool(cpu.running),
    }
    return out


resA = run_case(0, "A: KFAULT_PC=0 (uninstalled handler)")
resB = run_case(0, "B: KFAULT_PC=0 rerun (determinism check)")

for r in (resA, resB):
    print("===", r["label"], "===")
    for t in r["trace"]:
        print(t)
    print("word8196 =", r["word8196"], "(11399181 = store LANDED, 1300 = refused)")
    print("fault_pc_packed:", r["fault_pc_packed"], "running:", r["running"])
