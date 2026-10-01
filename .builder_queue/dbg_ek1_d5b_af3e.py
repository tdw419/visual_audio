#!/usr/bin/env python3
"""dbg_ek1_d5b_af3e.py — pin the D5 trap-target arithmetic: unpack kf into
the pixel PC the E-K1 arm actually computes (glyph_isa_v2.py:1052-1056)."""
import sys

sys.path.insert(0, ".")
from tools.glyph_isa_v2 import INSTR_WIDTH, OpcodeMapV2  # noqa: E402

OM = OpcodeMapV2()
for kf in (1966080, 1966084):
    tx, ty = kf & 0xFFFF, (kf >> 16) & 0xFFFF
    target_x = tx * INSTR_WIDTH
    print("kf=%d -> col=%d row=%d -> pixel PC (x=%d, y=%d) -> word(target)="
          "%d" % (kf, tx, ty, target_x, ty, ty * 32 + target_x))
OM.close()
