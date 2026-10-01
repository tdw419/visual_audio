#!/usr/bin/env python3
"""probe_pst_disarm_af3e.py — escalation leg: from inside its tile, can a
tiled USER task use PARALLEL_ST to rewrite the fence's OWN config words
(TILE_ROW/COL/H/W at words 8280..8283), disarm the fence, then ST anywhere?

Also: once disarmed, does the E-K1 ST check read TILE_H live (i.e. does the
whole box model collapse, or does only the ARMING snapshot matter)?
"""
import os
import sys

sys.path.insert(0, "/home/jericho/projects/zion/projects/visual_audio")

from tools.glyph_isa_v2 import (  # noqa: E402
    GlyphAssemblerV2,
    OpcodeMapV2,
    TILE_H_ADDR,
    TILE_ROW_ADDR,
)
from tools.glyph_process import GlyphProcessTable  # noqa: E402

OM = OpcodeMapV2()
TILE_H_WORD = TILE_H_ADDR >> 2
TILE_ROW_WORD = TILE_ROW_ADDR >> 2


def run_case(label, prog, target_word):
    img = GlyphAssemblerV2(OM).assemble(prog, width_instrs=8)
    t = GlyphProcessTable()
    pid = t.spawn(img, name=label, tile=(5, 0, 2, 4))
    cpu = t.tasks[pid]["cpu"]
    rc = t.wait(pid)
    return {
        "label": label,
        "rc": rc,
        "faulted": bool(cpu.faulted),
        "fault_addr": int(getattr(cpu, "fault_addr", 0) or 0),
        "mode_super": cpu.mode == 0,
        "tile_h_after": int(cpu.memory[TILE_H_WORD]),
        "tile_row_after": int(cpu.memory[TILE_ROW_WORD]),
        f"mem[{target_word}]": int(cpu.memory[target_word]),
    }


def main():
    out = []
    cases = []

    # Case A: disarm TILE_H via PARALLEL_ST, then ST far outside (word 999)
    cases.append(run_case("pst_disarm_then_st", [
        "LDI r2 %d" % TILE_H_WORD,
        "LDI r3 0",
        "PARALLEL_ST r2 r3 1",     # TILE_H := 0 (fence disarmed)
        "LDI r2 999",
        "LDI r3 4660",             # 0x1234
        "ST r2 r3",                # does the live TILE_H==0 disable the trap?
        "HALT",
    ], 999))

    # Case B: same disarm, then ST into ANOTHER task's tile region
    # (tile (5,0,2,4) belongs to this task; word 160+8=168 row5 col8 is a
    # plausible neighbor-tile word) — same mechanics, different optics.
    cases.append(run_case("pst_disarm_then_st_neighbor", [
        "LDI r2 %d" % TILE_H_WORD,
        "LDI r3 0",
        "PARALLEL_ST r2 r3 1",
        "LDI r2 168",
        "LDI r3 4660",
        "ST r2 r3",
        "HALT",
    ], 168))

    # Case C: move the fence ONTO the target instead of disarming
    # (TILE_ROW := 0 via PARALLEL_ST makes words 0..(0+2)*32) legal)
    cases.append(run_case("pst_refence_then_st", [
        "LDI r2 %d" % TILE_ROW_WORD,
        "LDI r3 0",
        "PARALLEL_ST r2 r3 1",     # TILE_ROW := 0 -> tile now rows 0..1
        "LDI r2 40",               # word 40 = row 1 col 8: inside NEW tile
        "LDI r3 4660",
        "ST r2 r3",
        "HALT",
    ], 40))

    for r in cases:
        out.append(repr(r))
    with open("/tmp/pst_disarm.txt", "w") as f:
        f.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
