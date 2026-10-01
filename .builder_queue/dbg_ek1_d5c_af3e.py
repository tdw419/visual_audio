#!/usr/bin/env python3
"""dbg_ek1_d5c_af3e.py — D5 v2: stage the payload at word 976 (the pixel PC
the rewritten vector actually lands on) and single-step the tail to observe
the trap->payload transition."""
import sys

sys.path.insert(0, ".")
from tools.glyph_isa_v2 import GlyphAssemblerV2, OpcodeMapV2, W_MEM  # noqa: E402
from tools.glyph_process import GlyphProcessTable  # noqa: E402

OM = OpcodeMapV2()
TILE = (5, 0, 8, 8)
OUT_WORD = 168
KFAULT_WORD = 8193
D5_TARGET = (30 << 16) | 4
D5_DEST = 30 * W_MEM + 16   # word 976 = pixel (16,30) = the trap target
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
prog = ["LDI r5 %d" % D5_TARGET, "LDI r1 %d" % KFAULT_WORD,
        "PARALLEL_ST r1 r5 1"] + staging(D5_DEST, payload)
img = GlyphAssemblerV2(OM).assemble(prog, width_instrs=8)
table = GlyphProcessTable()
pid = table.spawn(img, name="d5dbg2", tile=TILE)
cpu = table.tasks[pid]["cpu"]
rc = table.wait(pid)
print("rc:", rc, "prt:", bytes(v & 0xFF for v in cpu.output).hex())
print("kfault:", cpu.memory[KFAULT_WORD])
print("halt_reason:", cpu.halt_reason)
table.close()
OM.close()
