import sys, tempfile
from pathlib import Path
sys.path.insert(0, 'tools'); sys.path.insert(0, '.')
import numpy as np

sys.path.insert(0, '.builder_queue')
from probe_d1_attribution_af3e import (kernel_prologue, kernel_epilogue,
                                       bake_two_pass, stamp_image,
                                       PT_TAG_WORD, PT_ARM_WORD,
                                       VPN12_PTE_WORD, VA_CANARY, CANARY)

from tools.glyph_isa_v2 import GlyphCPUv2, OpcodeMapV2

pte_vwu_12 = 1 | 2 | 4 | (12 << 8)
stamps = {PT_TAG_WORD: 0x505447, PT_ARM_WORD: 1536, VPN12_PTE_WORD: pte_vwu_12}
prog = (kernel_prologue()
        + ":__task\nLDI r15 %d\nLD r10 r15\n" % VA_CANARY
        + kernel_epilogue())
img = bake_two_pass(prog, cols_instrs=8)
h, w, _ = img.shape
print("dims", w, "x", h, "=", w * h, "words")
# tag word address bounds
print("tag_addr 1535 in-bounds?", 1535 < w * h)
stamp_image(img, {VA_CANARY: CANARY})
stamp_image(img, stamps)

cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=8, fs_pix_enabled=True)
r, g, b = img[1535 // w, 1535 % w]
print("pixel at word 1535 pre-exec:", int(r), int(g), int(b),
      "=>", (int(r) << 16) | (int(g) << 8) | int(b))
# What's at the word AFTER stamping — does stamp_image write where we think?
wrow, wcol = 1535 % w, 1535 // w
print("stamp target pixel:", wrow, wcol)
