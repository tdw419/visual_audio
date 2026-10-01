"""glyph_taskmgr.py — CLAIM QUEUE item 41: dynamic process lifecycle &
spatial task manager (process kill/pause signals, interactive task
manager tile, clean window close).

Spec (QUEUE_STATE item-41, brief .builder_queue/BRIEF_item41_taskmgr.md):
compose the LANDED item-26 process table + item-38 compositor into a
lifecycle layer. "Signals" on the cooperative model are honest
run-boundary operations — there is NO preemption and NO mid-run
interrupt (glyph_process.py:198-199 refuses re-entry of a running task;
that landed refusal stays). kill/pause act BEFORE first run or AFTER a
run boundary, kernel-class (landed precedent: item-40 _seed_tray /
harvest, glyph_notify.py:313-349).

Layer contract (what this module consumes, never modifies):
  - item-26 (tools/glyph_process.py): GlyphProcessTable pid table,
    states ready/running/exited, EXIT_OK/EXIT_FAULT, the cooperative
    _run_task refusal. USED, never overridden (no monkey-patching).
  - item-38 (tools/glyph_compositor.py): GlyphCompositor.place/
    run_all/composite/hit_test/set_visible — records append-only;
    retirement is set_visible(False) (the item-40 expire idiom).
  - item-29 (tools/glyph_containment.py): every task is FENCED to its
    own tile via place(); an out-of-tile store traps E-K1 to the
    reaper and reaps EXIT_FAULT.
  - item-40 (tools/glyph_notify.py): idioms only — guest paint from
    TILE_ROW/COL, kernel-class seed, respawn-repaint at a locked rect.
  - CPU-oracle engine: NO new syscall, NO engine change (N1 byte-guard).

The task manager tile: a real fenced compositor window whose guest task
paints one row per task — a state cell colored from kernel-seeded words
(green ready, amber paused, red exited-fault, dim gray exited-ok). The
guest paints from its OWN tile origin (TILE_ROW/COL idiom); refresh()
respawns the manager task at the SAME locked rect with re-seeded state
words (glyph_notify.py:_repaint_tray shape).

Honesty (Phase-2 boundary, item-37/40 doctrine): host-side artifact
over the CPU-oracle engine. kill() before first run is the SIGKILL
analog and is total by construction (no guest code executes — the PRT
stream stays empty); it is NOT a mid-run termination. pause() is not a
signal delivery — it is a scheduler-visible state flip at a run
boundary. No GPU/WGSL execution, no preemption, no interrupts. No
rates/latencies asserted (rule-1 floors do not attach).
"""
from __future__ import annotations

import numpy as np

from tools.glyph_compositor import CompositorError, GlyphCompositor
from tools.glyph_isa_v2 import (
    TILE_COL_ADDR,
    TILE_ROW_ADDR,
    GlyphAssemblerV2,
    OpcodeMapV2,
    W_MEM,
)
from tools.glyph_process import EXIT_FAULT, EXIT_OK  # noqa: F401

# ── GlyphTaskManager ABI constants ───────────────────────────────────────

STATE_READY = "ready"
STATE_PAUSED = "paused"
STATE_RUNNING = "running"
STATE_EXITED = "exited"

# Per-state row colors (word & 0xFFFFFF -> RGB, the Glyph convention).
STATE_COLORS = {
    STATE_READY: 0x20C040,    # green
    STATE_PAUSED: 0xFFC000,   # amber
    "exited-fault": 0xFF2020, # red
    "exited-ok": 0x606060,    # dim gray
}

MGR_ROW = 2                     # manager tile plane row
MGR_COL = 0                     # manager tile plane col
MGR_ROW_W = 4                   # cells per task row: state cell + 3 pad
MGR_MAX_TASKS = 6               # task rows the manager tile can show


class TaskManagerError(Exception):
    """Raised on manager misuse — loud, never silent."""


def _exit_key(exit_status: int | None) -> str:
    """Color key for an exited task."""
    if exit_status is None:
        return "exited-fault"   # not reaped cleanly -> treat as fault
    return "exited-ok" if exit_status == EXIT_OK else "exited-fault"


