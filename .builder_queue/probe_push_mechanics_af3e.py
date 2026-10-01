#!/usr/bin/env python3
"""probe_push_mechanics_af3e.py — leg 2: PUSH/POP address the IMAGE plane
(_mem_write -> _addr_to_xy, scanline), not the Word-RAM. Verify a tiled
USER task's PUSH lands out-of-tile in the image with no box consult."""
import os
import sys

import numpy as np

REPO = "/home/jericho/projects/zion/projects/visual_audio"
sys.path.insert(0, REPO)

from tools.glyph_isa_v2 import GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2  # noqa: E402
from tools.glyph_process import GlyphProcessTable  # noqa: E402

out = []
OM = OpcodeMapV2()
TILE_ROW, TILE_COL, TILE_H, TILE_W = 5, 0, 2, 4

# Program: r31=165, push canary (0x0BADF00D masked to 24-bit image pixel 0x0BADF0),
# then LOAD BACK via POP to prove the image-plane round trip, PRT it, HALT.
prog = [
    "LDI r31 165",
    "LDI r3 7602272",   # 0x740C00 ... use simple value 0x0BADF0 = 7602192? use 12345
    "LDI r3 12345",
    "PUSH r3",
    "POP r4",
    "PRT r4",
    "HALT",
]
img = GlyphAssemblerV2(OM).assemble(prog, width_instrs=8)
out.append(f"assembled shape: {img.shape}")

table = GlyphProcessTable()
pid = table.spawn(img, name="push_img", tile=(TILE_ROW, TILE_COL, TILE_H, TILE_W))
task = table.tasks[pid]
cpu = task["cpu"]
out.append(f"spawned image shape (reaper-tall copy): {task['image'].shape}")

rc = table.wait(pid)
im = task["image"]
# PUSH addr = r31 after decrement = 164. _addr_to_xy: width = im.shape[1]
w = im.shape[1]
x, y = 164 % w, 164 // w
out.append(f"rc={rc} faulted={cpu.faulted} mode={cpu.mode}")
out.append(f"PRT output (POP round-trip): {cpu.output}")
out.append(f"image pixel at PUSH target (x={x},y={y}): {tuple(int(c) for c in im[y, x])}")
out.append(f"expected (12345 = 0x003039): (0x00, 0x30, 0x39)")
out.append(f"word-RAM mem[164]: {cpu.memory[164]} (image-plane write, RAM untouched)")
# is (col=4, row=5) inside the tile? tile cols 0..3 -> NO: first col outside = 4
out.append(f"tile covers cols 0..3 rows 5..6; target col=4 row=5 -> OUTSIDE tile: {(TILE_COL <= 4 < TILE_COL + TILE_W) and (TILE_ROW <= 5 < TILE_ROW + TILE_H)}")

with open("/tmp/push_mech4.txt", "w") as f:
    f.write("\n".join(out) + "\n")
