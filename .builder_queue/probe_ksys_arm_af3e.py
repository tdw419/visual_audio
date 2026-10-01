#!/usr/bin/env python3
"""probe_ksys_arm_af3e.py — Phase 1c research (BK-41 candidate): the proposed
"cheap posture" for BK-40 (arm KSYS_PC by default on tiled spawns) stores its
own control word in guest-visible RAM (word 8194 = BOX_MMIO_BASE + 0x08 >> 2),
which BK-39 measured fence-blind to PARALLEL_ST. This probe measures whether
the E-K2 posture actually contains a tiled USER task or just relocates the
hole.

Harness = the landed item-29 containment path itself:
GlyphProcessTable.spawn(tile=(5,0,8,8)), auto reaper (row 30).
Tile = rows 5-12 x cols 0-7 (word grid, W_MEM=32). OUT word 168 = row 5 col 8
(first word outside). STAGE word 176 = row 5 col 16 (outside).

KSYS_PC packing: (row << 16) | col; engine unpacks ty = ksys >> 16,
tx = (ksys & 0xFFFF) * INSTR_WIDTH -> pixel (x, y) = (tx, ty). Gadget planted
at PIXEL row 6, x=0 -> packed (6 << 16) | 0 = 393216.

PROBE-DEFECT DISCLOSURE (draft 1, caught on read-back before any finding):
numpy img[6:8] = gadget on a 2-row image is a SILENT NO-OP (out-of-range
slice) — legs A/C/D jumped to black pixels and reported nothing. Draft 2
builds a tall canvas explicitly and asserts the gadget pixels are on-canvas
and non-black before evidence is taken.

Cases (3 runs each, stdout must be identical):
  A. ctl_ksys_dispatch — KSYS_PC armed to an in-tile gadget that plain-STs
     VALUE to STAGE (176) then HALTs; user program issues one syscall.
     Purpose: validate E-K2 dispatch mechanics (gadget runs in SUPER where
     the E-K1 ST fence is mode-gated off, glyph_isa_v2.py:1074).
  B. disarm_then_read — KSYS_PC armed, but the user program first
     PARALLEL_STs 0 to word 8194 (BK-39 fence-blind write), then issues
     0x02 READ with dest=STAGE, ring seeded 'K','F'. Predicted: ksys reads 0
     after the disarm, the DIRECT fence-blind handler runs, and 'KF' lands
     out-of-tile at 176 clean — the armed posture defeated by one instruction.
  C. self_arm — KSYS_PC == 0 at spawn (posture OFF); the user program
     PARALLEL_STs the gadget pointer (393216) into word 8194 itself, then
     issues a syscall. Predicted: E-K2 dispatch executes guest-chosen code in
     SUPER mode; its ST lands out-of-tile — the guest turns the posture ON
     FOR ITSELF and points it at its own tile.
  D. ctl_st_out — no posture, plain ST to 176: must TRAP (E-K1 baseline
     live; reaper catches; EXIT_FAULT). No bypass involved.
Controls never touch PARALLEL_ST or KSYS word (except the E-K1 baseline).
"""
import hashlib
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from tools.glyph_isa_v2 import (  # noqa: E402
    GlyphAssemblerV2,
    INPUT_DATA_ADDR,
    INPUT_LEN_ADDR,
    KSYS_PC_ADDR,
    MODE_SUPER,
    OpcodeMapV2,
    TILE_H_ADDR,
    W_MEM,
)
from tools.glyph_process import EXIT_FAULT, EXIT_OK, GlyphProcessTable  # noqa: E402

OM = OpcodeMapV2()
TILE_ROW, TILE_COL, TILE_H, TILE_W = 5, 0, 8, 8
STAGE_WORD = 176                                      # row 5, col 16 (outside)
KSYS_WORD = KSYS_PC_ADDR >> 2                         # 8194
GADGET_ROW = 6                                        # pixel row 6 (in tile)
GADGET_PACKED = (GADGET_ROW << 16) | 0                # 393216
VALUE = 0xC0FFEE
CANVAS_ROWS = 32


