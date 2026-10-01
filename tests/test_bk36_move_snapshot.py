"""BK-36 gate: snapshot-at-reap — a moved window composites what its
guest actually painted.

Legs:
  L1  Full-tile painter (USER guest paints ALL cells of its 3x5 tile
      from inside its own fence, exit 0) run + reaped, then dragged to
      (20,10): post-move composite shows 15/15 lit cells at the NEW
      rect, same color. RED today: 0/15 (RESEARCH_move_damage_blackout.md
      scenario b).
  L2  Origin-painter moved: the single paint follows the window to the
      new rect (RED today: lost).
  L3  Pre-reap move still refused loud (contract unchanged).
  L4  LIVE (un-reaped) windows still render from RAM: composite before
      reap identical with snapshots enabled (snapshot inactive while a
      window is live); a live repaint between composites is visible.
  L5  Non-vacuity: snapshot capture neutered -> L1's 15/15 goes RED
      (proved by mutation, reverted after).
  L6  Family: item-38 (incl. C4's out-of-plane refusal) + item-41 gates
      green with the snapshot change in place.

RED legs (run before GREEN, mutations reverted after):
  RED A (L5): neuter `_snapshot_at_reap` -> L1 FAILS.
  RED B: stash the implementation -> L1+L2 FAIL (the pre-landing defect).

Honesty: no rates/latencies asserted (rule-1 floors do not attach); all
asserts structural. NOT proven: no GPU/WGSL execution (host CPU oracle);
no live (running-guest) dragging semantics change (move() still refuses
non-reaped windows); item-40 notification surfaces not exercised.
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.glyph_compositor import CompositorError, GlyphCompositor  # noqa: E402
from tools.glyph_isa_v2 import (  # noqa: E402
    TILE_COL_ADDR,
    TILE_H_ADDR,
    TILE_ROW_ADDR,
    W_MEM,
    GlyphAssemblerV2,
    OpcodeMapV2,
)
from tools.glyph_process import EXIT_OK  # noqa: E402

ORIGIN = (40, 2)          # plane origin of the test window
SIZE = (3, 5)             # 3 rows x 5 cols = 15 cells
NEW_ORIGIN = (20, 10)     # the drag destination
COLOR = 0xFF0000          # red


def _prog(lines):
    om = OpcodeMapV2()
    img = GlyphAssemblerV2(om).assemble(lines, width_instrs=8)
    om.close()
    return img


def _rgb(color: int) -> tuple:
    return ((color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF)


def _full_tile_painter(color: int) -> np.ndarray:
    """USER-mode guest: read OWN TILE_ROW/TILE_COL from the MMIO block,
    compute its fence origin, paint ALL 15 cells of the 3x5 tile (walk
    origin + r*W_MEM + c for r in 0..3, c in 0..5 — every store inside
    its own fence), then EXIT 0. The item-37 desktop-suite idiom.

    ISA notes (proven this tick): the engine ISA is 2-operand
    (ADD/MUL read rd,rs2 -> rd += rs2 / rd *= rs2), so constants are
    materialized via ADD rd rK from an LDI'd register; JNZ jumps when
    the CMP flag is CLEAR (i.e. while operands differ)."""
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
        f"LDI r19 {SIZE[0]}",          # h = 3
        f"LDI r22 {SIZE[1]}",          # w = 5
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


def _origin_painter(word_addr: int, color: int) -> np.ndarray:
    return _prog([
        f"LDI r5 {color}",
        f"LDI r6 {word_addr}",
        "ST r6 r5",
        "LDI r1 0",
        "SYSCALL r0 0x05",
        "HALT",
    ])


def _lit_cells(canvas: np.ndarray, color: int = COLOR) -> int:
    want = np.array(_rgb(color), dtype=np.uint8)
    if canvas.size == 0:
        return 0
    return int(sum(1 for px in canvas.reshape(-1, 3) if tuple(px) == tuple(want)))


# ── L1: full-tile painter moved -> 15/15 lit at the NEW rect ─────────────
def test_l1_full_tile_snapshot_follows_move():
    comp = GlyphCompositor()
    wid = comp.place(_full_tile_painter(COLOR), plane_origin=ORIGIN,
                     size=SIZE, name="fullpaint")
    statuses = comp.run_all()
    pid = comp.window(wid)["pid"]
    assert statuses[pid] == EXIT_OK, "guest must exit 0 (fence held)"
    pre = comp.composite()
    assert _lit_cells(pre) == 15, "pre-move: all 15 cells painted"
    comp.move(wid, NEW_ORIGIN)
    post = comp.composite()
    assert _lit_cells(post) == 15, \
        "post-move: the dragged window keeps ALL 15 painted cells"
    # The lit cells are exactly the NEW rect, same color per cell.
    want = np.array(_rgb(COLOR), dtype=np.uint8)
    for dr in range(SIZE[0]):
        for dc in range(SIZE[1]):
            got = tuple(post[NEW_ORIGIN[0] + dr, NEW_ORIGIN[1] + dc])
            assert got == tuple(want), f"new rect ({dr},{dc}): {got}"
    comp.close()


# ── L2: origin-painter moved -> the paint follows ─────────────────────────
def test_l2_origin_paint_follows_move():
    comp = GlyphCompositor()
    word = ORIGIN[0] * W_MEM + ORIGIN[1]
    wid = comp.place(_origin_painter(word, COLOR), plane_origin=ORIGIN,
                     size=SIZE, name="originpaint")
    comp.run_all()
    pre = comp.composite()
    assert tuple(pre[ORIGIN[0], ORIGIN[1]]) == _rgb(COLOR)
    comp.move(wid, NEW_ORIGIN)
    post = comp.composite()
    assert tuple(post[NEW_ORIGIN[0], NEW_ORIGIN[1]]) == _rgb(COLOR), \
        "the single painted cell must follow the dragged window"
    comp.close()


# ── L3: pre-reap move still refused loud ──────────────────────────────────
def test_l3_move_before_reap_refused():
    comp = GlyphCompositor()
    wid = comp.place(_origin_painter(ORIGIN[0] * W_MEM + ORIGIN[1], COLOR),
                     plane_origin=ORIGIN, size=SIZE, name="live")
    with pytest.raises(CompositorError):
        comp.move(wid, NEW_ORIGIN)
    assert comp.window(wid)["rect"] == (ORIGIN[0], ORIGIN[1], SIZE[0], SIZE[1])
    comp.close()


# ── L4: live windows still render from RAM (snapshot inactive) ────────────
def test_l4_live_windows_render_from_ram():
    comp = GlyphCompositor()
    word = ORIGIN[0] * W_MEM + ORIGIN[1]
    wid = comp.place(_origin_painter(word, COLOR), plane_origin=ORIGIN,
                     size=SIZE, name="live")
    # Run the guest to completion WITHOUT reaping it (the table's wait()
    # directly, the item-41 mechanism): the composite must still render
    # from RAM (the snapshot only exists at reap time — run_all()).
    pid = comp.window(wid)["pid"]
    comp._table.wait(pid)
    pre = comp.composite()
    assert tuple(pre[ORIGIN[0], ORIGIN[1]]) == _rgb(COLOR)
    assert _lit_cells(pre) == 1
    # Host-side RAM poke (the B-state test seam, no guest involved):
    # a live window's composite must reflect it (snapshot inactive).
    cpu = comp._table.tasks[comp.window(wid)["pid"]]["cpu"]
    cpu.memory[word] = 0x00FF00
    mid = comp.composite()
    assert tuple(mid[ORIGIN[0], ORIGIN[1]]) == _rgb(0x00FF00), \
        "live window renders from RAM, not from any snapshot"
    comp.close()


# ── L6: family regression (item-38 + item-41) is run by the lane as a
# separate pytest invocation; see the receipt for the exact command. ───────
