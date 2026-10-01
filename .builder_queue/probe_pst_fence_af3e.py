#!/usr/bin/env python3
"""probe_pst_fence_af3e.py — Phase 1c research: is the item-29 tile fence
bypassable by WRITE arms other than ST?

Prior art (landed): BK-38 (LD reads unguarded); _addr_in_box consulted at
exactly ONE site — the USER store trap (glyph_isa_v2.py:1041). This probe
measures the OTHER guest-reachable write arms from a tiled USER task:

  A. PARALLEL_ST (glyph_isa_v2.py:1264-1295): writes self.memory[a] with a
     bounds check only (:1273) — no mode check, no _addr_in_box consult.
  B. PUSH (:1091-1093) / CALL (:1101-1105): write via _mem_write
     (:702-708) — image-pixel write-through, no box consult.

Harness = the landed item-29 containment path itself:
GlyphProcessTable.spawn(tile=(5,0,2,4)) with the auto-armed reaper.

Controls:
  st_cross_fence   — the E-K1 baseline: plain ST out-of-tile must trap.
  pst_in_tile      — PARALLEL_ST inside the tile must land (the opcode
                     itself works, the gap is the missing consult).
Determinism: 3 identical runs, diff.
"""
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from tools.glyph_containment import DEFAULT_REAPER_ROW, wrap_with_reaper  # noqa: E402,F401
from tools.glyph_isa_v2 import (  # noqa: E402
    GlyphAssemblerV2,
    MODE_SUPER,
    OpcodeMapV2,
    TILE_H_ADDR,
    W_MEM,
)
from tools.glyph_process import EXIT_FAULT, EXIT_OK, GlyphProcessTable  # noqa: E402

OM = OpcodeMapV2()
TILE_ROW, TILE_COL, TILE_H, TILE_W = 5, 0, 2, 4
IN_TILE_WORD = TILE_ROW * W_MEM + TILE_COL          # 160
OUT_TILE_WORD = IN_TILE_WORD + TILE_W               # 164 (first word outside)
TILE_H_WORD = TILE_H_ADDR >> 2                      # the fence's OWN config word
CANARY = 0x0BADF00D


def run_case(label, prog_lines, seed):
    img = GlyphAssemblerV2(OM).assemble(prog_lines, width_instrs=8)
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
        "out_word_value": int(cpu.memory[OUT_TILE_WORD]),
        "tile_h_word": int(cpu.memory[TILE_H_WORD]),
        "mode_super": int(cpu.mode) == MODE_SUPER,
    }


def main():
    # A: PARALLEL_ST — r2 = out-of-tile addr, r3 = canary source, count 1
    pst_out_prog = [
        "LDI r2 %d" % OUT_TILE_WORD,
        "LDI r3 %d" % (CANARY & 0xFFFFFF),
        "PARALLEL_ST r2 r3 1",
        "HALT",
    ]
    # B: PUSH — pre-decrement r31 to the out-of-tile word, push the canary
    push_out_prog = [
        "LDI r31 %d" % (OUT_TILE_WORD + 1),
        "LDI r3 %d" % (CANARY & 0xFFFFFF),
        "PUSH r3",
        "HALT",
    ]
    # Control: plain ST out-of-tile must trap (E-K1 baseline)
    st_out_prog = [
        "LDI r2 %d" % OUT_TILE_WORD,
        "LDI r3 %d" % (CANARY & 0xFFFF),
        "ST r2 r3",
        "HALT",
    ]
    # Control: PARALLEL_ST in-tile must land
    pst_in_prog = [
        "LDI r2 %d" % IN_TILE_WORD,
        "LDI r3 %d" % (CANARY & 0xFFFFFF),
        "PARALLEL_ST r2 r3 1",
        "HALT",
    ]

    # NOTE: no TILE_H seed here — arm_tile() runs inside spawn(); seeding the
    # tile config word post-spawn would DISARM the fence and invalidate the
    # control (first draft had this bug; caught on read-back).
    seed = {OUT_TILE_WORD: 0, IN_TILE_WORD: 0}
    results = []
    for _ in range(3):
        results.append([
            run_case("pst_cross_fence", pst_out_prog, seed),
            run_case("push_cross_fence", push_out_prog, seed),
            run_case("st_cross_fence_ctl", st_out_prog, seed),
            run_case("pst_in_tile_ctl", pst_in_prog, seed),
        ])
    for r4 in results:
        for r in r4:
            print(r)
    print("deterministic:", all(results[i] == results[0] for i in range(1, 3)))
    pst = results[0][0]
    push = results[0][1]
    st = results[0][2]
    print("VERDICT pst_cross_fence:",
          "SILENT CROSS-FENCE WRITE (canary landed out-of-tile, clean exit)"
          if (pst["rc_name"] == "EXIT_OK" and pst["out_word_value"] == (CANARY & 0xFFFFFF))
          else "trapped" if st["faulted"] or pst["faulted"] else "other")
    print("VERDICT push_cross_fence:",
          "SILENT CROSS-FENCE WRITE" if (push["rc_name"] == "EXIT_OK" and push["out_word_value"] == (CANARY & 0xFFFFFF))
          else "trapped/other")
    print("VERDICT st_cross_fence_ctl:",
          "trapped as required" if st["faulted"] else "NOT TRAPPED (baseline broken)")
    print("VERDICT pst_in_tile_ctl:",
          "landed as required" if pst_in_lands(results) else "did NOT land (opcode broken)")


def pst_in_lands(results):
    r = results[0][3]
    return r["rc_name"] == "EXIT_OK" and r["out_word_value"] == 0 and r["faulted"] is False


if __name__ == "__main__":
    main()
