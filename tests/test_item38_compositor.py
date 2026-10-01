"""item-38 gate: spatial window compositing, z-order elevation, damage
clipping, top-window focus, drag repositioning (GlyphCompositor).

Legs:
  C1  Overlapping placement: two windows on overlapping rects both spawn
      FENCED (TILE_* armed, MODE_USER); z assigned by arrival order; no
      error (overlap is the compositor's contract — GlyphStratum's live
      overlap guard is NOT weakened; the compositor is a sibling module).
  C2  Damage clipping: opaque top window wins every contested cell; the
      bottom window shows ONLY where the top does not cover.
  C3  Z-order elevation: raise(bottom) flips ownership of the contested
      cells in BOTH composite() and hit_test().
  C4  Drag repositioning: move() relocates the paint to the new rect
      (old rect now shows the bottom window), out-of-plane move refused
      loud with the record unchanged.
  C5  Fences still govern: an out-of-tile store traps (E-K1 + reaper),
      never lands, offender reaped EXIT_FAULT, the innocent window still
      composites.
  C6  Focus/visibility: hit_test returns the topmost visible window; a
      hidden window drops out of hit_test AND the composite (cells
      reveal the window beneath).
  C7  Guest-computed paint FROM the fence: a USER-mode guest LOADs its
      own TILE_ROW/TILE_COL, computes its origin word, paints there
      (measured prerequisite: output/item38_probe_selftile.py).
  C8  Non-vacuity: zero windows -> (0,0,3) canvas; all-hidden -> all
      black at the bbox (a gate that cannot fail is decoration).

RED legs (run before GREEN, mutations reverted after):
  RED 1: composite z-sort flipped (ascending -> descending) -> C2 FAILS.
  RED 2: clipping application suppressed (occupied mask writes removed)
         -> C2 FAILS (lower window overpaints the top).

Honesty: no rates/latencies asserted (rule-1 floors do not attach); all
asserts structural. NOT proven: no GPU/WGSL execution (host CPU oracle);
no incremental dirty-rect damage tracking (full recompute per composite);
move() is a reaped-window record/composite move, not live guest dragging.
"""
import hashlib
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.glyph_compositor import CompositorError, GlyphCompositor  # noqa: E402
from tools.glyph_isa_v2 import (  # noqa: E402
    MODE_USER,
    TILE_COL_ADDR,
    TILE_H_ADDR,
    TILE_ROW_ADDR,
    W_MEM,
    GlyphAssemblerV2,
    OpcodeMapV2,
)
from tools.glyph_process import EXIT_FAULT, EXIT_OK  # noqa: E402


def _prog(lines):
    om = OpcodeMapV2()
    img = GlyphAssemblerV2(om).assemble(lines, width_instrs=8)
    om.close()
    return img


def _painter(word_addr: int, color: int) -> np.ndarray:
    """Store `color` at word_addr, then EXIT 0."""
    return _prog([
        f"LDI r5 {color}",
        f"LDI r6 {word_addr}",
        "ST r6 r5",
        "LDI r1 0",
        "SYSCALL r0 0x05",
        "HALT",
    ])


def _exit_prog(status: int) -> np.ndarray:
    return _prog([
        f"LDI r1 {status}",
        "SYSCALL r0 0x05",
        "HALT",
    ])


def _self_tile_painter(color: int) -> np.ndarray:
    """USER-mode guest: read OWN TILE_ROW/TILE_COL from the MMIO block,
    compute origin = row*W_MEM + col, paint `color` there. (The LD/ST
    fence governs stores only; MMIO reads are in-contract — measured,
    output/item38_probe_selftile.py.)"""
    return _prog([
        f"LDI r20 {TILE_ROW_ADDR >> 2}",
        "LD r10 r20",
        f"LDI r21 {TILE_COL_ADDR >> 2}",
        "LD r11 r21",
        f"LDI r12 {W_MEM}",
        "MUL r10 r12",
        "ADD r10 r11",
        f"LDI r5 {color}",
        "ST r10 r5",
        "LDI r1 0",
        "SYSCALL r0 0x05",
        "HALT",
    ])


