#!/usr/bin/env python3
"""Per-step trace of the self-text dispatcher probe: did the window store
really land via the dispatcher's SUPER execution, and where did PRT go?"""
import sys
from pathlib import Path

HERE = Path('/home/jericho/projects/zion/projects/visual_audio')
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tools"))

from tools.glyph_process import GlyphProcessTable  # noqa: E402
from tools.glyph_gpt.baker import bake_image  # noqa: E402
from tools.glyph_containment import arm_tile  # noqa: E402
from tools.glyph_isa_v2 import OpcodeMapV2  # noqa: E402

TILE = (256, 19, 1, 2)
WORD_KSYS = 8194
PACKED_D1 = (1 << 16) | 0

text = (
    ":__entry\n"
    "SYSCALL r10 6\n"
    ":post\n"
    "LDI r3 99\n"
    "HALT\n"
    ":handler\n"
    "LDI r6 %d\n"
    "LDI r7 %d\n"
    "ST r7 r6\n"
    "LDI r5 52\n"
    "PRT r6\n"
    "SYSRET\n"
    % (PACKED_D1, WORD_KSYS)
)

table = GlyphProcessTable(cols_instrs=8, memory_words=16384)
img = bake_image(text, cols_instrs=8, min_rows=64, out_path=None)
h, w, _ = img.shape
print('image', img.shape)
# per-step trace in the same posture
from tools.glyph_isa_v2 import GlyphCPUv2
from tools.glyph_containment import wrap_with_reaper
img2 = wrap_with_reaper(img, 30, OpcodeMapV2())
if img2.shape[0] > img.shape[0]:
    import numpy as np
    img2 = np.concatenate([img, img2[img.shape[0]:]], axis=0)
cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=8)
cpu.memory = [0] * 16384
arm_tile(cpu, TILE)
cpu._tile_confinement = True
cpu.memory[8193] = 30 << 16
cpu.memory[WORD_KSYS] = PACKED_D1
cpu.running = True
steps = 0
while cpu.running and steps < 60:
    x, y = cpu.pc
    cpu.step(img2)
    print('step %2d pc=(%d,%d) mode=%s ksys=%d out=%s fault=%s' % (
        steps, x, y, 'SUPER' if cpu.mode == 0 else 'USER',
        cpu.memory[WORD_KSYS], cpu.output, cpu.fault_reason or cpu.faulted))
    steps += 1
