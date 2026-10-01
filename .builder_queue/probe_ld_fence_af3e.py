#!/usr/bin/env python3
"""probe_ld_fence_af3e.py — measure the item-29 carried note: "LD not box-checked".

Question: can a USER-mode task confined to tile (row,col,h,w) READ words
outside its tile via unpaged LD (PAGE_TABLE_ADDR == 0)?

Method (landed modules only, no tree mutation):
  1. Build a tiny program image: seed a canary word at an OUT-of-tile RAM
     address (via SUPER-mode STs emitted as host-side memory writes BEFORE
     execution — identical to how the item-29 gate seeds neighbor RAM),
     then in USER mode: LD the out-of-tile canary, ST it to an in-tile
     word, HALT.
  2. Run through GlyphProcessTable.spawn(tile=...) — the exact item-29
     containment harness (reaper auto-armed).
  3. Observe: does the LD fault (E-K1-style) or does the out-of-tile
     value land in the tile (silent cross-fence read)?
  4. Control: identical program with the LD source IN tile -> lands.
  5. ST control: same shape program with ST out-of-tile -> traps (B3
     re-proves the asymmetry baseline on this exact tree/HEAD).
Determinism: 3 identical runs, diff.
"""
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from tools.glyph_containment import DEFAULT_REAPER_ROW, wrap_with_reaper  # noqa: E402
from tools.glyph_isa_v2 import (  # noqa: E402
    FAULT_ADDR_ADDR,
    FAULT_PC_ADDR,
    GlyphAssemblerV2,
    MODE_SUPER,
    OpcodeMapV2,
    TILE_H_ADDR,
    TILE_ROW_ADDR,
    W_MEM,
)
from tools.glyph_process import EXIT_FAULT, EXIT_OK, GlyphProcessTable  # noqa: E402

OM = OpcodeMapV2()
TILE_ROW, TILE_COL, TILE_H, TILE_W = 5, 0, 2, 4
IN_TILE_WORD = TILE_ROW * W_MEM + TILE_COL        # 160
OUT_TILE_WORD = IN_TILE_WORD + TILE_W             # 164 (first word outside)
CANARY = 0x0BADF00D


def build_image(prog_lines):
    asm = GlyphAssemblerV2(OM)
    return asm.assemble(prog_lines, width_instrs=8)


def run_case(label, prog_lines, seed):
    img = build_image(prog_lines)
    table = GlyphProcessTable()
    pid = table.spawn(img, name=label, tile=(TILE_ROW, TILE_COL, TILE_H, TILE_W))
    cpu = table.tasks[pid]["cpu"]
    for addr, val in seed.items():
        cpu.memory[addr] = val & 0xFFFFFFFF
    rc = table.wait(pid)
    return {
        "label": label,
        "rc": rc,
        "rc_name": "EXIT_OK" if rc == EXIT_OK else ("EXIT_FAULT" if rc == EXIT_FAULT else f"?{rc}"),
        "faulted": bool(cpu.faulted),
        "fault_addr": int(getattr(cpu, "fault_addr", 0) or 0),
        "in_tile_word": int(cpu.memory[IN_TILE_WORD]),
        "mode_after": int(cpu.mode),
        "mode_super": int(cpu.mode) == MODE_SUPER,
    }


def main():
    # LD source register = r2 holds the absolute word address.
    ld_prog = [
        "LDI r2 %d" % OUT_TILE_WORD,
        "LD r3 r2",                    # read the OUT-of-tile canary
        "LDI r2 %d" % IN_TILE_WORD,
        "ST r2 r3",                    # land it in-tile
        "HALT",
    ]
    st_prog = [                        # control: store OUT of tile must trap
        "LDI r2 %d" % IN_TILE_WORD,
        "LDI r3 %d" % (CANARY & 0xFFFF),
        "LDI r2 %d" % OUT_TILE_WORD,
        "ST r2 r3",
        "HALT",
    ]
    in_tile_prog = [                   # control: LD from IN tile must land
        "LDI r2 %d" % IN_TILE_WORD,
        "LD r3 r2",
        "LDI r2 %d" % (IN_TILE_WORD + 1),
        "ST r2 r3",
        "HALT",
    ]

    seed = {OUT_TILE_WORD: CANARY, IN_TILE_WORD: 0x0}
    results = []
    for run in range(3):
        results.append([
            run_case("ld_cross_fence", ld_prog, seed),
            run_case("st_cross_fence", st_prog, seed),
            run_case("ld_in_tile", in_tile_prog, seed),
        ])
    for r3 in results:
        for r in r3:
            print(r)
    print("deterministic:", all(results[i] == results[0] for i in range(1, 3)))
    ld = results[0][0]
    print("VERDICT ld_cross_fence:",
          "SILENT CROSS-FENCE READ (value landed)" if
          (ld["rc_name"] == "EXIT_OK" and ld["in_tile_word"] == CANARY)
          else "fenced/trapped" if ld["faulted"] else "other")


if __name__ == "__main__":
    main()
