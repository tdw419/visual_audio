#!/usr/bin/env python3
"""probe_syscall_fence_af3e.py — Phase 1c research (BK-40 candidate): are the
SYSCALL write arms (0x02 READ, 0x04 FILE_READ, 0x13 FILE_LIST, 0x11
STORE_CODE) guest-reachable write paths that bypass the item-29 tile fence?

Prior art (landed, this lane): BK-38 (LD unguarded), BK-39 (PARALLEL_LD/ST +
PUSH/CALL unguarded; BOX0 self-grant). This probe measures the syscall
layer — the remaining guest-reachable write class not yet probed.

Harness = the landed item-29 containment path itself:
GlyphProcessTable.spawn(tile=(5,0,8,8)) (words 160..223), auto reaper.
OUT word 224 = first word outside the tile.

PROBE-DESIGN DISCLOSURE (caught on read-back, two drafts):
  Draft 1 staged path bytes at word 300 via PARALLEL_ST — but PARALLEL_ST's
  write-through pixel mirror (glyph_isa_v2.py:1292-1295) wrote image pixel
  300 = instruction 75, corrupting the probe's own instruction stream mid-
  run (FILE_READ/STORE_CODE silently never executed). Draft 2's in-tile
  controls reported 'landed' from a truthiness bug ('\x00\x00'.strip() is
  truthy). Fixed before any finding was recorded: staging moved to word 160
  (mirror -> pixel 160 = instruction 40, past this <=30-instruction
  program), controls asserted on hex != '0000'.

Cases (all USER, tile armed, out-of-tile dest unless marked ctl):
  A. syscall 0x02 READ (ring seeded 'K','F'), dest=224
  B. syscall 0x04 FILE_READ '/tmp/b40' (b'KFENCE'), dest=224
  C. syscall 0x13 FILE_LIST '/tmp', dest=224
  D. syscall 0x11 STORE_CODE image-pixel 200 -> 224 (image-plane class;
     verdict measured on image pixels, not RAM words)
Controls:
  ctl_st_out  — plain ST to 224 must trap (E-K1 baseline; fault_addr=896).
  ctl_read_in — 0x02 READ dest=160 must land ('K').
  ctl_fr_in   — 0x04 FILE_READ dest=160 must land ('K').

Determinism: 3 identical runs, diff.
"""
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from tools.glyph_isa_v2 import (  # noqa: E402
    GlyphAssemblerV2,
    INPUT_DATA_ADDR,
    INPUT_LEN_ADDR,
    MODE_SUPER,
    OpcodeMapV2,
    TILE_H_ADDR,
    W_MEM,
)
from tools.glyph_process import EXIT_FAULT, EXIT_OK, GlyphProcessTable  # noqa: E402

OM = OpcodeMapV2()
TILE_ROW, TILE_COL, TILE_H, TILE_W = 5, 0, 8, 8
IN_TILE_WORD = TILE_ROW * W_MEM + TILE_COL          # 160
OUT_TILE_WORD = IN_TILE_WORD + TILE_W               # 168 (row 5, col 8: first
#   word OUTSIDE the tile — tile words are rows 5-12 x cols 0-7, NOT the
#   contiguous 160..223 block; first draft used 160+64=224 which is row 7
#   col 0 = INSIDE, and the ST control correctly landed there, exposing the
#   geometry error on read-back)
FR_IN_DEST = IN_TILE_WORD + 16                      # 176, ctl_fr_in dest
TILE_H_WORD = TILE_H_ADDR >> 2
FIXTURE = "/tmp/b40"
FIXTURE_BYTES = b"KFENCE"
ALLOW_ROOT = "/tmp"


def run_case(label, prog_lines, seed, image_seed=None):
    img = GlyphAssemblerV2(OM).assemble(prog_lines, width_instrs=8)
    table = GlyphProcessTable()
    pid = table.spawn(img, name=label, tile=(TILE_ROW, TILE_COL, TILE_H, TILE_W))
    cpu = table.tasks[pid]["cpu"]
    task_img = table.tasks[pid]["image"]
    ih, iw, _ = task_img.shape
    if image_seed:
        for pix, val in image_seed.items():
            task_img[pix // iw, pix % iw] = (
                (val >> 16) & 0xFF, (val >> 8) & 0xFF, val & 0xFF)
    pre_out_pix = tuple(int(v) for v in task_img[OUT_TILE_WORD // iw,
                                                 OUT_TILE_WORD % iw])
    # Seed the kernel input ring (0x02 READ source) with 2 bytes.
    cpu.memory[INPUT_DATA_ADDR >> 2] = ord("K")
    cpu.memory[(INPUT_DATA_ADDR >> 2) + 1] = ord("F")
    cpu.memory[INPUT_LEN_ADDR >> 2] = 2
    for addr, val in seed.items():
        cpu.memory[addr] = val & 0xFFFFFFFF
    rc = table.wait(pid)
    out = int(cpu.memory[OUT_TILE_WORD])
    inb = int(cpu.memory[IN_TILE_WORD])
    post_out_pix = tuple(int(v) for v in task_img[OUT_TILE_WORD // iw,
                                                  OUT_TILE_WORD % iw])
    def _hex(w):
        return bytes([w & 0xFF, (w >> 8) & 0xFF]).hex()
    return {
        "label": label,
        "rc": rc,
        "rc_name": "EXIT_OK" if rc == EXIT_OK else ("EXIT_FAULT" if rc == EXIT_FAULT else f"?{rc}"),
        "faulted": bool(cpu.faulted),
        "fault_addr": int(getattr(cpu, "fault_addr", 0) or 0),
        "out_hex": _hex(out),
        "in_hex": _hex(inb),
        "out_pix": post_out_pix,
        "out_pix_changed": post_out_pix != pre_out_pix,
        "tile_h_word": int(cpu.memory[TILE_H_WORD]),
        "mode_super": int(cpu.mode) == MODE_SUPER,
    }