def _rgb(color: int) -> tuple:
    return ((color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF)


# Geometry: BOTTOM window rows [10,13) x cols [0,5); TOP window rows
# [11,14) x cols [3,8) — overlap = row 11..12 x col 3..4 (2x2 contested).
BOT = (10, 0, 3, 5)
TOP = (11, 3, 3, 5)
BOT_WORD = BOT[0] * W_MEM + BOT[1]        # 320: bottom origin word
TOP_WORD = TOP[0] * W_MEM + TOP[1]        # 355: top origin word
BOT_COLOR = 0x0000FF                       # blue — bottom paint
TOP_COLOR = 0x00FF00                       # green — top paint
CONTESTED_CELLS = [(11, 3), (11, 4), (12, 3), (12, 4)]
BOT_ONLY_CELLS = [(10, 4), (12, 0), (12, 2)]  # (10,0) is the bottom's paint cell
TOP_ONLY_CELLS = [(11, 5), (11, 7), (13, 5), (13, 7)]


def _two_overlapping(comp, bottom_prog, top_prog):
    bot = comp.place(bottom_prog, plane_origin=BOT[:2], size=BOT[2:], name="bottom")
    top = comp.place(top_prog, plane_origin=TOP[:2], size=TOP[2:], name="top")
    return bot, top


# ── C1: overlapping placement, both fenced, z by arrival ─────────────────
def test_c1_overlap_permitted_both_fenced():
    comp = GlyphCompositor()
    bot, top = _two_overlapping(comp, _exit_prog(0), _exit_prog(0))
    assert _rects_overlap_report(BOT, TOP), "test geometry must overlap"
    wb, wt = comp.window(bot), comp.window(top)
    # z assigned by arrival: bottom=1, top=2 (later stacks ON TOP).
    assert wb["z"] == 1 and wt["z"] == 2
    # BOTH tasks fenced to their OWN rects (overlap is composite-level,
    # never fence-level).
    for wcb, rect in ((wb, BOT), (wt, TOP)):
        pid = wcb["pid"]
        cpu = comp._table.tasks[pid]["cpu"]
        assert cpu.memory[TILE_ROW_ADDR >> 2] == rect[0]
        assert cpu.memory[TILE_COL_ADDR >> 2] == rect[1]
        assert cpu.memory[TILE_H_ADDR >> 2] == rect[2]
        assert cpu.mode == MODE_USER
    assert all(s == EXIT_OK for s in comp.run_all().values())
    comp.close()


def _rects_overlap_report(a, b):
    return (a[0] < b[0] + b[2] and b[0] < a[0] + a[2]
            and a[1] < b[1] + b[3] and b[1] < a[1] + a[3])


# ── C2: damage clipping — top window wins contested cells ────────────────
def test_c2_damage_clip_top_wins():
    comp = GlyphCompositor()
    bot, top = _two_overlapping(comp,
                                _painter(BOT_WORD, BOT_COLOR),
                                _painter(TOP_WORD, TOP_COLOR))
    statuses = comp.run_all()
    assert statuses[comp.window(bot)["pid"]] == EXIT_OK
    assert statuses[comp.window(top)["pid"]] == EXIT_OK
    canvas = comp.composite()
    assert canvas.shape == (14, 8, 3)
    # Top window's paint owns every contested cell.
    for (r, c) in CONTESTED_CELLS:
        got = tuple(canvas[r, c])
        if (r, c) == (TOP[0], TOP[1]):
            continue  # the top painter's own origin cell is TOP_COLOR too
        # contested cells not painted by either guest must be black
        assert got == (0, 0, 0), f"contested ({r},{c})={got}, expected black"
    # The top ORIGIN cell is TOP green.
    assert tuple(canvas[TOP[0], TOP[1]]) == _rgb(TOP_COLOR)
    # Bottom-origin cell is BOT blue (only place bottom paint can show).
    assert tuple(canvas[BOT[0], BOT[1]]) == _rgb(BOT_COLOR)
    # Cells ONLY the bottom covers but did not paint: black.
    for (r, c) in BOT_ONLY_CELLS:
        assert tuple(canvas[r, c]) == (0, 0, 0), f"bot-only ({r},{c})"
    # Cells ONLY the top covers but did not paint: black.
    for (r, c) in TOP_ONLY_CELLS:
        assert tuple(canvas[r, c]) == (0, 0, 0), f"top-only ({r},{c})"
    comp.close()


# ── C3: elevation flips composite + hit_test ownership ───────────────────
def test_c3_raise_flips_ownership():
    comp = GlyphCompositor()
    bot, top = _two_overlapping(comp,
                                _painter(BOT_WORD, BOT_COLOR),
                                _painter(TOP_WORD, TOP_COLOR))
    comp.run_all()
    # Before: top window (wid `top`) owns the contested cell.
    assert comp.hit_test(11, 3) == top
    assert tuple(comp.composite()[TOP[0], TOP[1]]) == _rgb(TOP_COLOR)
    # Elevate the bottom window.
    new_z = comp.raise_window(bot)
    assert new_z == 3 and comp.window(bot)["z"] == 3
    # hit_test flips.
    assert comp.hit_test(11, 3) == bot
    # Composite flips: the bottom window now claims the contested damage
    # region first; the top is CLIPPED out of it. The contested cell
    # (11,3) renders the BOTTOM task's RAM word 355 (0 — the bottom
    # painted only word 320), so the top's green DISAPPEARS from the
    # contested cell: green -> black is the measured ownership flip.
    canvas = comp.composite()
    assert tuple(canvas[BOT[0], BOT[1]]) == _rgb(BOT_COLOR)
    assert tuple(canvas[TOP[0], TOP[1]]) == (0, 0, 0), \
        "elevated bottom must clip the top out of the contested cell"
    # Re-raise the original top: back on top for focus.
    comp.raise_window(top)
    assert comp.hit_test(11, 3) == top
    comp.close()


# ── C4: drag repositioning (reaped windows) ──────────────────────────────
def test_c4_move_drag():
    comp = GlyphCompositor()
    bot, top = _two_overlapping(comp,
                                _painter(BOT_WORD, BOT_COLOR),
                                _painter(TOP_WORD, TOP_COLOR))
    comp.run_all()
    # move BEFORE reaped: refused loud.
    comp2 = GlyphCompositor()
    _ = comp2.place(_exit_prog(0), plane_origin=(30, 0), size=(2, 4))
    with pytest.raises(CompositorError):
        comp2.move(1, (40, 0))
    comp2.close()
    # Drag top to a rect that no longer overlaps bottom's paint cell.
    NEW = (20, 10)
    comp.move(top, NEW)
    wt = comp.window(top)
    assert (wt["y"], wt["x"]) == NEW
    assert wt["rect"] == (NEW[0], NEW[1], TOP[2], TOP[3])
    assert wt["w"] == TOP[3] and wt["h"] == TOP[2]
    canvas = comp.composite()
    # BK-36 snapshot-at-reap: the top window's paint is FROZEN at reap
    # time (word 355 = green), so the drag carries the green paint to the
    # new rect — the moved window composites WHAT ITS GUEST PAINTED, not
    # whatever RAM happens to sit at the new grid words (the old behavior
    # rendered word 670 = 0 there, i.e. 100% blackout; BK-36 L1 proves the
    # fix on a full-tile painter).
    assert tuple(canvas[BOT[0], BOT[1]]) == _rgb(BOT_COLOR)
    assert tuple(canvas[TOP[0], TOP[1]]) == (0, 0, 0), \
        "the OLD rect is vacated: the paint moved with the window"
    assert tuple(canvas[NEW[0], NEW[1]]) == _rgb(TOP_COLOR), \
        "moved origin renders the reap-time snapshot (the guest's green paint)"
    assert tuple(canvas[BOT[0], BOT[1]]) == _rgb(BOT_COLOR)
    # Out-of-plane move: refused loud, record unchanged.
    with pytest.raises(CompositorError):
        comp.move(top, (16384 // W_MEM, 0))
    assert comp.window(top)["rect"] == (NEW[0], NEW[1], TOP[2], TOP[3])
    comp.close()


# ── C5: fences still govern overlapping windows ──────────────────────────
def test_c5_fence_governs_even_with_overlap():
    comp = GlyphCompositor()
    # Innocent bottom window paints its own origin.
    bot = comp.place(_painter(BOT_WORD, BOT_COLOR),
                     plane_origin=BOT[:2], size=BOT[2:], name="innocent")
    # Rogue top window (overlapping) tries to store into the BOTTOM
    # window's origin word (320) — far outside its own tile (rows
    # [11,14) x cols [3,8) -> words 355..).
    VICTIM_WORD = BOT_WORD
    rogue = comp.place(_painter(VICTIM_WORD, 0xFF00FF),
                       plane_origin=TOP[:2], size=TOP[2:], name="rogue")
    statuses = comp.run_all()
    assert statuses[comp.window(bot)["pid"]] == EXIT_OK
    assert statuses[comp.window(rogue)["pid"]] == EXIT_FAULT
    # The store never landed in the victim word.
    vcpu = comp._table.tasks[comp.window(bot)["pid"]]["cpu"]
    assert vcpu.memory[VICTIM_WORD] == BOT_COLOR
    # ...and the rogue's own RAM never received the magenta at 320
    # either (the write was trapped, not redirected).
    rcwu = comp._table.tasks[comp.window(rogue)["pid"]]["cpu"]
    assert rcwu.memory[VICTIM_WORD] != 0xFF00FF
    # The innocent window still composites.
    canvas = comp.composite()
    assert tuple(canvas[BOT[0], BOT[1]]) == _rgb(BOT_COLOR)
    comp.close()


# ── C6: focus + visibility drop-out ──────────────────────────────────────
def test_c6_focus_and_visibility():
    comp = GlyphCompositor()
    bot, top = _two_overlapping(comp,
                                _painter(BOT_WORD, BOT_COLOR),
                                _painter(TOP_WORD, TOP_COLOR))
    comp.run_all()
    # Focus rule: topmost visible window at the contested cell.
    assert comp.hit_test(11, 3) == top
    # Hide the top window: focus passes through to bottom; composite
    # reveals the cells beneath (all black here — bottom only painted
    # its origin).
    comp.set_visible(top, False)
    assert comp.hit_test(11, 3) == bot
    canvas = comp.composite()
    assert tuple(canvas[TOP[0], TOP[1]]) == (0, 0, 0)
    assert tuple(canvas[BOT[0], BOT[1]]) == _rgb(BOT_COLOR)
    assert canvas.shape == (13, 5, 3), "hidden window drops out of bbox"
    comp.close()


# ── C7: guest-computed paint from its own fence ──────────────────────────
def test_c7_guest_paints_from_fence():
    comp = GlyphCompositor()
    wid = comp.place(_self_tile_painter(0x00FF00),
                     plane_origin=(40, 2), size=(3, 5), name="selfpaint")
    wcb = comp.window(wid)
    assert comp.run_all()[wcb["pid"]] == EXIT_OK
    origin_word = 40 * W_MEM + 2
    cpu = comp._table.tasks[wcb["pid"]]["cpu"]
    assert cpu.memory[origin_word] == 0x00FF00, \
        "guest must have computed its own fence origin and painted it"
    canvas = comp.composite()
    assert tuple(canvas[40, 2]) == (0, 255, 0)
    comp.close()


# ── C8: non-vacuity ──────────────────────────────────────────────────────
def test_c8_nonvacuity():
    comp = GlyphCompositor()
    assert comp.composite().shape == (0, 0, 3), "zero windows -> empty canvas"
    wid = comp.place(_painter(355, 0x00FF00), plane_origin=TOP[:2],
                     size=TOP[2:], name="solo")
    comp.run_all()
    comp.set_visible(wid, False)
    canvas = comp.composite()
    assert canvas.shape == (0, 0, 3), "all windows hidden -> empty canvas"
    comp.close()

    comp2 = GlyphCompositor()
    w1 = comp2.place(_exit_prog(0), plane_origin=(10, 0), size=(2, 4))
    comp2.place(_painter(355, 0x00FF00), plane_origin=(11, 3), size=(3, 5))
    comp2.set_visible(w1, False)
    comp2.run_all()
    canvas = comp2.composite()
    # Only the visible window's bbox remains; every rendered cell that
    # no guest painted must be black (not garbage, not stale).
    for r in range(canvas.shape[0]):
        for c in range(canvas.shape[1]):
            if (r, c) == (TOP[0], TOP[1]):
                continue
            assert tuple(canvas[r, c]) == (0, 0, 0), f"({r},{c}) not black"
    assert tuple(canvas[TOP[0], TOP[1]]) == (0, 255, 0)
    comp2.close()
