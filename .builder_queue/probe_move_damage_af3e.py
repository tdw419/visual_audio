"""R-research probe (af3e62239ce2, 2026-09-26 ~23:xx CDT): quantify the
item-38 C4 open candidate — move() is word-anchored, so a DRAGGED reaped
window composites its RAM at the NEW grid addresses. Measure, on one
tree (HEAD dd3cdd26), exactly which cells go black after a move, for
(a) a window that painted only its origin word, and (b) a window whose
guest painted its WHOLE tile from inside the fence (the item-37 idiom),
to see whether the candidate is an edge case or a product defect.

No engine/compositor file is modified; probe imports the landed modules
only. Structural asserts; no rate claims (rule-1 floors do not attach).
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import numpy as np  # noqa: E402

from tools.glyph_compositor import GlyphCompositor  # noqa: E402
from tools.glyph_isa_v2 import (  # noqa: E402
    MODE_USER,
    TILE_COL_ADDR,
    TILE_ROW_ADDR,
    W_MEM,
    GlyphAssemblerV2,
    OpcodeMapV2,
)


def _prog(lines):
    om = OpcodeMapV2()
    img = GlyphAssemblerV2(om).assemble(lines, width_instrs=8)
    om.close()
    return img


def _painter(word_addr, color):
    return _prog([
        f"LDI r5 {color}",
        f"LDI r6 {word_addr}",
        "ST r6 r5",
        "LDI r1 0",
        "SYSCALL r0 0x05",
        "HALT",
    ])


def _fill_tile(color):
    """USER guest paints every cell of its OWN tile by LDing TILE_ROW/
    TILE_COL from MMIO and walking h*w words from its origin (3x5=15
    stores, all inside its fence)."""
    return _prog([
        f"LDI r20 {TILE_ROW_ADDR >> 2}",
        "LD r10 r20",
        f"LDI r21 {TILE_COL_ADDR >> 2}",
        "LD r11 r21",
        f"LDI r12 {W_MEM}",
        "MUL r10 r12",
        "ADD r10 r11",       # r10 = origin word
        f"LDI r5 {color}",
        "LDI r13 0",         # r = 0
        "LDI r19 3",         # h = 3
        "LDI r22 5",         # w = 5
        "LDI r18 0",
        "LDI r15 1",
        "LDI r12 32",        # W_MEM (reuse; r12 was scratch after origin calc)
        ":r_loop",
        "LDI r14 0",         # c = 0
        ":c_loop",
        "LDI r17 0",
        "ADD r17 r13",       # r17 = r          (2-op: r17 += r13)
        "MUL r17 r12",       # r17 = r*32
        "ADD r17 r10",       #      + origin
        "ADD r17 r14",       #      + c  -> inside the 3x5 tile
        "ST r17 r5",
        "ADD r14 r15",       # c += 1
        "CMP r14 r22",
        "JNZ :c_loop",       # while c != 5 (JNZ jumps on flag CLEAR)
        "ADD r13 r15",       # r += 1
        "CMP r13 r19",
        "JNZ :r_loop",       # while r != 3
        "LDI r1 0",
        "SYSCALL r0 0x05",
        "HALT",
    ])


def _rgb(word):
    return ((word >> 16) & 0xFF, (word >> 8) & 0xFF, word & 0xFF)


RED = 0xFF0000

# ── (a) origin-painter, moved (the C4 case) ──────────────────────────────
print("=== (a) origin-only painter, moved ===")
comp = GlyphCompositor()
rect = (10, 0, 3, 5)
word = rect[0] * W_MEM + rect[1]
wid = comp.place(_painter(word, RED), plane_origin=rect[:2],
                 size=rect[2:], name="origin_painter")
comp.run_all()
pre = comp.composite()
print(f"pre-move  canvas[{rect[0]},{rect[1]}] = {tuple(pre[rect[0], rect[1]])} "
      f"(expect {_rgb(RED)})")
NEW = (20, 10)
comp.move(wid, NEW)
post = comp.composite()
new_word = NEW[0] * W_MEM + NEW[1]
print(f"post-move canvas[{NEW[0]},{NEW[1]}] = {tuple(post[NEW[0], NEW[1]])} "
      f"(new grid word {new_word}, which holds {0x0})")
lit_pre = int((pre != 0).any(axis=2).sum())
lit_post = int((post != 0).any(axis=2).sum())
print(f"lit cells pre={lit_pre} post={lit_post}")
comp.close()

# ── (b) full-tile painter, moved (the product case) ──────────────────────
print("=== (b) full-tile painter (guest paints all 15 cells), moved ===")
comp = GlyphCompositor()
rect = (10, 0, 3, 5)
wid = comp.place(_fill_tile(RED), plane_origin=rect[:2], size=rect[2:],
                 name="fill_painter")
comp.run_all()
pre = comp.composite()
lit_pre = int((pre != 0).any(axis=2).sum())
print(f"pre-move: lit cells={lit_pre} (expect 15); origin="
      f"{tuple(pre[rect[0], rect[1]])}")
NEW = (20, 10)
comp.move(wid, NEW)
post = comp.composite()
lit_post = int((post != 0).any(axis=2).sum())
new_word = NEW[0] * W_MEM + NEW[1]
print(f"post-move: lit cells={lit_post} of 15; origin cell renders "
      f"{tuple(post[NEW[0], NEW[1]])} (RAM word {new_word} = "
      f"{comp._table.tasks[comp.window(wid)['pid']]['cpu'].memory[new_word]})")
black = 15 - lit_post
print(f"BLACK CELLS after drag: {black}/15 "
      f"({100 * black / 15:.0f}% of the moved window's pixels)")
comp.close()
print("done")
