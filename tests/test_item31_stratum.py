"""item-31 gate: GPU-first spatial window coordinator (GlyphStratum).

Claim-queue item 31 (QUEUE_STATE.json / watchdog draft spec): "Spatial
Program Coordinator managing autonomous process windows as rectangular
instruction/framebuffer tiles on infinite 2D plane without host compositor
dependency."

Legs:
  W1  open_window claims a rect on the word-grid plane and spawns the
      window's task FENCED to it (item-29 tile words armed in the task's
      own RAM, engine MODE_USER); the WCB row records the wcb.rs field
      vocabulary (STATE/X/Y/W/H/Z/VISIBLE) with z assigned ascending.
  W2  PLACEMENT CONTAINMENT: a second window overlapping an open window's
      rect is refused LOUD (StratumError); after the refusal the first
      window is untouched and a NON-overlapping window opens fine.
  W3  MMIO REFUSAL: any rect overlapping the isolation MMIO block rows
      [256,264) is refused — a window there could rewrite its own fence
      words (TILE_* live at BOX_MMIO_BASE+0x160..0x16C). Zero-extent and
      out-of-plane rects refused loud too.
  W4  THE COMPOSITE IS THE PLANE: a window task stores a color word into
      its OWN tile words; after run_all, composite() shows the color at
      the window's rect — and ONLY there (background black, other cells
      untouched).
  W5  FENCED PAINT: a task that tries to paint OUTSIDE its window's rect
      traps (the engine's E-K1 trap — no host check needed), the store
      does NOT land in the victim cells, the offending window's task is
      reaped EXIT_FAULT, and the composite still renders the other
      windows — cross-window paint is impossible BY THE FENCE.
  W6  Z-ORDER + HIT-TEST: raise_window puts a window on top; hit_test
      returns the topmost visible window covering a contested cell; a
      hidden window (set_visible False) drops out of hit_test and out of
      the composite; close_window frees its rect (the same rect can be
      re-opened after close).
  W7  FULL CHAIN: window programs arrive through the item-30 loader
      (store_program -> sync -> fresh GlyphVfs -> load) and open fenced:
      a loader-supplied window paints its tile and the composite proves
      it (the coordinator composes the LAYER, not just spawned arrays).
  R1  MIGRATION: item-29's containment gate re-runs GREEN in this tree
      via subprocess (the coordinator is a pure consumer of spawn(tile=)).
  R2  MIGRATION: item-30's loader gate re-runs GREEN in this tree via
      subprocess (the coordinator changes no loader code path).
  N1  ENGINE-BYTE guard: tools/glyph_isa_v2.py is byte-identical to HEAD
      (item-31 is a HOST-side coordinator; any engine drift invalidates
      the gate's premises).

Honesty: no rates/latencies asserted (rule-1 floors do not attach); all
asserts structural (rects, WCB fields, RAM words, composite pixels,
statuses). Zero new syscall numbers; no engine change (the fence is the
landed item-29 arm over the EXISTING GO-2 tile predicate). NOT proven:
no GPU/WGSL execution (host CPU engine, Phase-2 doctrine — same boundary
as items 26-30); no live/incremental compositing of RUNNING tasks
(cooperative run-then-compose); no input routing (item-32); no shell UI
(item-33); "infinite plane" is the sparse coordinate model bounded by
each task's memory_words (the engine contract), not unbounded RAM.
"""
import hashlib
import os
import subprocess
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.glyph_isa_v2 import (  # noqa: E402
    BOX_MMIO_BASE,
    FAULT_ADDR_ADDR,
    FAULT_PC_ADDR,
    GlyphAssemblerV2,
    OpcodeMapV2,
    TILE_H_ADDR,
    TILE_ROW_ADDR,
    MODE_USER,
    W_MEM,
)
from tools.glyph_loader import load_program, store_program  # noqa: E402
from tools.glyph_process import EXIT_FAULT, EXIT_OK  # noqa: E402
from tools.glyph_root_init import GlyphRootFs  # noqa: E402
from tools.glyph_stratum import (  # noqa: E402
    MMIO_ROW_HI,
    MMIO_ROW_LO,
    StratumError,
    GlyphStratum,
)

# A window rect well clear of the MMIO rows and of other legs' rects.
R1_ROW, R1_COL, R1_H, R1_W = 10, 0, 2, 4
IN_R1_WORD = R1_ROW * W_MEM + R1_COL                    # 320
OUT_R1_WORD = IN_R1_WORD + R1_W                         # 324: first col outside


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


