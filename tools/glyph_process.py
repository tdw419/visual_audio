"""glyph_process.py — item-26 spatial process model: spawn primitive +
multi-task coordination (CLAIM QUEUE round-13 item 26).

Landscape (why this exists, grounded in landed artifacts):
  - SE021 (tools/glyph_child_runner.py) proved glyph-on-glyph isolation:
    a child runs in a FRESH GlyphCPUv2 with its own memory — it cannot
    touch the parent's registers or RAM. But the runner is a one-shot
    HOST subprocess; there is no process TABLE, no pid, no exit-status
    reaping, no coordination between tasks.
  - item-25 (tools/glyph_vfs.py, commit 9c285fdf) landed an attachable
    VFS so tasks can share DATA (staged overlay + PNG disk).

item-26 is the third leg: a host-side process table that spawns tasks as
fresh in-process GlyphCPUv2 engines over supplied images, tracks
pid -> (image, cpu, state, exit_status), and coordinates tasks through a
shared VFS. NO new syscall numbers are introduced — a Python-only table
adds no guest-visible ABI, so the WGSL twin contract is untouched (the
0x12/0x13 bridge false-success class, TICKET_ITEM8 precedent, never gets
a new number to mis-bridge).

Design contract:
  - spawn(image, vfs=None) -> pid. The parent's engine state is NEVER
    shared: each task gets a fresh GlyphCPUv2 (SE021 isolation delta,
    in-process instead of subprocess — the table is a scheduler, not a
    shell verb).
  - wait(pid) -> exit_status. Steps the task's engine to HALT/EXIT/fault
    (bounded by max_instructions), then returns the exit status:
    * SYSCALL 0x05 EXIT carries r1 -> the engine's _handle_syscall
      returns it; the item-26 engine hook (2 additive lines keyed on
      the same getattr-default pattern as item-25's vfs hook) latches it
      into cpu.exit_status when the task runs under a table.
    * clean HALT with no EXIT -> exit_status 0 (a program that stops is
      a success by the child-runner rc contract).
    * faulted engine -> exit_status 1 (glyph_child_runner.py:49 rc=1
      contract).
  - wait_any() -> (pid, status) for multi-task coordination.
  - Shared VFS: the table attaches ONE GlyphVfs to every task that
    supplies vfs_shared=True, so 0x03/0x04/0x13 hits the same staged
    overlay/disk — the coordination channel (item-25's landed arms,
    unmodified).

What this is NOT: no preemption, no timer-yield scheduling across tasks
(GH-16's in-engine tick is untouched), no signals, no memory sharing
between task RAMs. Multi-task = cooperative, spawn-then-wait.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from tools.glyph_isa_v2 import (  # noqa: F401
    KFAULT_PC_ADDR,
    GlyphCPUv2,
    OpcodeMapV2,
    _unpack_immediate,
)
from tools.glyph_containment import (  # noqa: F401
    DEFAULT_REAPER_ROW,
    ContainmentError,
    arm_tile,
    wrap_with_reaper,
)

# Exit-status contract (mirrors tools/glyph_child_runner.py):
EXIT_OK = 0
EXIT_FAULT = 1


class GlyphProcessError(Exception):
    pass


class _TaskExitStatus(GlyphCPUv2):
    """GlyphCPUv2 with a latched exit status.

    Subclass rather than monkey-patching so the base class's __init__ /
    step() behavior is inherited byte-for-byte. _handle_syscall(0x05)
    RETURNS the status (glyph_isa_v2.py:1554-1559); the table wraps the
    handler ONCE at spawn to latch it — the same additive-hook shape as
    item-25's `self.vfs = None` default (no behavior change unless a
    process table is driving the engine).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.exit_status: int | None = None
        self._on_exit: Any = None  # set by the table (callable or None)

    def _handle_syscall(self, syscall_num: int, image: np.ndarray, imm: int = 0) -> int:
        rc = super()._handle_syscall(syscall_num, image, imm)
        if syscall_num == 0x05 and self._on_exit is not None:
            self._on_exit(rc)
        return rc


