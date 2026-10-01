"""item-41 gate: dynamic process lifecycle & spatial task manager.

Legs:
  T1  Spawn + lifecycle table: placements are 'ready'; run_ready()
      advances them to 'exited' with correct statuses; tasks() is an
      accurate multi-task snapshot.
  T2  Kill-before-run: EXIT_FAULT reap with an EMPTY PRT stream (no
      guest code executed) and no paint in the composite.
  T3  Pause/resume: paused tasks are skipped by run_ready(); resume
      re-arms them; loud refusals on bad transitions.
  T4  Kill-after-reap refuses; recorded status unchanged.
  T5  Manager tile end-to-end: fenced manager window paints one
      distinct state color per task row from seeded words; hit_test
      returns the manager wid.
  T6  Refresh respawn: same locked rect, NEW state color after a
      lifecycle change (reactive leg).
  T7  Clean window close: reaped window retires (hit_test/composite
      drop it, tracking drops); non-reaped close refused loud.
  T8  Fence still governs: out-of-tile ST under run_ready() reaps
      EXIT_FAULT; manager operations still work afterwards.
  N1  Engine byte-guard: glyph_isa_v2.py md5 == HEAD's blob.
  N2  Non-vacuity: zero tasks -> empty run, unpainted task rows;
      pause() on a never-existent pid raises.

RED legs (run before GREEN, mutations reverted after):
  RED 1: run_ready() ignores the paused state -> T3 FAILS.
  RED 2: kill() marks EXIT_OK instead of EXIT_FAULT -> T2 FAILS.

Honesty: no rates/latencies asserted (rule-1 floors do not attach);
all asserts structural. NOT proven: no GPU/WGSL execution (host CPU
oracle); kill is NOT mid-run termination (run-boundary, guest never
runs); no preemption/interrupts (cooperative commit-between-runs).
"""
import hashlib
import os
import subprocess
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.glyph_compositor import GlyphCompositor  # noqa: E402
from tools.glyph_isa_v2 import (  # noqa: E402
    GlyphAssemblerV2,
    OpcodeMapV2,
    W_MEM,
)
from tools.glyph_process import EXIT_FAULT, EXIT_OK  # noqa: E402
from tools.glyph_taskmgr import (  # noqa: E402
    MGR_COL,
    MGR_MAX_TASKS,
    MGR_ROW,
    MGR_ROW_W,
    STATE_COLORS,
    STATE_PAUSED,
    STATE_READY,
    TaskManagerError,
    GlyphTaskManager,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _head_md5(rel: str) -> str:
    out = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=REPO,
                         capture_output=True, check=True)
    return hashlib.md5(out.stdout).hexdigest()


