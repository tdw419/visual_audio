#!/usr/bin/env python3
"""dbg_ek1_d5_af3e.py — trace the D5 leg's staging and trap: which words got
written where, and what the engine executed after vectoring to (30,4)."""
import sys

sys.path.insert(0, ".")
from tools.glyph_isa_v2 import (  # noqa: E402
    GlyphAssemblerV2, MODE_SUPER, OpcodeMapV2, W_MEM)
from tools.glyph_process import GlyphProcessTable  # noqa: E402

OM = OpcodeMapV2()
TILE = (5, 0, 8, 8)
OUT_WORD = 168
KFAULT_WORD = 8193
D5_TARGET = (30 << 16) | 4
CANARY = 4660


def payload_words(lines):
    img = GlyphAssemblerV2(OM).assemble(lines, width_instrs=8)
    h, w, _ = img.shape
    return [int(img[y, x, 0]) << 16 | int(img[y, x, 1]) << 8 | int(img[y, x, 2])
            for y in range(h) for x in range(w)]


def staging(dest, words, canary_reg=6):
    lines = []
    base = 5
    for off in range(0, len(words), 4):
        chunk = words[off:off + 4]
        for i, wv in enumerate(chunk):
            lines.append("LDI r%d %d" % (base + i, wv))
        lines.append("LDI r1 %d" % (dest + off))
        lines.append("PARALLEL_ST r1 r5 %d" % len(chunk))
    lines += [
        "LDI r%d %d" % (canary_reg, CANARY),
        "LDI r2 %d" % OUT_WORD,
        "LDI r3 %d" % CANARY,
        "ST r2 r3",
        "HALT",
    ]
    return lines


payload = payload_words(["PRT r6", "HALT"])[:8]
print("payload[:8]:", [hex(v) for v in payload])
D5_DEST = 4 * W_MEM + 4 * 4   # word 144? or pixel-space?
print("D5 staging dest word:", D5_DEST, "-> pixel(x,y):",
      (D5_DEST % 32, D5_DEST // 32))

prog = ["LDI r5 %d" % D5_TARGET, "LDI r1 %d" % KFAULT_WORD,
        "PARALLEL_ST r1 r5 1"] + staging(D5_DEST, payload)
img = GlyphAssemblerV2(OM).assemble(prog, width_instrs=8)
table = GlyphProcessTable()
pid = table.spawn(img, name="d5dbg", tile=TILE)
cpu = table.tasks[pid]["cpu"]
task_img = table.tasks[pid]["image"]
rc = table.wait(pid)
h, w, _ = task_img.shape
print("rc:", rc, "prt:", bytes(v & 0xFF for v in cpu.output))
print("kfault:", cpu.memory[KFAULT_WORD], "expected:", D5_TARGET)
# dump pixels around the staged area: words 140..150 -> (x,y)
for a in range(140, 152):
    x, y = a % w, a // w
    px = task_img[y, x]
    v = int(px[0]) << 16 | int(px[1]) << 8 | int(px[2])
    if v:
        print("word %d pixel(%d,%d): %06x" % (a, x, y, v))
# where did PC walk? instrument: single-step manually
print("halt_reason:", cpu.halt_reason)
table.close()
OM.close()
