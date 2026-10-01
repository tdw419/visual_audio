#!/usr/bin/env python3
"""Self-text dispatcher probe, CORRECTED layout: place the handler at a
known word by checking the baker's actual layout first, then arm ksys to
the handler's real (row, col).

Layout discovery: bake the handler-only snippet and find which (x,y) holds
its first instruction word (real ST color from OpcodeMapV2).
"""
import sys
from pathlib import Path

HERE = Path('/home/jericho/projects/zion/projects/visual_audio')
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tools"))

import numpy as np  # noqa: E402
from tools.glyph_process import GlyphProcessTable  # noqa: E402
from tools.glyph_gpt.baker import bake_image  # noqa: E402
from tools.glyph_isa_v2 import OpcodeMapV2, GlyphAssemblerV2  # noqa: E402

om = OpcodeMapV2()
ST_COLOR = om.opcode_to_rgb('ST')


def img_word(img, word):
    h, w, _ = img.shape
    idx = word % (h * w)
    px = img[idx // w, idx % w]
    return (int(px[0]) << 16) | (int(px[1]) << 8) | int(px[2])


# 1) layout discovery: where does the baker put instruction N?
text = (
    ":__entry\n"
    "SYSCALL r10 6\n"     # instr 0
    "LDI r3 99\n"         # instr 1 (post)
    "HALT\n"              # instr 2
    "LDI r6 1\n"          # instr 3 (handler start — want its coords)
    "LDI r7 8194\n"       # instr 4
    "ST r7 r6\n"          # instr 5  <- the :968 window store
    "LDI r5 52\n"         # instr 6
    "PRT r6\n"            # instr 7
    "SYSRET\n"            # instr 8
)
img = bake_image(text, cols_instrs=8, min_rows=64, out_path=None)
h, w, _ = img.shape
print('image', img.shape)
for i in range(10):
    x = (i % 8) * 4
    y = i // 8
    print('instr', i, 'pixel', (x, y), 'word', y * 32 + x // 4 * 1 * 0 + (y * w + x) // 3 if False else '', hex(img_word(img, (y * w + x) // 3)))
# word index: image is HxWx3; word k = pixel index k in scanline order (w=32 => 32 px/row = 8 instrs/row)
for i in range(10):
    x = (i % 8) * 4
    y = i // 8
    word = (y * w + x) // 3
    print('instr %d -> pixel (%d,%d) scanline word %d val %s' % (
        i, x, y, word, hex(img_word(img, word))))