def stage_path(path_bytes, sysnum, dest):
    """Stage path at word 160 (in-tile; mirror hits pixel 160 = instruction
    40, past this program's <=30 instructions), then issue the syscall with
    r1=path_addr, r2=dest, r3=max_len."""
    lines = []
    for i, b in enumerate(path_bytes):
        lines.append("LDI r5 %d" % (160 + i))
        lines.append("LDI r6 %d" % b)
        lines.append("PARALLEL_ST r5 r6 1")
    lines += [
        "LDI r1 160",
        "LDI r2 %d" % dest,
        "LDI r3 64",
        "LDI r17 %d" % sysnum,
        "SYSCALL r10 %d" % sysnum,
        "HALT",
    ]
    return lines


def prog_read(dest):
    # 0x02 READ: handler reads r1=addr, r2=want (glyph_isa_v2.py:1440-1441).
    return [
        "LDI r1 %d" % dest,
        "LDI r2 2",
        "LDI r17 2",
        "SYSCALL r10 2",
        "HALT",
    ]


def prog_store_code(dst, src):
    # 0x11 STORE_CODE: r1=dst, r2=src, r3=len (image-pixel words).
    return [
        "LDI r1 %d" % dst,
        "LDI r2 %d" % src,
        "LDI r3 1",
        "LDI r17 17",
        "SYSCALL r10 17",
        "HALT",
    ]


def main():
    with open(FIXTURE, "wb") as f:
        f.write(FIXTURE_BYTES)

    cases = [
        ("read_out", prog_read(OUT_TILE_WORD), {OUT_TILE_WORD: 0}, None),
        ("file_read_out", stage_path(FIXTURE.encode(), 4, OUT_TILE_WORD),
         {OUT_TILE_WORD: 0}, None),
        ("file_list_out", stage_path(b"/tmp", 19, OUT_TILE_WORD),
         {OUT_TILE_WORD: 0}, None),
        ("store_code_out", prog_store_code(OUT_TILE_WORD, 200),
         {}, {200: 0x414243}),
        ("ctl_st_out", [
            "LDI r2 %d" % OUT_TILE_WORD,
            "LDI r3 4660",
            "ST r2 r3",
            "HALT",
        ], {OUT_TILE_WORD: 0}, None),
        ("ctl_read_in", prog_read(IN_TILE_WORD), {IN_TILE_WORD: 0}, None),
        ("ctl_fr_in", stage_path(FIXTURE.encode(), 4, FR_IN_DEST),
         {FR_IN_DEST: 0}, None),
    ]

    results = []
    for _ in range(3):
        results.append([run_case(lbl, prog, seed, iseed) for lbl, prog, seed, iseed in cases])
    for r4 in results:
        for r in r4:
            print(r)
    print("deterministic:", all(results[i] == results[0] for i in range(1, 3)))

    r0 = {r["label"]: r for r in results[0]}
    for lbl in ("read_out", "file_read_out", "file_list_out"):
        r = r0[lbl]
        landed = (r["rc_name"] == "EXIT_OK") and (r["out_hex"] != "0000")
        print(f"VERDICT {lbl}:", "SILENT CROSS-FENCE WRITE (clean exit, dest word non-zero out-of-tile)"
              if landed else f"not landed (rc={r['rc_name']}, out={r['out_hex']})")
    r = r0["store_code_out"]
    print("VERDICT store_code_out:",
          "SILENT IMAGE-PLANE WRITE (clean exit, out-of-tile pixel changed)"
          if (r["rc_name"] == "EXIT_OK" and r["out_pix_changed"])
          else f"not landed (rc={r['rc_name']}, out_pix={r['out_pix']})")
    st = r0["ctl_st_out"]
    print("VERDICT ctl_st_out:", "trapped as required"
          if st["faulted"] and st["fault_addr"] == OUT_TILE_WORD * 4
          else f"NOT TRAPPED (rc={st['rc_name']}, fault_addr={st['fault_addr']})")
    ri = r0["ctl_read_in"]
    print("VERDICT ctl_read_in:", "landed in-tile as required"
          if ri["rc_name"] == "EXIT_OK" and ri["in_hex"] == "4b00"
          else f"did NOT land (rc={ri['rc_name']}, in_hex={ri['in_hex']})")
    fi = r0["ctl_fr_in"]
    print("VERDICT ctl_fr_in:", "landed in-tile as required"
          if fi["rc_name"] == "EXIT_OK" and fi["in_hex"] != "0000" and not fi["faulted"]
          else f"did NOT land (rc={fi['rc_name']}, in_hex={fi['in_hex']})")


if __name__ == "__main__":
    main()
