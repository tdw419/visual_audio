#!/usr/bin/env python3
"""dbg_ek1_decode_af3e.py — decode helper for the E-K1 hijack probe: what the
assembler really emits for the payloads, and where each leg's trap landed."""
import sys

sys.path.insert(0, ".")
from tools.glyph_isa_v2 import GlyphAssemblerV2, OpcodeMapV2  # noqa: E402

OM = OpcodeMapV2()


def words_of(lines):
    img = GlyphAssemblerV2(OM).assemble(lines, width_instrs=8)
    h, w, _ = img.shape
    return [int(img[y, x, 0]) << 16 | int(img[y, x, 1]) << 8 | int(img[y, x, 2])
            for y in range(h) for x in range(w)]


prt = words_of(["PRT r6", "HALT"])
print("PRT r6/HALT payload words:", [hex(v) for v in prt if v])
print("  -> prt byte observed '34' = 0x34 = 52 = canary 4660 & 0xFF:",
      hex(4660 & 0xFF))

d3 = words_of(["LDI r2 164", "LD r6 r2", "LDI r3 11399181", "ST r2 r3", "HALT"])
print("D3 payload words:", [hex(v) for v in d3 if v])
print("D3 observed tramp:", hex(15487056), hex(16776962))
print("  15487056 decode:", (15487056 >> 16, (15487056 >> 8) & 0xFF, 15487056 & 0xFF))
print("  16776962 decode:", (16776962 >> 16, (16776962 >> 8) & 0xFF, 16776962 & 0xFF))

print("D5_TARGET (30<<16)|4 =", (30 << 16) | 4, hex((30 << 16) | 4))
print("observed D5 kfault_word = 1966084 =", hex(1966084),
      "-> row", 1966084 >> 16, "col", 1966084 & 0xFFFF)
print("D5 halt pixel word 976 = (col", 976 % 32, ",row", 976 // 32, ")")
OM.close()