class GlyphTaskManager:
    """Process lifecycle + spatial task manager over the item-38
    compositor and the item-26 process table it drives."""

    def __init__(self, compositor: GlyphCompositor | None = None):
        self.comp = compositor if compositor is not None else GlyphCompositor()
        self._om = OpcodeMapV2()
        self._asm = GlyphAssemblerV2(self._om)
        # wid -> {"pid": int, "name": str}  (tracked application windows)
        self._tracked: dict[int, dict] = {}
        # pids paused by the manager (a manager-side overlay — the landed
        # table's own state machine is never overloaded: its
        # ready/running/exited values drive _run_task's re-entry guard).
        self._paused: set[int] = set()
        self._mgr_wid: int | None = None
        self._mgr_task_n = 0

    # ── lifecycle signals (run-boundary, kernel-class) ───────────────────
    def pause(self, pid: int) -> None:
        """pause(pid): ready -> paused. A paused task is skipped by
        run_ready() and cannot be run to completion. Loud refusals:
        unknown pid, exited task (its lifecycle is finished — a pause
        after exit is a caller bug, not a scheduler event)."""
        task = self._require_pid(pid)
        if task["state"] == STATE_EXITED:
            raise TaskManagerError(
                f"pause: pid {pid} has exited (status "
                f"{task['exit_status']}) — lifecycle finished, refused")
        if task["state"] != STATE_READY:
            raise TaskManagerError(
                f"pause: pid {pid} is {task['state']!r}, not ready — refused")
        self._paused.add(pid)

    def resume(self, pid: int) -> None:
        """resume(pid): paused -> ready. Loud refusal otherwise."""
        self._require_pid(pid)
        if pid not in self._paused:
            raise TaskManagerError(
                f"resume: pid {pid} is not paused — refused")
        self._paused.discard(pid)

    def kill(self, pid: int) -> None:
        """kill(pid): the SIGKILL analog at a run boundary. For a task
        that has NOT yet run: reap it WITHOUT executing any guest code —
        state 'exited', exit_status EXIT_FAULT. Total by construction
        (the guest never runs), and honestly NOT a mid-run kill. For an
        already-exited task: loud refusal (T4)."""
        task = self._require_pid(pid)
        if task["state"] == STATE_EXITED:
            raise TaskManagerError(
                f"kill: pid {pid} already exited (status "
                f"{task['exit_status']}) — nothing to kill")
        task["exit_status"] = EXIT_FAULT
        task["state"] = STATE_EXITED

    def run_ready(self) -> dict[int, int]:
        """Advance every READY task one cooperative run to completion
        (skipping paused tasks — the scheduler-visible effect of
        pause). Returns pid -> exit status for the tasks that ran."""
        statuses: dict[int, int] = {}
        for wid, info in self._tracked.items():
            pid = info["pid"]
            if pid in self._paused:
                continue                     # paused: skipped, not run
            task = self._require_pid(pid)
            if task["state"] == STATE_EXITED:
                continue                     # killed earlier: not resurrected
            try:
                statuses[pid] = self.comp._table.wait(pid)
            finally:
                # NB: comp.window() returns a COPY of the record — the
                # reaped flag must be set on the compositor's live
                # _windows record itself (internal-table access, the
                # same class of access as item-40's comp._table use).
                self.comp._windows[wid]["reaped"] = True
        return statuses

    # ── placement (the manager owns its windows' lifecycle) ──────────────
    def place_app(self, image: np.ndarray, plane_origin: tuple[int, int],
                  size: tuple[int, int], name: str = "") -> int:
        """Place an application window (fenced, item-38 contract) and
        track it. The task stays 'ready' until run_ready() advances it
        (cooperative delivery — placement never runs guest code)."""
        wid = self.comp.place(image, plane_origin=plane_origin, size=size,
                              name=name)
        pid = self.comp.window(wid)["pid"]
        self._tracked[wid] = {"pid": pid, "name": name or f"win{wid}"}
        return wid

    # ── clean window close (the compositor's records are append-only) ────
    def close_window(self, wid: int) -> None:
        """Cleanly close a REAPED window: set_visible(False) (the
        compositor's sanctioned removal) and drop the manager's
        tracking. A non-reaped window's tile is live — REFUSED loud,
        record unchanged."""
        if wid not in self._tracked:
            raise TaskManagerError(f"close_window: window {wid} is not tracked")
        wcb = self.comp.window(wid)
        if not wcb["reaped"]:
            raise TaskManagerError(
                f"close_window: window {wid} has not run to completion — "
                "a live tile is not closable, refused")
        self.comp.set_visible(wid, False)
        del self._tracked[wid]

    # ── the task manager tile ────────────────────────────────────────────
    def open_manager(self) -> int:
        """Place the task-manager tile (a real fenced window) and run
        ONLY the manager task. NB: comp.run_all() is compositor-global
        (it would run every app task that is merely being displayed —
        opening a task list must not execute applications); the
        manager drives its own pid through the landed table's wait()."""
        if self._mgr_wid is not None:
            wcb = self.comp.window(self._mgr_wid)
            if wcb["state"] == 1 and wcb["visible"] == 1:
                raise TaskManagerError("open_manager: the manager tile is already open")
        self._mgr_wid = self.comp.place(
            self._manager_program(),
            plane_origin=(MGR_ROW, MGR_COL),
            size=(1 + MGR_MAX_TASKS, MGR_ROW_W),   # header row + task rows
            name="taskmgr")
        self._seed_manager()
        self._run_manager_task()
        return self._mgr_wid

    def refresh(self) -> int:
        """Respawn the manager task at the SAME locked rect with freshly
        seeded state words (item-40 _repaint_tray shape): the reactive
        leg — a state change becomes a new paint."""
        if self._mgr_wid is None:
            raise TaskManagerError("refresh: the manager was never opened")
        self.comp.set_visible(self._mgr_wid, False)
        self._mgr_task_n += 1
        self._mgr_wid = self.comp.place(
            self._manager_program(),
            plane_origin=(MGR_ROW, MGR_COL),
            size=(1 + MGR_MAX_TASKS, MGR_ROW_W),
            name=f"taskmgr{self._mgr_task_n}")
        assert self._mgr_wid is not None  # place() always returns an int wid
        self._seed_manager()
        self._run_manager_task()
        return self._mgr_wid

    def _run_manager_task(self) -> None:
        """Run ONLY the manager task's engine (its own fenced tile) to
        completion and mark its window reaped. Application windows stay
        untouched — a task-list refresh never executes applications."""
        assert self._mgr_wid is not None
        wcb = self.comp._windows[self._mgr_wid]
        pid = wcb["pid"]
        try:
            self.comp._table.wait(pid)
        finally:
            wcb["reaped"] = True

    # ── introspection ────────────────────────────────────────────────────
    def tasks(self) -> dict[int, dict]:
        """Snapshot keyed by window id: wid -> {pid, name, state,
        exit_status}. `state` is the MANAGER-VISIBLE state: 'paused'
        when the manager paused the pid, otherwise the landed table's
        own state."""
        snap: dict[int, dict] = {}
        for wid, info in self._tracked.items():
            task = self._require_pid(info["pid"])
            state = (STATE_PAUSED if info["pid"] in self._paused
                     else task["state"])
            snap[wid] = {
                "pid": info["pid"],
                "name": info["name"],
                "state": state,
                "exit_status": task["exit_status"],
            }
        return snap

    def manager_wid(self) -> int | None:
        return self._mgr_wid

    def close(self) -> None:
        self.comp.close()
        self._om.close()

    # ── internals ────────────────────────────────────────────────────────
    def _require_pid(self, pid: int) -> dict:
        if pid not in self.comp._table.tasks:
            raise TaskManagerError(f"no such pid: {pid}")
        return self.comp._table.tasks[pid]

    def _state_rows(self) -> list[tuple[int, str]]:
        """(pid, color_key) per tracked task, wid order — the rows the
        manager tile paints. Exceeding MGR_MAX_TASKS refuses loud at
        seed time (the tile simply cannot draw more rows)."""
        rows = []
        for wid, info in self._tracked.items():
            pid = info["pid"]
            task = self._require_pid(pid)
            if pid in self._paused:
                key = STATE_PAUSED
            elif task["state"] == STATE_EXITED:
                key = _exit_key(task["exit_status"])
            else:
                key = task["state"]
            rows.append((pid, key))
        if len(rows) > MGR_MAX_TASKS:
            raise TaskManagerError(
                f"manager tile holds {MGR_MAX_TASKS} rows, {len(rows)} tracked "
                "tasks — refused loud, seed unchanged")
        return rows

    def _manager_program(self) -> np.ndarray:
        """The manager task: read TILE_ROW/COL (the item-40 C7 idiom),
        then for each task row i paint MGR_ROW_W cells — cell 0 the
        seeded state color, the rest background. Seeded color word 0
        paints nothing (an empty row stays black; N2)."""
        tile_row_ptr = TILE_ROW_ADDR >> 2
        tile_col_ptr = TILE_COL_ADDR >> 2
        b = MGR_ROW * W_MEM + MGR_COL
        lines = [
            f"LDI r20 {tile_row_ptr}",
            "LD r10 r20",
            f"LDI r21 {tile_col_ptr}",
            "LD r11 r21",
            f"LDI r12 {W_MEM}",
            "MUL r10 r12",
            "ADD r10 r11",               # r10 = tile origin word
            "LDI r13 1",                 # stride (next cell)
        ]
        for i in range(MGR_MAX_TASKS):
            base = b + (1 + i) * MGR_ROW_W
            lines += [
                f"LDI r14 {base}",
                "LD r17 r14",            # seeded state color word
                "LDI r19 0",
                "CMP r17 r19",
                f"JZ :skip{i}",          # zero word -> no paint (N2)
                "ST r10 r17",            # state cell at tile origin + i*ROW_W
                f":skip{i}",
                "ADD r10 r13",           # advance one cell per row slot
            ]
        # NOTE: rows advance one CELL per task in this layout refinement:
        # the manager paints row i's state cell at tile-origin cell (i+1)
        # of its FIRST column — the header cell 0 stays unpainted. The
        # seed addresses below use the same mapping.
        lines += ["LDI r1 0", "SYSCALL r0 0x05", "HALT"]
        return self._asm.assemble(lines, width_instrs=8)

    def _seed_manager(self) -> None:
        """Kernel-class seed: one state-color word per tracked task row
        into the manager task's RAM (the guest copies them through —
        the paint is still guest-side, fenced)."""
        wcb = self.comp.window(self._mgr_wid)
        cpu = self.comp._table.tasks[wcb["pid"]]["cpu"]
        b = MGR_ROW * W_MEM + MGR_COL
        for i, (_pid, key) in enumerate(self._state_rows()):
            cpu.memory[b + (1 + i) * MGR_ROW_W] = STATE_COLORS[key] & 0xFFFFFF