def _engine_md5() -> str:
    with open(os.path.join(REPO, "tools/glyph_isa_v2.py"), "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


_OM = OpcodeMapV2()
_ASM = GlyphAssemblerV2(_OM)


def _halt_image() -> np.ndarray:
    return _ASM.assemble(["LDI r1 0", "SYSCALL r0 0x05", "HALT"],
                         width_instrs=8)


def _paint_image(color: int, cells: int) -> np.ndarray:
    """A guest that paints `cells` cells at its own tile origin (TILE
    ROW/COL idiom) then exits."""
    from tools.glyph_isa_v2 import TILE_COL_ADDR, TILE_ROW_ADDR
    return _ASM.assemble([
        f"LDI r20 {TILE_ROW_ADDR >> 2}",
        "LD r10 r20",
        f"LDI r21 {TILE_COL_ADDR >> 2}",
        "LD r11 r21",
        f"LDI r12 {W_MEM}",
        "MUL r10 r12",
        "ADD r10 r11",
        f"LDI r13 {cells}",
        f"LDI r14 {color}",
        "ST r10 r14",
        "ADD r10 r13",
        "LDI r1 0",
        "SYSCALL r0 0x05",
        "HALT",
    ], width_instrs=8)


def _rogue_image(target_word: int) -> np.ndarray:
    from tools.glyph_isa_v2 import KFAULT_PC_ADDR
    return _ASM.assemble([
        f"LDI r1 {KFAULT_PC_ADDR >> 2}",
        "LD r2 r1",                  # r2 = reaper pc (park cleanly after)
        f"LDI r3 {W_MEM}",
        "MUL r3 r12",
        f"LDI r3 {target_word}",
        "LDI r4 0xDEADB0",
        "ST r3 r4",                  # OUT OF TILE -> E-K1 trap
        "LDI r1 0",
        "SYSCALL r0 0x05",
        "HALT",
    ], width_instrs=8)


def _manager_cell(mgr: GlyphTaskManager, row_index: int) -> tuple[int, int]:
    """(row, col) of task-row `row_index`'s state cell on the plane.
    The manager guest paints row i's state cell at tile-origin + i
    cells along its first column."""
    return MGR_ROW, MGR_COL + row_index


def _canvas_cell(comp: GlyphCompositor, row: int, col: int):
    canvas = comp.composite()
    return canvas[row, col] if (row < canvas.shape[0] and col < canvas.shape[1]) else None


def _rgb_of(word: int) -> tuple[int, int, int]:
    return ((word >> 16) & 0xFF, (word >> 8) & 0xFF, word & 0xFF)


# ── T1 ───────────────────────────────────────────────────────────────────

def test_t1_spawn_and_lifecycle_table():
    comp = GlyphCompositor()
    mgr = GlyphTaskManager(comp)
    try:
        w1 = mgr.place_app(_halt_image(), (4, 4), (1, 3), name="alpha")
        w2 = mgr.place_app(_halt_image(), (8, 8), (1, 3), name="beta")
        snap = mgr.tasks()
        assert len(snap) == 2
        assert set(snap) == {w1, w2}
        assert all(t["state"] == STATE_READY for t in snap.values())
        assert {t["name"] for t in snap.values()} == {"alpha", "beta"}
        statuses = mgr.run_ready()
        assert len(statuses) == 2
        assert all(rc == EXIT_OK for rc in statuses.values())
        snap = mgr.tasks()
        assert all(t["state"] == "exited" for t in snap.values())
        assert all(t["exit_status"] == EXIT_OK for t in snap.values())
    finally:
        comp.close()


# ── T2 ───────────────────────────────────────────────────────────────────

def test_t2_kill_before_run_never_executes():
    comp = GlyphCompositor()
    mgr = GlyphTaskManager(comp)
    try:
        wid = mgr.place_app(_paint_image(0xF0F0F0, 3), (4, 4), (1, 3),
                            name="victim")
        pid = mgr.tasks()[wid]["pid"]
        mgr.kill(pid)
        snap = mgr.tasks()
        assert snap[wid]["state"] == "exited"
        assert snap[wid]["exit_status"] == EXIT_FAULT
        # no guest code executed: PRT stream EMPTY
        assert comp.output(wid) == b""
        # and run_ready() does not resurrect it
        assert mgr.run_ready() == {}
        # no paint ever landed from the victim's tile
        assert _canvas_cell(comp, 4, 4) is None or \
            tuple(_canvas_cell(comp, 4, 4)) == (0, 0, 0)
    finally:
        comp.close()


# ── T3 ───────────────────────────────────────────────────────────────────

def test_t3_pause_resume():
    comp = GlyphCompositor()
    mgr = GlyphTaskManager(comp)
    try:
        wp = mgr.place_app(_halt_image(), (4, 4), (1, 3), name="pausedone")
        wr = mgr.place_app(_halt_image(), (8, 8), (1, 3), name="runner")
        pid_p = mgr.tasks()[wp]["pid"]
        pid_r = mgr.tasks()[wr]["pid"]
        mgr.pause(pid_p)
        assert mgr.tasks()[wp]["state"] == STATE_PAUSED
        statuses = mgr.run_ready()          # paused one skipped
        assert set(statuses) == {pid_r}
        assert mgr.tasks()[wp]["state"] == STATE_PAUSED
        assert mgr.tasks()[wr]["state"] == "exited"
        mgr.resume(pid_p)
        assert mgr.tasks()[wp]["state"] == STATE_READY
        statuses = mgr.run_ready()
        assert set(statuses) == {pid_p}
        assert mgr.tasks()[wp]["exit_status"] == EXIT_OK
        # loud refusals
        with pytest.raises(TaskManagerError):
            mgr.resume(pid_r)               # exited, not paused
        with pytest.raises(TaskManagerError):
            mgr.pause(pid_r)                # exited
        with pytest.raises(TaskManagerError):
            mgr.pause(4242)                 # unknown pid
    finally:
        comp.close()


# ── T4 ───────────────────────────────────────────────────────────────────

def test_t4_kill_after_exit_refuses():
    comp = GlyphCompositor()
    mgr = GlyphTaskManager(comp)
    try:
        wid = mgr.place_app(_halt_image(), (4, 4), (1, 3), name="done")
        pid = mgr.tasks()[wid]["pid"]
        mgr.run_ready()
        before = mgr.tasks()[wid]
        with pytest.raises(TaskManagerError):
            mgr.kill(pid)
        after = mgr.tasks()[wid]
        assert before == after              # refusal left the record intact
    finally:
        comp.close()


# ── T5 ───────────────────────────────────────────────────────────────────

def test_t5_manager_tile_paints_states():
    comp = GlyphCompositor()
    mgr = GlyphTaskManager(comp)
    try:
        wa = mgr.place_app(_halt_image(), (6, 20), (1, 3), name="readyapp")
        wb = mgr.place_app(_halt_image(), (10, 20), (1, 3), name="pauser")
        wc = mgr.place_app(_halt_image(), (14, 20), (1, 3), name="victim")
        pid_a = mgr.tasks()[wa]["pid"]
        pid_b = mgr.tasks()[wb]["pid"]
        pid_c = mgr.tasks()[wc]["pid"]
        mgr.kill(pid_c)                     # exited-fault
        mgr.pause(pid_b)                    # paused
        # pid_a stays ready

        mw = mgr.open_manager()
        wcb = comp.window(mw)
        assert wcb["state"] == 1 and wcb["visible"] == 1
        # the manager tile is a real fenced placement at the locked rect
        assert (wcb["y"], wcb["x"]) == (MGR_ROW, MGR_COL)

        # rows in tracked (wid) order: wa -> ready, wb -> paused, wc -> exited-fault
        expect = [STATE_COLORS[STATE_READY], STATE_COLORS[STATE_PAUSED],
                  STATE_COLORS["exited-fault"]]
        for i, want in enumerate(expect):
            r, c = _manager_cell(mgr, i)
            cell = _canvas_cell(comp, r, c)
            assert cell is not None, f"row {i}: no composite cell"
            got = (int(cell[0]), int(cell[1]), int(cell[2]))
            assert got == _rgb_of(want), \
                f"row {i}: {got} != {_rgb_of(want)}"
        # hit_test inside the tile returns the manager wid
        r, c = _manager_cell(mgr, 0)
        assert comp.hit_test(r, c) == mw
    finally:
        comp.close()


# ── T6 ───────────────────────────────────────────────────────────────────

def test_t6_refresh_respawn_reactive():
    comp = GlyphCompositor()
    mgr = GlyphTaskManager(comp)
    try:
        wa = mgr.place_app(_halt_image(), (6, 20), (1, 3), name="app")
        pid_a = mgr.tasks()[wa]["pid"]
        mgr.open_manager()
        r, c = _manager_cell(mgr, 0)
        cell = _canvas_cell(comp, r, c)
        assert cell is not None
        assert tuple(int(v) for v in cell) == _rgb_of(STATE_COLORS[STATE_READY])

        mgr.pause(pid_a)
        old_wid = mgr.manager_wid()
        assert old_wid is not None
        old_rect = comp.window(old_wid)["rect"]
        assert mgr.tasks()[wa]["state"] == STATE_PAUSED
        new_wid = mgr.refresh()
        assert new_wid is not None
        new_wcb = comp.window(new_wid)
        assert new_wcb["rect"] == old_rect  # SAME locked rect
        cell = _canvas_cell(comp, r, c)
        assert cell is not None
        got = (int(cell[0]), int(cell[1]), int(cell[2]))
        assert got == _rgb_of(STATE_COLORS[STATE_PAUSED])
    finally:
        comp.close()


# ── T7 ───────────────────────────────────────────────────────────────────

def test_t7_clean_close_and_live_refusal():
    comp = GlyphCompositor()
    mgr = GlyphTaskManager(comp)
    try:
        w1 = mgr.place_app(_paint_image(0x00FF00, 2), (4, 4), (1, 3), name="closable")
        w2 = mgr.place_app(_halt_image(), (8, 4), (1, 3), name="live")
        mgr.run_ready()                     # w1, w2 both reaped
        # close w1: retires cleanly
        mgr.close_window(w1)
        assert w1 not in mgr.tasks()
        # composite no longer shows its paint: hide it and re-composite
        # (records are append-only; a hidden window drops out)
        cell = _canvas_cell(comp, 4, 5)
        # after close, composite of remaining windows: w2 at (8,4) — row 4 col 5
        # must now be BLACK only if w1 was the painter there. w1 painted
        # (4,4)-(4,5); after retirement the cell falls back to w2's coverage
        # or black. w2's rect is row 8 — no coverage. So black:
        assert cell is None or tuple(cell) == (0, 0, 0)
        assert comp.hit_test(4, 4) is None
        # live-window refusal: place + never run
        w3 = mgr.place_app(_halt_image(), (12, 4), (1, 3), name="live3")
        before = comp.window(w3)
        with pytest.raises(TaskManagerError):
            mgr.close_window(w3)
        assert comp.window(w3) == before    # record unchanged
    finally:
        comp.close()


# ── T8 ───────────────────────────────────────────────────────────────────

def test_t8_fence_governs_and_lane_survives():
    comp = GlyphCompositor()
    mgr = GlyphTaskManager(comp)
    try:
        target = 5 * W_MEM + 0              # row 5 col 0 — outside its tile
        wr = mgr.place_app(_rogue_image(target), (8, 4), (1, 3), name="rogue")
        wa = mgr.place_app(_halt_image(), (12, 4), (1, 3), name="innocent")
        pid_r = mgr.tasks()[wr]["pid"]
        pid_a = mgr.tasks()[wa]["pid"]
        statuses = mgr.run_ready()
        assert statuses[pid_r] == EXIT_FAULT
        assert statuses[pid_a] == EXIT_OK
        assert mgr.tasks()[wr]["state"] == "exited"
        # the lane still works: place + pause + resume a fresh task runs fine
        wb = mgr.place_app(_halt_image(), (16, 4), (1, 3), name="after")
        pid_b = mgr.tasks()[wb]["pid"]
        mgr.pause(pid_b)
        assert mgr.tasks()[wb]["state"] == STATE_PAUSED
        assert set(mgr.run_ready()) == set()   # paused: skipped
        mgr.resume(pid_b)
        assert mgr.run_ready() == {pid_b: EXIT_OK}
        with pytest.raises(TaskManagerError):
            mgr.kill(pid_r)                 # already reaped — refuse loud
    finally:
        comp.close()


# ── N1 / N2 ──────────────────────────────────────────────────────────────

def test_n1_engine_byte_guard():
    assert _engine_md5() == _head_md5("tools/glyph_isa_v2.py")


def test_n2_non_vacuity():
    comp = GlyphCompositor()
    mgr = GlyphTaskManager(comp)
    try:
        assert mgr.run_ready() == {}        # zero tasks, nothing runs
        mw = mgr.open_manager()             # tile paints no task rows
        for i in range(MGR_MAX_TASKS):
            r, c = _manager_cell(mgr, i)
            cell = _canvas_cell(comp, r, c)
            assert cell is None or tuple(cell) == (0, 0, 0)
        with pytest.raises(TaskManagerError):
            mgr.pause(31337)                # never-existed pid
    finally:
        comp.close()
