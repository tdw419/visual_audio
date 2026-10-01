#!/usr/bin/env python3
"""probe_pst_escalation_af3e.py — final escalation legs:

1. Can PARALLEL_ST arm BOX0_LO/HI to cover ALL of RAM (full fence takeover)?
   The BOX words live in the isolation MMIO block (words 8192+) — if
   PARALLEL_ST can write them, the task makes ITSELF omnipotent, no disarm
   needed (box covering everything = _addr_in_box always true = E-K1 never
   fires; ST remains the sanctioned-looking path).
2. Confirm cross-fence read via PARALLEL_LD from a neighbor tile word
   (read-side parity for completeness of the BK-38 family).
"""
import os
import sys

sys.path.insert(0, "/home/jericho/projects/zion/projects/visual_audio")

from tools.glyph_isa_v2 import (  # noqa: E402
    BOX0_HI_ADDR,
    BOX0_LO_ADDR,
    GlyphAssemblerV2,
    OpcodeMapV2,
)
from tools.glyph_process import EXIT_FAULT, EXIT_OK, GlyphProcessTable  # noqa: E402

OM = OpcodeMapV2()
BOX0_LO_WORD = BOX0_LO_ADDR >> 2
BOX0_HI_WORD = BOX0_HI_ADDR >> 2
IN_TILE_WORD = 5 * 32 + 0    # 160
OUT_TILE_WORD = 164
NEIGHBOR_WORD = 168          # row 5 col 8: a plausible neighbor-tile word
CANARY = 0x0BADF00D & 0xFFFFFF


def run_case(label, prog, seed):
    img = GlyphAssemblerV2(OM).assemble(prog, width_instrs=8)
    t = GlyphProcessTable()
    pid = t.spawn(img, name=label, tile=(5, 0, 2, 4))
    cpu = t.tasks[pid]["cpu"]
    for a, v in seed.items():
        cpu.memory[a] = v & 0xFFFFFFFF
    rc = t.wait(pid)
    return {
        "label": label,
        "rc": rc,
        "rc_name": "EXIT_OK" if rc == EXIT_OK else ("EXIT_FAULT" if rc == EXIT_FAULT else f"?{rc}"),
        "faulted": bool(cpu.faulted),
        "box0_lo_after": int(cpu.memory[BOX0_LO_WORD]),
        "box0_hi_after": int(cpu.memory[BOX0_HI_WORD]),
        "st_target_999": int(cpu.memory[999]),
    }


def main():
    out = []
    # Leg 1: arm BOX0 to cover all RAM via PARALLEL_ST, then ST to word 999
    prog = [
        "LDI r2 %d" % BOX0_LO_WORD,
        "LDI r3 0",
        "PARALLEL_ST r2 r3 1",          # BOX0_LO := 0
        "LDI r2 %d" % BOX0_HI_WORD,
        "LDI r3 65536",                 # BOX0_HI := 65536 (covers 16K words x4)
        "PARALLEL_ST r2 r3 1",
        "LDI r2 999",
        "LDI r3 4660",                  # 0x1234
        "ST r2 r3",                     # now inside the SELF-GRANTED box
        "HALT",
    ]
    out.append(repr(run_case("pst_self_grant_box", prog, {})))

    # Leg 2: PARALLEL_LD cross-fence read (read-side parity)
    prog2 = [
        "LDI r2 %d" % NEIGHBOR_WORD,
        "PARALLEL_LD r4 %d 1" % NEIGHBOR_WORD,  # rd=4, addr imm, count 1
        "HALT",
    ]
    img = GlyphAssemblerV2(OM).assemble(prog2, width_instrs=8)
    t = GlyphProcessTable()
    pid = t.spawn(img, name="pst_ld_cross", tile=(5, 0, 2, 4))
    cpu = t.tasks[pid]["cpu"]
    cpu.memory[NEIGHBOR_WORD] = CANARY
    rc = t.wait(pid)
    out.append(f"PARALLEL_LD cross-fence: rc={rc} faulted={cpu.faulted} "
               f"r4={cpu.registers[4]} (0x{cpu.registers[4]:08X}) canary=0x{CANARY:08X} "
               f"-> {'SILENT READ' if cpu.registers[4] == CANARY else 'no'}")

    with open("/tmp/pst_esc.txt", "w") as f:
        f.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
