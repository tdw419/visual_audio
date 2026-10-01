#!/usr/bin/env python3
"""Manual rot-check (not a gate leg): run T1's Task-A program on the REAL
engine in the manual posture T3 uses, asserting the fence refuses and the
canary does NOT land — proves T3's neutered-module leg discriminates against
the real engine's behavior (the two runs differ ONLY in the module)."""
import sys
sys.path.insert(0, ".")
sys.path.insert(0, "tools")
from tools.glyph_isa_v2 import GlyphCPUv2, OpcodeMapV2
from tools.glyph_containment import arm_tile, wrap_with_reaper
from tools.glyph_gpt.baker import bake_image

CANARY = 0x0ADF00D
PT_TAG_WORD = 1535
PT_BASE = 1536
ARM = 8211
TILE = (256, 19, 1, 2)
text = (":__entry\nLDI r15 %d\nLDI r14 %d\nST r15 r14\n"
        "LDI r5 %d\nLDI r15 1535\nST r15 r5\nHALT\n" % (ARM, PT_BASE, CANARY))


def stamp(img, d):
    h, w, _ = img.shape
    for word, val in d.items():
        i = word % (h * w)
        img[i // w, i % w] = ((val >> 16) & 255, (val >> 8) & 255, val & 255)
    return img


img = wrap_with_reaper(
    stamp(bake_image(text, cols_instrs=8, min_rows=64, out_path=None),
          {PT_TAG_WORD: 0x505447, PT_BASE + 5: 0x7 | (5 << 8)}),
    30, OpcodeMapV2())
cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=8)
cpu.memory = [0] * 16384
arm_tile(cpu, TILE)
cpu._tile_confinement = True  # spawn(tile=...) sets this; arm_tile alone does not
cpu.memory[8193] = 30 << 16
cpu.running = True
s = 0
while cpu.running and s < 12:
    print("step", s, "r15", cpu.registers[15] & 0xFFFFFFFF,
          "r14", cpu.registers[14] & 0xFFFFFFFF, "r5", cpu.registers[5] & 0xFFFFFFFF,
          "word1535", hex(cpu.memory[PT_TAG_WORD] & 0xFFFFFFFF),
          "faulted", cpu.faulted, "pc_y", getattr(cpu, "pc_y", None))
    cpu.step(img)
    s += 1
print("END: faulted", cpu.faulted, "word1535",
      hex(cpu.memory[PT_TAG_WORD] & 0xFFFFFFFF),
      "reason", repr(cpu.fault_reason))
faulted = cpu.faulted
word1535 = cpu.memory[PT_TAG_WORD] & 0xFFFFFFFF
reason = cpu.fault_reason
print("REAL engine: faulted=%s word1535=%#x reason=%r" % (faulted, word1535, reason))
assert faulted, "real engine must refuse the header-window paged ST"
assert "paged_paddr_fence" in (reason or "")
assert "paddr=1535" in (reason or "")
assert word1535 != CANARY, "canary must NOT land on the real engine"
print("ROT-CHECK OK: real engine refuses; T3's neutered copy landing the canary is a discriminating contrast")
