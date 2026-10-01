#!/usr/bin/env python3
"""
geos_proctab — process table and lifecycle (Glyph OS skeleton, OS-level).

WHY THIS EXISTS (the Linux gap it closes)
    GH-7 spawns two user tasks in BOX0/BOX1 and round-robins them; GH-16 adds
    timer preemption; BK-3/BK-4 add signals and join. Each is real, and each
    manages its own state independently inside the kernel image. What Linux has
    and GeOS does NOT is ONE authoritative process table: a single object that
    can answer "is pid 5 alive?", "who is its parent?", "what are its caps and
    address space?", and that makes illegal state transitions impossible
    instead of merely unlikely.

    Without it, waitpid (BK-4) cannot distinguish "child running" from "child
    never existed", and reaping is unverifiable.

ENGINE FACTS THIS MODULE MUST MATCH
    Boxes are BOX0/BOX1/BOX2 (MMIO lo/hi words at BOX_MMIO_BASE + 0x0C..0x2C).
    MODE_SUPER=0 / MODE_USER=1 (glyph_isa_v2 lines 102-103).
    Exit codes surface through the mailbox word convention used by BK-4.
    There is no hardware pid register — pid is kernel bookkeeping, which is
    exactly why the table must be the single authority.

DESIGN INVARIANTS
    I1  Pid allocation is deterministic: lowest free pid, never random, never
        recycled ahead of a lower free pid. Replayable (receipt discipline).
    I2  Transitions are validated against an explicit table. Any transition not
        in the table raises — no implicit "almost anything goes" transition.
    I3  A zombie is not dead: it holds an exit code until reaped by its parent.
        Collapsing these loses the exit status (the bug BK-4 exists to avoid).
    I4  A pid is not reusable while its descriptor is unreaped (no pid reuse
        races), and `reap` is the ONLY path from ZOMBIE to DEAD.
    I5  Every process names its address space (asid) and its cap set. A process
        without an aspace is a malformed process, not a default one.

BOUNDARY MAP
    GeosKernel spawn (GH-7) ──> Proctab.admit()
    GeosKernel exit  (BK-4) ──> Proctab.mark_exited()
    parent wait      (BK-4) ──> Proctab.reap()
    scheduler        (GH-16) ─> Proctab.ready_set()
    aspace teardown          <── Proctab.reap() drops the space's reference;
                                 the asid is freed at refcount 1 -> 0 (I5,
                                 OS-SKEL-R3 step 9 — the space is the owner)
    cap checks (geos_caps)   <── ProcessDescriptor.caps

PHASE STATUS
    Phase 1 (structure) : done    Phase 2 (lock): done
    Phase 3 (population): in progress (step 5: admit/mark_exited/reap populated;
                          no kernel wiring, no real MMIO, no engine integration)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import sys
from typing import Dict, List, Optional, Sequence, Tuple

try:
    from tools.geos_aspace import (
        AddressSpace,
        AsidAllocator,
        drop_reference,
        get_asid_allocator,
        get_space_source,
        set_space_source,
    )  # noqa: F401
except ModuleNotFoundError:  # direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from tools.geos_aspace import (
        AddressSpace,
        AsidAllocator,
        drop_reference,
        get_asid_allocator,
        get_space_source,
        set_space_source,
    )  # noqa: F401

__all__ = [
    "STATE_NEW",
    "STATE_READY",
    "STATE_RUNNING",
    "STATE_WAITING",
    "STATE_ZOMBIE",
    "STATE_DEAD",
    "ALL_STATES",
    "LEGAL_TRANSITIONS",
    "can_transition",
    "PidAllocator",
    "ProcessDescriptor",
    "Proctab",
    "InvalidTransition",
]

STATE_NEW = "new"
STATE_READY = "ready"
STATE_RUNNING = "running"
STATE_WAITING = "waiting"      # blocked on a child (BK-4 join) or a mailbox (BK-13)
STATE_ZOMBIE = "zombie"        # exited, exit code held until reaped (I3)
STATE_DEAD = "dead"            # reaped; resources released

ALL_STATES: Tuple[str, ...] = (
    STATE_NEW, STATE_READY, STATE_RUNNING, STATE_WAITING, STATE_ZOMBIE, STATE_DEAD,
)

# I2: the complete set of legal transitions. Anything absent raises.
LEGAL_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    STATE_NEW: (STATE_READY,),                       # admitted
    STATE_READY: (STATE_RUNNING, STATE_DEAD),        # scheduled, or killed pre-run
    STATE_RUNNING: (STATE_READY, STATE_WAITING, STATE_ZOMBIE),  # yield/block/exit
    STATE_WAITING: (STATE_READY, STATE_DEAD),        # woken, or killed while blocked
    STATE_ZOMBIE: (STATE_DEAD,),                     # reap ONLY (I4)
    STATE_DEAD: (),                                  # terminal
}


class InvalidTransition(RuntimeError):
    """Raised when a lifecycle transition is not in LEGAL_TRANSITIONS (I2)."""


def can_transition(src: str, dst: str) -> bool:
    """Is src -> dst legal? IMPLEMENTED (pure). Raises on an unknown state."""
    for state in (src, dst):
        if state not in LEGAL_TRANSITIONS:
            raise ValueError(f"unknown process state: {state!r} (known: {ALL_STATES})")
    return dst in LEGAL_TRANSITIONS[src]


class PidAllocator:
    """Deterministic lowest-free pid allocation. IMPLEMENTED (pure, I1)."""

    def __init__(self, capacity: int = 4096) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self._live: List[int] = []

    def alloc(self) -> int:
        if len(self._live) >= self.capacity:
            raise RuntimeError(f"pid space exhausted ({self.capacity} live)")
        for candidate in range(self.capacity):
            if candidate not in self._live:
                self._live.append(candidate)
                return candidate
        raise AssertionError("unreachable")

    def free(self, pid: int) -> None:
        """Release a pid — ONLY legal after reap (I4)."""
        if pid not in self._live:
            raise KeyError(f"pid {pid} is not live (double-free or pre-reap release)")
        self._live.remove(pid)

    def live(self) -> List[int]:
        return sorted(self._live)


@dataclass
class ProcessDescriptor:
    """One process. LOCKED fields; extra kernel state lives in `meta`.

    pid        : deterministic, from PidAllocator (I1)
    parent_pid : None for the first process (init); used by reap/wait (BK-4)
    asid       : its address space identity (geos_aspace) — never absent (I5)
    box        : which BOX region hosts it (0, 1, 2) — the engine's real boxes
    caps       : capability mask (geos_caps)
    state      : one of ALL_STATES
    exit_code  : meaningful only in ZOMBIE/DEAD (I3)
    """

    pid: int
    asid: int
    box: int
    caps: int = 0
    parent_pid: Optional[int] = None
    state: str = STATE_NEW
    exit_code: Optional[int] = None
    meta: Dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.state not in LEGAL_TRANSITIONS:
            raise ValueError(f"unknown state: {self.state!r}")
        if self.pid < 0 or self.asid < 0:
            raise ValueError("pid and asid must be non-negative")
        if self.box not in (0, 1, 2):
            raise ValueError(f"box must be 0, 1 or 2 (engine boxes), got {self.box}")


@dataclass
class Proctab:
    """The single authoritative process table (Phase 3 in progress).

    PHASE 3 (step 5 populated; no kernel wiring, no real MMIO, no engine integration):
        admit(desc)          : validate descriptor (NEW, lowest free pid, valid asid),
                               reserve pid + asid, transition NEW->READY.
        transition(pid, dst) : enforce LEGAL_TRANSITIONS (I2); raise InvalidTransition.
        mark_exited(pid, code): RUNNING->ZOMBIE with code recorded (I3).
        reap(pid)            : ZOMBIE->DEAD, free pid + asid (I4/I5); returns code.
        ready_set()          : pids in READY, ascending — what the GH-16 scheduler
                               consumes; must exclude zombies.
        children_of(pid)     : for BK-4 wait semantics.
        zombies()            : unreaped zombie pids, ascending (I3).
    """

    procs: Dict[int, ProcessDescriptor] = field(default_factory=dict)
    pids: PidAllocator = field(default_factory=PidAllocator)

    def admit(self, desc: ProcessDescriptor) -> ProcessDescriptor:
        if desc.state != STATE_NEW:
            raise ValueError(f"descriptor state must be {STATE_NEW!r}, got {desc.state!r}")
        if desc.pid in self.pids.live() or (desc.pid in self.procs and self.procs[desc.pid].state != STATE_DEAD):
            raise ValueError(f"pid {desc.pid} is already live or unreaped")
        allocator = get_asid_allocator()
        if allocator is None:
            raise RuntimeError(f"no asid allocator bound: refusing to admit pid {desc.pid}")

        asid_allocated = False
        if desc.asid not in allocator.live():
            try:
                granted_asid = allocator.alloc()
            except RuntimeError as exc:
                raise ValueError(f"asid space exhausted: {exc}") from exc
            if granted_asid != desc.asid:
                allocator.free(granted_asid)
                raise ValueError(
                    f"asid {desc.asid} not allocated or not lowest free ({granted_asid}) (I5)"
                )
            asid_allocated = True

        try:
            granted_pid = self.pids.alloc()
        except Exception:
            if asid_allocated:
                allocator.free(desc.asid)
            raise

        if granted_pid != desc.pid:
            self.pids.free(granted_pid)
            if asid_allocated:
                allocator.free(desc.asid)
            raise ValueError(f"pid {desc.pid} is not lowest free pid ({granted_pid}) (I1)")

        self.procs[desc.pid] = desc
        self.transition(desc.pid, STATE_READY)
        return desc

    def transition(self, pid: int, dst: str) -> ProcessDescriptor:
        """IMPLEMENTED guard, Phase-3 body — enforces I2 then stubs the effect."""
        desc = self.procs.get(pid)
        if desc is None:
            raise KeyError(f"unknown pid {pid}")
        if not can_transition(desc.state, dst):
            raise InvalidTransition(
                f"pid {pid}: illegal transition {desc.state} -> {dst} "
                f"(legal from {desc.state}: {LEGAL_TRANSITIONS[desc.state]})"
            )
        desc.state = dst
        return desc

    def mark_exited(self, pid: int, code: int) -> ProcessDescriptor:
        if isinstance(code, bool) or not isinstance(code, int) or code < 0:
            raise ValueError(f"exit code must be a non-negative integer, got {code!r}")
        desc = self.transition(pid, STATE_ZOMBIE)
        desc.exit_code = code
        return desc

    def reap(self, pid: int) -> Optional[int]:
        desc = self.procs.get(pid)
        if desc is None:
            raise KeyError(f"unknown pid {pid}")
        if desc.state != STATE_ZOMBIE:
            raise InvalidTransition(
                f"pid {pid}: cannot reap process in state {desc.state!r} (must be {STATE_ZOMBIE!r})"
            )
        allocator = get_asid_allocator()
        if allocator is None:
            raise RuntimeError(f"no asid allocator bound: refusing to reap pid {pid}")

        if pid not in self.pids.live():
            raise KeyError(f"pid {pid} is not live in pid allocator")
        if desc.asid not in allocator.live():
            raise RuntimeError(f"asid {desc.asid} is not live in bound asid allocator")

        # OS-SKEL-R3 step 9 (I5): the SPACE owns the asid, so reap can only drop a
        # reference. A descriptor that names no space is malformed (I5) — refuse
        # loudly and mutate nothing rather than inventing a space for it.
        if desc.meta.get("aspace") is None:
            raise KeyError(
                f"pid {pid} names no address space (I5): refusing to reap a malformed process"
            )

        self.transition(pid, STATE_DEAD)
        self.pids.free(pid)

        unbound_source = get_space_source() is None
        if unbound_source:
            def _local_source(target_asid: int) -> Optional[AddressSpace]:
                for p in self.procs.values():
                    if p.asid == target_asid and p.state != STATE_DEAD:
                        return p.meta.get("aspace")
                if desc.asid == target_asid:
                    return desc.meta.get("aspace")
                return None

            set_space_source(_local_source)

        try:
            drop_reference(desc.asid)
        finally:
            if unbound_source:
                set_space_source(None)

        return desc.exit_code

    def ready_set(self) -> List[int]:
        """Pids that are READY, ascending. IMPLEMENTED (pure, I3)."""
        return sorted(p.pid for p in self.procs.values() if p.state == STATE_READY)

    def children_of(self, pid: Optional[int]) -> List[int]:
        """Child pids, ascending. IMPLEMENTED (pure)."""
        return sorted(p.pid for p in self.procs.values() if p.parent_pid == pid)

    def zombies(self) -> List[int]:
        """Unreaped zombie pids, ascending. IMPLEMENTED (pure, I3)."""
        return sorted(p.pid for p in self.procs.values() if p.state == STATE_ZOMBIE)


if __name__ == "__main__":  # Phase-3 smoke: lifecycle with bound allocator.
    from tools.geos_aspace import set_asid_allocator

    alloc = AsidAllocator()
    set_asid_allocator(alloc)
    tab = Proctab()
    # Step 9 (I5): every descriptor names its space — reap resolves it and drops
    # a reference, so a space-less descriptor would (correctly) be refused.
    aid0 = alloc.alloc()
    init = tab.admit(ProcessDescriptor(pid=0, asid=aid0, box=0, caps=0, parent_pid=None,
                                       meta={"aspace": AddressSpace(asid=aid0, pt_base_word=1536)}))
    aid1 = alloc.alloc()
    child = tab.admit(ProcessDescriptor(pid=1, asid=aid1, box=1, caps=1, parent_pid=0,
                                        meta={"aspace": AddressSpace(asid=aid1, pt_base_word=1536)}))
    tab.transition(1, STATE_RUNNING)
    tab.mark_exited(1, 42)
    print(f"ready={tab.ready_set()} zombies={tab.zombies()} children_of(0)={tab.children_of(0)}")
    print(f"reap(1) -> {tab.reap(1)}  state={tab.procs[1].state}")
    try:
        tab.transition(1, STATE_RUNNING)
    except InvalidTransition as exc:
        print(f"refused dead->running: {exc}")
    set_asid_allocator(None)