def build_image(user_lines, gadget_lines):
    """User program at pixel row 0, gadget at pixel row GADGET_ROW. Asserts
    the gadget pixels are actually on-canvas and non-black (draft-1 guard)."""
    img_user = GlyphAssemblerV2(OM).assemble(user_lines, width_instrs=8)
    img_gad = GlyphAssemblerV2(OM).assemble(gadget_lines, width_instrs=8)
    if img_user.shape[0] > GADGET_ROW:
        raise SystemExit("user program overlaps gadget row")
    canvas = np.zeros((CANVAS_ROWS, 32, 3), dtype=np.uint8)
    canvas[0:img_user.shape[0]] = img_user
    canvas[GADGET_ROW:GADGET_ROW + img_gad.shape[0]] = img_gad
    # draft-1 guard: the dispatch target pixel must be lit
    px = tuple(int(v) for v in canvas[GADGET_ROW, 0])
    if px == (0, 0, 0):
        raise SystemExit(f"gadget dispatch pixel (0,{GADGET_ROW}) is black")
    return canvas


def run_case(label, image, ksys_word_val=None, seed_ring=None):
    table = GlyphProcessTable()
    pid = table.spawn(image, name=label,
                      tile=(TILE_ROW, TILE_COL, TILE_H, TILE_W))
    cpu = table.tasks[pid]["cpu"]
    if ksys_word_val is not None:
        cpu.memory[KSYS_WORD] = ksys_word_val & 0xFFFFFFFF
    if seed_ring:
        data, length = seed_ring
        for i, b in enumerate(data):
            cpu.memory[(INPUT_DATA_ADDR >> 2) + i] = b
        cpu.memory[INPUT_LEN_ADDR >> 2] = length
    rc = table.wait(pid)
    st = int(cpu.memory[STAGE_WORD])
    return {
        "label": label,
        "rc_name": "EXIT_OK" if rc == EXIT_OK else ("EXIT_FAULT" if rc == EXIT_FAULT else f"?{rc}"),
        "faulted": bool(cpu.faulted),
        "mode_super": int(cpu.mode) == MODE_SUPER,
        "stage176_hex": f"0x{st:06X}",
        "stage176_word177": f"0x{int(cpu.memory[STAGE_WORD + 1]):06X}",
        "ksys_after": int(cpu.memory[KSYS_WORD]),
        "tile_h_after": int(cpu.memory[TILE_H_ADDR >> 2]),
    }


def main():
    GADGET = ["LDI r2 %d" % STAGE_WORD, "LDI r3 %d" % VALUE,
              "ST r2 r3", "HALT"]
    SYSCALLER = ["LDI r17 2", "SYSCALL r10 2", "HALT"]
    DISARM = ["LDI r2 %d" % KSYS_WORD, "LDI r3 0", "PARALLEL_ST r2 r3 1"]
    SELFARM = ["LDI r2 %d" % KSYS_WORD,
               "LDI r3 %d" % GADGET_PACKED, "PARALLEL_ST r2 r3 1"]

    img_A = build_image(SYSCALLER, GADGET)
    img_B = build_image(DISARM + ["LDI r1 %d" % STAGE_WORD, "LDI r2 2",
                                  "LDI r17 2", "SYSCALL r10 2", "HALT"], GADGET)
    img_C = build_image(SELFARM + SYSCALLER, GADGET)
    img_D = GlyphAssemblerV2(OM).assemble(
        ["LDI r2 %d" % STAGE_WORD, "LDI r3 %d" % VALUE, "ST r2 r3", "HALT"],
        width_instrs=8)

    runs = []
    for _ in range(3):
        runs.append([
            run_case("ctl_ksys_dispatch", img_A, ksys_word_val=GADGET_PACKED),
            run_case("disarm_then_read", img_B, ksys_word_val=GADGET_PACKED,
                     seed_ring=(b"KF", 2)),
            run_case("self_arm", img_C),
            run_case("ctl_st_out", img_D),
        ])

    blob = "\n".join(str(r) for run in runs for r in run)
    ident = all(str(runs[0][i]) == str(runs[k][i])
                for k in range(3) for i in range(4))
    print("determinism md5 (3 runs x 4 cases):",
          hashlib.md5(blob.encode()).hexdigest())
    print("3-run identical:", ident)
    for r in runs[0]:
        print(r)

    with open("/tmp/ksys_probe.txt", "w") as f:
        f.write(blob + "\n")


if __name__ == "__main__":
    main()