def _rgb(color: int) -> tuple:
    return ((color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF)


# ── W1: open_window arms the fence + records the WCB row ────────────────
def test_w1_open_window_fences_and_records_wcb():
    s = GlyphStratum()
    wid = s.open_window(_exit_prog(0), plane_origin=(R1_ROW, R1_COL),
                        size=(R1_H, R1_W), name="alpha")
    wcb = s.window(wid)
    # WCB vocabulary (wcb.rs fields, word-grid coords):
    assert wcb["state"] == 1
    assert wcb["x"] == R1_COL and wcb["y"] == R1_ROW
    assert wcb["w"] == R1_W and wcb["h"] == R1_H
    assert wcb["z"] == 1 and wcb["visible"] == 1
    # The task is FENCED: tile words armed in its own RAM, MODE_USER.
    pid = wcb["pid"]
    cpu = s._table.tasks[pid]["cpu"]
    assert cpu.memory[TILE_ROW_ADDR >> 2] == R1_ROW
    assert cpu.memory[TILE_H_ADDR >> 2] == R1_H
    assert cpu.mode == MODE_USER
    assert s.run_all()[pid] == EXIT_OK
    s.close()


# ── W2: overlapping placement refused loud; non-overlap fine ─────────────
def test_w2_overlap_refused_nonoverlap_ok():
    s = GlyphStratum()
    s.open_window(_exit_prog(0), plane_origin=(R1_ROW, R1_COL),
                  size=(R1_H, R1_W), name="first")
    # Exact-same rect: overlap.
    with pytest.raises(StratumError):
        s.open_window(_exit_prog(0), plane_origin=(R1_ROW, R1_COL),
                      size=(R1_H, R1_W), name="dup")
    # Partial overlap (one row down, same cols).
    with pytest.raises(StratumError):
        s.open_window(_exit_prog(0), plane_origin=(R1_ROW + 1, R1_COL),
                      size=(R1_H, R1_W), name="partial")
    # Disjoint rect: opens, and gets the next z.
    wid = s.open_window(_exit_prog(0), plane_origin=(R1_ROW, R1_COL + R1_W + 1),
                        size=(R1_H, R1_W), name="second")
    assert s.window(wid)["z"] == 2
    assert len(s.windows()) == 2
    s.close()


# ── W3: MMIO-block rects refused + degenerate rects refused ──────────────
def test_w3_mmio_and_degenerate_rects_refused():
    s = GlyphStratum()
    # A rect fully inside the MMIO rows: refuses.
    with pytest.raises(StratumError):
        s.open_window(_exit_prog(0), plane_origin=(MMIO_ROW_LO, 0),
                      size=(2, 4), name="mmio-inside")
    # A rect straddling the MMIO boundary row: refuses.
    with pytest.raises(StratumError):
        s.open_window(_exit_prog(0), plane_origin=(MMIO_ROW_LO - 1, 0),
                      size=(2, 4), name="mmio-straddle")
    # Zero-extent size: refuses (TILE_H==0 is the engine's "inert" encoding).
    with pytest.raises(StratumError):
        s.open_window(_exit_prog(0), plane_origin=(R1_ROW, R1_COL),
                      size=(0, 4), name="zero-h")
    # Origin beyond the RAM-bounded plane: refuses.
    with pytest.raises(StratumError):
        s.open_window(_exit_prog(0), plane_origin=(16384 // W_MEM, 0),
                      size=(2, 4), name="off-plane")
    # Col must stay within one grid row: refuses.
    with pytest.raises(StratumError):
        s.open_window(_exit_prog(0), plane_origin=(R1_ROW, W_MEM - 1),
                      size=(2, 4), name="col-overflow")
    assert s.windows() == {}, "refused opens must not leave window records"
    s.close()


# ── W4: the composite is the plane ───────────────────────────────────────
def test_w4_composite_shows_window_paint():
    s = GlyphStratum()
    color = 0x0BADC0DE & 0xFFFFFF  # engine words are 24-bit
    wid = s.open_window(_painter(IN_R1_WORD, color),
                        plane_origin=(R1_ROW, R1_COL),
                        size=(R1_H, R1_W), name="painter")
    assert s.run_all()[s.window(wid)["pid"]] == EXIT_OK
    canvas = s.composite()
    # Canvas covers the window's bounding box.
    assert canvas.shape == (R1_ROW + R1_H, R1_COL + R1_W, 3)
    # The painted word renders as RGB at ITS grid cell...
    assert tuple(canvas[R1_ROW, R1_COL]) == _rgb(color)
    # ...and ONLY there: the rest of the rect is unpainted (word 0 = black).
    for dr in range(R1_H):
        for dc in range(R1_W):
            if (dr, dc) == (0, 0):
                continue
            got = tuple(canvas[R1_ROW + dr, R1_COL + dc])
            assert got == (0, 0, 0), f"cell ({dr},{dc})={got} not black"
    # Background cells outside the rect stay black too.
    assert tuple(canvas[0, 0]) == (0, 0, 0)
    assert tuple(canvas[R1_ROW - 1, R1_COL]) == (0, 0, 0)
    # And the plane words OUTSIDE the tile were never written (the fence).
    cpu = s._table.tasks[s.window(wid)["pid"]]["cpu"]
    assert cpu.memory[OUT_R1_WORD] == 0
    s.close()


# ── W5: cross-window paint is impossible BY THE FENCE ────────────────────
def test_w5_out_of_window_paint_traps_and_never_lands():
    s = GlyphStratum()
    #窗口A at rows [10,12): paints its own tile — the innocent neighbor.
    a = s.open_window(_painter(IN_R1_WORD, 0x00FF00),
                      plane_origin=(R1_ROW, R1_COL), size=(R1_H, R1_W),
                      name="neighbor")
    # Window B below A: tries to paint INTO A's tile rows (word 320 is
    # outside B's rect at rows [20,22)) — the cross-window paint attempt.
    b_row = R1_ROW + 10
    b = s.open_window(_painter(IN_R1_WORD, 0xFF0000),
                      plane_origin=(b_row, R1_COL), size=(2, 4),
                      name="escaping")
    statuses = s.run_all()
    assert statuses[s.window(a)["pid"]] == EXIT_OK
    assert statuses[s.window(b)["pid"]] == EXIT_FAULT, \
        "cross-window paint must be reaped EXIT_FAULT"
    cpu_b = s._table.tasks[s.window(b)["pid"]]["cpu"]
    # The offending store NEVER landed in A's tile...
    assert cpu_b.memory[IN_R1_WORD] == 0, "cross-window store LANDED — breach"
    # ...the engine raised the E-K1 fault with evidence words...
    assert cpu_b.faulted is True
    assert cpu_b.memory[FAULT_ADDR_ADDR >> 2] == IN_R1_WORD * 4
    # ...and A's own paint is intact in A's OWN engine (RAM isolation +
    # fence: B cannot even address A's RAM, let alone store into it).
    cpu_a = s._table.tasks[s.window(a)["pid"]]["cpu"]
    assert cpu_a.memory[IN_R1_WORD] == 0x00FF00
    # The composite still renders A; B contributes nothing (its rect cells
    # stay black — B's paint never landed anywhere).
    canvas = s.composite()
    assert tuple(canvas[R1_ROW, R1_COL]) == _rgb(0x00FF00)
    assert tuple(canvas[b_row, R1_COL]) == (0, 0, 0)
    s.close()


# ── W6: z-order, hit-test, visibility, close-frees-rect ──────────────────
def test_w6_zorder_hittest_visibility_close():
    s = GlyphStratum()
    # NOTE: placement containment (W2) guarantees open rects are DISJOINT,
    # so a hit-test cell is contested only across z/visibility state over
    # time, never between simultaneously-open windows — the leg asserts
    # exactly that: rect lookup when one window covers the cell, None on
    # empty space, and top-most-among-VISIBLE semantics once one window is
    # hidden is exercised by hide+reopen of the SAME rect.
    wa = s.open_window(_exit_prog(0), plane_origin=(R1_ROW, R1_COL),
                       size=(R1_H, R1_W), name="A")
    wb = s.open_window(_exit_prog(0), plane_origin=(R1_ROW, R1_COL + R1_W + 1),
                       size=(R1_H, R1_W), name="B")
    # hit_test resolves each window's own cells to it.
    assert s.hit_test(R1_ROW, R1_COL) == wa
    assert s.hit_test(R1_ROW, R1_COL + R1_W + 1) == wb
    # Empty space: None.
    assert s.hit_test(0, 0) is None
    # raise_window bumps A above B's z (visible in the WCB record).
    assert s.raise_window(wa) == 3
    assert s.window(wa)["z"] > s.window(wb)["z"]
    # Hidden windows drop out of hit_test and the composite.
    s.set_visible(wa, False)
    assert s.hit_test(R1_ROW, R1_COL) is None
    canvas = s.composite()
    assert tuple(canvas[R1_ROW, R1_COL]) == (0, 0, 0), \
        "hidden window must not render"
    s.set_visible(wa, True)
    assert s.hit_test(R1_ROW, R1_COL) == wa
    # close_window retires the record and frees the rect: the SAME rect
    # can be re-opened (W2's overlap refusal no longer fires).
    s.close_window(wa)
    assert s.window(wa)["state"] == 0
    wid_reuse = s.open_window(_exit_prog(0), plane_origin=(R1_ROW, R1_COL),
                              size=(R1_H, R1_W), name="A2")
    assert wid_reuse > wb
    # Unknown window id: loud.
    with pytest.raises(StratumError):
        s.window(999)
    s.close()


# ── W7: full chain — loader-supplied windows compose ─────────────────────
def test_w7_loader_supplied_windows_compose(tmp_path):
    from tools.glyph_vfs import GlyphVfs  # noqa: E402  (item-25 arms)

    png = str(tmp_path / "root.png")
    root = GlyphRootFs.format(png, hostname=b"stratum-w7")
    # Each painter targets the FIRST WORD OF ITS OWN tile (the composite
    # cell its window owns) — red at (10,0), blue at (10,5): disjoint
    # rects, so each store is in-tile and must land.
    red = _painter(R1_ROW * W_MEM + R1_COL, 0xFF0000)
    blue = _painter(R1_ROW * W_MEM + (R1_COL + R1_W + 1), 0x0000FF)
    store_program(root, "/bin/win_red", red)
    store_program(root, "/bin/win_blue", blue)
    assert root.sync() == 0
    del root

    s = GlyphStratum()
    # The programs arrive through the item-30 loader chain (fresh VFS,
    # digest verify, reshape) and open FENCED on the plane.
    wid_r = s.open_window_from_disk(
        png, "/bin/win_red", plane_origin=(R1_ROW, R1_COL),
        size=(R1_H, R1_W), name="red")
    wid_b = s.open_window_from_disk(
        png, "/bin/win_blue", plane_origin=(R1_ROW, R1_COL + R1_W + 1),
        size=(R1_H, R1_W), name="blue")
    statuses = s.run_all()
    assert all(v == EXIT_OK for v in statuses.values())
    # Both windows painted their OWN first tile word — in their OWN RAM.
    cpu_r = s._table.tasks[s.window(wid_r)["pid"]]["cpu"]
    cpu_b = s._table.tasks[s.window(wid_b)["pid"]]["cpu"]
    assert cpu_r.memory[R1_ROW * W_MEM + R1_COL] == 0xFF0000
    assert cpu_b.memory[R1_ROW * W_MEM + (R1_COL + R1_W + 1)] == 0x0000FF
    # Neither store leaked into the other's plane cells.
    assert cpu_r.memory[R1_ROW * W_MEM + (R1_COL + R1_W + 1)] == 0
    assert cpu_b.memory[R1_ROW * W_MEM + R1_COL] == 0
    # The composite shows red and blue at their own rects — the plane is
    # the shared canvas, the RAMs are not.
    canvas = s.composite()
    assert tuple(canvas[R1_ROW, R1_COL]) == (0xFF, 0, 0)
    assert tuple(canvas[R1_ROW, R1_COL + R1_W + 1]) == (0, 0, 0xFF)
    # The gap cell between the windows stays black.
    assert tuple(canvas[R1_ROW, R1_COL + R1_W]) == (0, 0, 0)
    s.close()


# ── R1/R2: migration — landed gates re-run on this tree ──────────────────
def test_r1_item29_gate_still_green():
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_item29_containment.py",
         "-x", "-q", "--no-header"],
        capture_output=True, text=True, timeout=600,
    )
    assert r.returncode == 0, f"item-29 gate regressed:\n{r.stdout[-2000:]}"


def test_r2_item30_gate_still_green():
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_item30_loader.py",
         "-x", "-q", "--no-header"],
        capture_output=True, text=True, timeout=600,
    )
    assert r.returncode == 0, f"item-30 gate regressed:\n{r.stdout[-2000:]}"


# ── N1: engine-byte guard ─────────────────────────────────────────────────
def test_n1_engine_byte_identical_to_head():
    head = subprocess.run(
        ["git", "show", "HEAD:tools/glyph_isa_v2.py"],
        capture_output=True, check=True,
    ).stdout
    with open("tools/glyph_isa_v2.py", "rb") as f:
        worktree = f.read()
    assert hashlib.sha256(head).hexdigest() == hashlib.sha256(worktree).hexdigest(), (
        "tools/glyph_isa_v2.py drifted from HEAD — item-31 is host-side only"
    )