class GlyphProcessTable:
    """Spawn/reap/coordinate spatial tasks over fresh GlyphCPUv2 engines."""

    def __init__(self, cols_instrs: int = 8, memory_words: int = 16384):
        self._opcode_map = OpcodeMapV2()
        self._cols_instrs = cols_instrs
        self._memory_words = memory_words
        self._next_pid = 1
        # pid -> dict(image, cpu, state, exit_status, name)
        self.tasks: dict[int, dict] = {}

    # ── spawn ────────────────────────────────────────────────────────────
    def spawn(self, image: np.ndarray, name: str = "", vfs=None,
              vfs_shared: bool = False, max_instructions: int = 100_000,
              tile: tuple[int, int, int, int] | None = None,
              reaper_pc: int = 0,
              reaper_row: int | None = None) -> int:
        """Spawn a task over `image` in a FRESH engine. Returns the pid.

        vfs_shared=True attaches the shared `vfs` (an attached GlyphVfs)
        to this task's engine — coordination via the item-25 arms.

        item-29 (per-process spatial containment): tile=(row,col,h,w)
        arms the GO-2 tile words in the task's own RAM and drops the
        engine to MODE_USER BEFORE the first instruction — the engine's
        existing box check then traps any out-of-tile user store (the
        store does not land; FAULT_ADDR/FAULT_PC record the evidence).
        reaper_pc (packed (row<<16)|col) arms KFAULT_PC so the trap
        vectors to a reaper trampoline instead of a bare stop; the table
        plants a HALT at (col 0, reaper_row) in a TALL COPY of the image
        (default row 30). After the trap the offending task HALTs parked
        on the trampoline in SUPER mode and _run_task maps faulted -> 
        EXIT_FAULT (the reaper contract). A task spawned with tile=None
        (the default) gets exactly the item-26 posture: MODE_SUPER,
        TILE_H==0, no box check, byte-identical legacy behavior.
        """
        if not isinstance(image, np.ndarray) or image.ndim != 3:
            raise GlyphProcessError("spawn: image must be an HxWx3 ndarray")
        if self._next_pid > 0xFFFF:
            raise GlyphProcessError("spawn: pid space exhausted (16-bit)")
        pid = self._next_pid
        self._next_pid += 1
        # item-29: containment image preparation happens BEFORE the pid is
        # handed out, so a wrap failure cannot leak a half-armed task.
        # THE FENCE NEEDS A CATCHER: arming a tile drops the engine to
        # USER, and the E-K1 store trap reads KFAULT_PC UNCONDITIONALLY on
        # the ST path (glyph_isa_v2.py:1052-1056 — unlike the LD/PT paths,
        # there is no kf==0 "disabled" branch). A tile armed with KFAULT_PC
        # == 0 would trap-straight-to-(0,0): the engine restarts the
        # program in SUPER mode, re-executes the offending store in SUPER
        # (never box-checked), and it LANDS — the fence would hold on the
        # first attempt and silently fail on the re-execution. So a tiled
        # spawn always arms a reaper vector: caller-supplied reaper_pc, or
        # the default trampoline (HALT at col 0 of reaper_row, planted by
        # wrap_with_reaper in a tall copy of the image).
        if tile is not None or reaper_pc:
            if reaper_pc and reaper_row is None:
                reaper_row = DEFAULT_REAPER_ROW
            if tile is not None and not reaper_pc:
                reaper_row = DEFAULT_REAPER_ROW if reaper_row is None else reaper_row
                reaper_pc = reaper_row << 16
            if reaper_row is not None:
                image = wrap_with_reaper(image, reaper_row, self._opcode_map)
        cpu = _TaskExitStatus(self._opcode_map, self._cols_instrs)
        cpu.memory = [0] * self._memory_words
        cpu._on_exit = self._make_exit_hook(pid)
        if tile is not None:
            try:
                arm_tile(cpu, tile)
                cpu._tile_confinement = True
            except ContainmentError as exc:
                raise GlyphProcessError(f"spawn: {exc}") from exc
        if reaper_pc:
            cpu.memory[KFAULT_PC_ADDR >> 2] = reaper_pc
        if vfs_shared and vfs is not None:
            if getattr(vfs, "attached_count", None) is None and not hasattr(vfs, "attach"):
                raise GlyphProcessError("spawn: vfs has no attach()")
            vfs.attach(cpu)
        self.tasks[pid] = {
            "image": image,
            "cpu": cpu,
            "state": "ready",
            "exit_status": None,
            "name": name or f"task{pid}",
            "max_instructions": max_instructions,
        }
        return pid

    def _make_exit_hook(self, pid: int):
        def hook(rc: int):
            task = self.tasks.get(pid)
            if task is not None:
                task["exit_status"] = rc
                task["state"] = "exited"
        return hook

    # ── scheduling ───────────────────────────────────────────────────────
    def _run_task(self, pid: int) -> int:
        task = self.tasks[pid]
        cpu = task["cpu"]
        if task["state"] == "exited":
            return task["exit_status"]
        if task["state"] == "running":
            raise GlyphProcessError(f"wait: pid {pid} is already being run")
        task["state"] = "running"
        try:
            cpu.run(task["image"], max_instructions=task["max_instructions"])
        except Exception:
            task["state"] = "exited"
            task["exit_status"] = EXIT_FAULT
            raise
        if task["exit_status"] is None:
            # No explicit EXIT: a clean HALT is rc 0 (child-runner
            # contract); a faulted engine is rc 1.
            task["exit_status"] = EXIT_FAULT if cpu.faulted else EXIT_OK
            task["state"] = "exited"
        else:
            task["state"] = "exited"
        return task["exit_status"]

    def wait(self, pid: int) -> int:
        """Run the task to completion and return its exit status."""
        if pid not in self.tasks:
            raise GlyphProcessError(f"wait: no such pid {pid}")
        return self._run_task(pid)

    def wait_any(self) -> tuple[int, int]:
        """Run the FIRST READY task in pid order and return (pid, status);
        if no ready task remains, return the first already-exited pair.
        The table is cooperative: `run()` on a non-exited task advances
        one engine to HALT (no preemption).
        """
        for pid in sorted(self.tasks):
            task = self.tasks[pid]
            if task["state"] == "ready":
                return pid, self._run_task(pid)
        for pid in sorted(self.tasks):
            task = self.tasks[pid]
            if task["state"] == "exited":
                return pid, task["exit_status"]
        raise GlyphProcessError("wait_any: no ready or exited tasks")

    def wait_all(self) -> dict[int, int]:
        """Run every ready task to completion; return pid -> status map."""
        statuses: dict[int, int] = {}
        for pid in sorted(self.tasks):
            if self.tasks[pid]["state"] != "exited":
                statuses[pid] = self._run_task(pid)
            else:
                statuses[pid] = self.tasks[pid]["exit_status"]
        return statuses

    # ── introspection ────────────────────────────────────────────────────
    def state(self, pid: int) -> str:
        if pid not in self.tasks:
            raise GlyphProcessError(f"state: no such pid {pid}")
        return self.tasks[pid]["state"]

    def output(self, pid: int) -> bytes:
        """The task's PRT stream (the glyph stdout contract)."""
        if pid not in self.tasks:
            raise GlyphProcessError(f"output: no such pid {pid}")
        return bytes(self.tasks[pid]["cpu"].output)

    def close(self):
        self._opcode_map.close()
