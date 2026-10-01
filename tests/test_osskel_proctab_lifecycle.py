"""
tests/test_osskel_proctab_lifecycle.py — Gate for OS-SKEL-R2 Phase 3 Step 5:
Proctab.admit / mark_exited / reap (full lifecycle + asid release on reap).

Gate clause (round brief `.builder_queue/brief_osskel_r2_phase3.md`, step 5):
  spawn→run→exit(42)→reap returns 42; pid AND asid are both reusable only
  after reap; `reap` on a non-zombie raises; two children, reap both.

Mechanism under test (recorded in the round brief so step 6/7 reuse it):
  the AsidAllocator is bound at module level in `tools/geos_aspace.py`
  (`set_asid_allocator` / `get_asid_allocator`, the step-3 idiom). Since
  OS-SKEL-R3 step 9 the SPACE owns the asid: `reap` drops a reference
  (`geos_aspace.drop_reference`), which frees the asid through the allocator
  hook exactly at the 1 -> 0 transition. With no allocator bound the release
  path refuses loudly (RuntimeError) and mutates nothing, mirroring
  `AddressSpace.release` (step 3). Fixtures below name a space because I5
  makes a process without one malformed, not defaulted (step 9) — the prod
  code no longer invents one.
"""

from __future__ import annotations

import inspect

import pytest

import tools.geos_aspace as geos_aspace
import tools.geos_proctab as geos_proctab
from tools.geos_aspace import AsidAllocator, get_asid_allocator, set_asid_allocator
from tools.geos_proctab import (
    STATE_DEAD,
    STATE_NEW,
    STATE_READY,
    STATE_RUNNING,
    STATE_WAITING,
    STATE_ZOMBIE,
    InvalidTransition,
    ProcessDescriptor,
    Proctab,
)


@pytest.fixture(autouse=True)
def unbind_allocator_after_each_test():
    """Every test starts and ends with no allocator bound (the refusal default)."""
    previous = get_asid_allocator()
    set_asid_allocator(None)
    try:
        yield
    finally:
        set_asid_allocator(previous)
        assert get_asid_allocator() is None


def _spawn(tab: Proctab, alloc: AsidAllocator, pid: int, box: int, parent_pid=None) -> ProcessDescriptor:
    """Admit a process whose asid was allocated from `alloc` (step-7 shape).

    Step 9: the descriptor also names its space (I5) — the space, not the
    process table, is the asid's owner, so `reap` resolves it.
    """
    asid = alloc.alloc()
    space = geos_aspace.AddressSpace(asid=asid, pt_base_word=1536)
    return tab.admit(
        ProcessDescriptor(
            pid=pid, asid=asid, box=box, parent_pid=parent_pid, meta={"aspace": space}
        )
    )


def test_l1_lifecycle_end_to_end() -> None:
    """L1: admit (NEW->READY, pid reserved), transition READY->RUNNING,
    mark_exited(pid, 42) -> ZOMBIE holding 42 (not yet dead, not in ready_set),
    reap -> returns 42, state DEAD, asid gone from the allocator."""
    alloc = AsidAllocator()
    set_asid_allocator(alloc)
    tab = Proctab()

    desc = _spawn(tab, alloc, pid=0, box=0)
    assert desc.state == STATE_READY
    assert tab.ready_set() == [0]
    assert tab.pids.live() == [0]
    assert alloc.live() == [0]

    assert tab.transition(0, STATE_RUNNING).state == STATE_RUNNING
    assert tab.ready_set() == []

    exited = tab.mark_exited(0, 42)
    assert exited.state == STATE_ZOMBIE
    assert exited.exit_code == 42
    assert tab.zombies() == [0]
    assert tab.ready_set() == []

    assert tab.reap(0) == 42
    assert tab.procs[0].state == STATE_DEAD
    assert tab.procs[0].exit_code == 42
    assert tab.zombies() == []
    assert tab.pids.live() == []
    assert alloc.live() == []


def test_l2_pid_and_asid_reusable_only_after_reap() -> None:
    """L2: while pid 1 is an unreaped zombie, neither pid 1 nor asid 1 can be
    handed out again (alloc() returns the next free one); after reap BOTH are
    reusable, and a fresh descriptor with pid 1 / asid 1 admits cleanly."""
    alloc = AsidAllocator()
    set_asid_allocator(alloc)
    tab = Proctab()

    _spawn(tab, alloc, pid=0, box=0)
    _spawn(tab, alloc, pid=1, box=1, parent_pid=0)
    tab.transition(1, STATE_RUNNING)
    tab.mark_exited(1, 42)
    assert tab.pids.live() == [0, 1]
    assert alloc.live() == [0, 1]

    # Not reusable yet: the next free pid / asid is 2, not 1.
    assert tab.pids.alloc() == 2
    tab.pids.free(2)
    assert alloc.alloc() == 2
    alloc.free(2)

    # And the pid cannot be re-admitted while its descriptor is an unreaped zombie.
    with pytest.raises(ValueError):
        tab.admit(
            ProcessDescriptor(
                pid=1,
                asid=1,
                box=1,
                parent_pid=0,
                meta={"aspace": geos_aspace.AddressSpace(asid=1, pt_base_word=1536)},
            )
        )

    assert tab.reap(1) == 42

    # Now reusable: both allocators hand 1 back (lowest free), and a fresh
    # descriptor may take that pid+asid again.
    assert tab.pids.alloc() == 1
    tab.pids.free(1)
    assert alloc.alloc() == 1
    alloc.free(1)

    reborn = tab.admit(
        ProcessDescriptor(
            pid=1,
            asid=1,
            box=1,
            parent_pid=0,
            meta={"aspace": geos_aspace.AddressSpace(asid=1, pt_base_word=1536)},
        )
    )
    assert reborn.state == STATE_READY
    assert tab.procs[1] is reborn
    assert tab.pids.live() == [0, 1]
    assert alloc.live() == [0, 1]


def test_l3_reap_on_non_zombie_raises() -> None:
    """L3: reap refuses on READY (whose READY->DEAD edge IS legal in the
    transition table, so the zombie check must be explicit), on RUNNING and on
    WAITING — and the refusal mutates nothing (state, pid and asid all intact).
    """
    alloc = AsidAllocator()
    set_asid_allocator(alloc)
    tab = Proctab()
    _spawn(tab, alloc, pid=0, box=0)
    _spawn(tab, alloc, pid=1, box=1)
    _spawn(tab, alloc, pid=2, box=2)

    # READY
    with pytest.raises(InvalidTransition):
        tab.reap(0)
    assert tab.procs[0].state == STATE_READY

    # RUNNING
    tab.transition(1, STATE_RUNNING)
    with pytest.raises(InvalidTransition):
        tab.reap(1)
    assert tab.procs[1].state == STATE_RUNNING
    assert tab.procs[1].exit_code is None

    # WAITING
    tab.transition(2, STATE_RUNNING)
    tab.transition(2, STATE_WAITING)
    with pytest.raises(InvalidTransition):
        tab.reap(2)
    assert tab.procs[2].state == STATE_WAITING

    # Nothing was released by any refusal.
    assert tab.pids.live() == [0, 1, 2]
    assert alloc.live() == [0, 1, 2]


def test_l4_unbound_allocator_refuses_loudly_and_atomically() -> None:
    """L4: with no allocator bound, reap raises RuntimeError BEFORE mutating:
    the process stays ZOMBIE, its pid stays reserved and its asid stays live.
    Binding the allocator afterwards lets the same reap complete — no partial
    release was left behind by the refusal."""
    alloc = AsidAllocator()
    set_asid_allocator(alloc)
    tab = Proctab()
    _spawn(tab, alloc, pid=0, box=0)
    tab.transition(0, STATE_RUNNING)
    tab.mark_exited(0, 42)

    set_asid_allocator(None)
    with pytest.raises(RuntimeError):
        tab.reap(0)
    assert tab.procs[0].state == STATE_ZOMBIE
    assert tab.procs[0].exit_code == 42
    assert tab.pids.live() == [0]
    assert alloc.live() == [0]

    set_asid_allocator(alloc)
    assert tab.reap(0) == 42
    assert tab.procs[0].state == STATE_DEAD
    assert tab.pids.live() == []
    assert alloc.live() == []


def test_l5_admit_refusals_leave_the_table_untouched() -> None:
    """L5: every refuse-to-admit path is loud AND non-mutating —
    (a) a live pid is a duplicate; (b) only a NEW descriptor may be admitted;
    (c) the pid must be the lowest free pid (I1), and the failed reservation is
    rolled back; (d) no allocator bound -> RuntimeError; (e) an asid that no
    allocator handed out is a malformed process (I5)."""
    alloc = AsidAllocator()
    set_asid_allocator(alloc)
    tab = Proctab()
    _spawn(tab, alloc, pid=0, box=0)

    # (a) duplicate live pid
    with pytest.raises(ValueError):
        tab.admit(ProcessDescriptor(pid=0, asid=0, box=0))
    assert tab.procs[0].state == STATE_READY
    assert tab.pids.live() == [0]

    # (b) non-NEW descriptor
    with pytest.raises(ValueError):
        tab.admit(ProcessDescriptor(pid=1, asid=1, box=1, state=STATE_READY))
    assert tab.pids.live() == [0]
    assert 1 not in tab.procs

    # (c) pid 2 with pid 1 free: not the lowest free pid (I1), and the failed
    # reservation must not leak (pid 1 is still what alloc() hands out next).
    alloc.alloc()  # asid 1 is live, so this is not the failure under test
    with pytest.raises(ValueError):
        tab.admit(ProcessDescriptor(pid=2, asid=1, box=2))
    assert tab.pids.live() == [0]
    assert 2 not in tab.procs
    assert tab.pids.alloc() == 1
    tab.pids.free(1)

    # (e) asid that no allocator handed out
    with pytest.raises(ValueError):
        tab.admit(ProcessDescriptor(pid=1, asid=250, box=1))
    assert tab.pids.live() == [0]
    assert 1 not in tab.procs

    # (d) no allocator bound at all -> loud refusal
    set_asid_allocator(None)
    with pytest.raises(RuntimeError):
        tab.admit(ProcessDescriptor(pid=1, asid=1, box=1))
    assert tab.pids.live() == [0]
    assert 1 not in tab.procs


def test_l6_two_children_reap_both() -> None:
    """L6: parent 0 with children 1 and 2; both run and exit with distinct
    codes; reap returns each child's own code, in any order; after both reaps
    only the parent is live, and both pids+asids are reusable again."""
    alloc = AsidAllocator()
    set_asid_allocator(alloc)
    tab = Proctab()

    _spawn(tab, alloc, pid=0, box=0)
    _spawn(tab, alloc, pid=1, box=1, parent_pid=0)
    _spawn(tab, alloc, pid=2, box=2, parent_pid=0)
    assert tab.children_of(0) == [1, 2]

    tab.transition(1, STATE_RUNNING)
    tab.mark_exited(1, 11)
    tab.transition(2, STATE_RUNNING)
    tab.mark_exited(2, 22)
    assert tab.zombies() == [1, 2]

    assert tab.reap(2) == 22
    assert tab.reap(1) == 11
    assert tab.zombies() == []
    assert tab.procs[1].state == STATE_DEAD and tab.procs[2].state == STATE_DEAD
    assert tab.children_of(0) == [1, 2]
    assert tab.pids.live() == [0]
    assert alloc.live() == [0]

    # Reaped pids+asids come back lowest-free and are re-admittable.
    assert tab.pids.alloc() == 1
    tab.pids.free(1)
    assert alloc.alloc() == 1
    alloc.free(1)
    reborn = tab.admit(
        ProcessDescriptor(
            pid=1,
            asid=1,
            box=1,
            parent_pid=0,
            meta={"aspace": geos_aspace.AddressSpace(asid=1, pt_base_word=1536)},
        )
    )
    assert reborn.state == STATE_READY


def test_l7_interface_and_binding_hygiene() -> None:
    """L7: signatures/annotations are unchanged (admit(desc), reap(pid) ->
    Optional[int], mark_exited(pid, code)), no new name was exported from
    geos_proctab, and the allocator hook lives in geos_aspace (one idiom)."""
    assert list(inspect.signature(Proctab.admit).parameters) == ["self", "desc"]
    assert list(inspect.signature(Proctab.mark_exited).parameters) == ["self", "pid", "code"]
    assert list(inspect.signature(Proctab.reap).parameters) == ["self", "pid"]
    assert Proctab.reap.__annotations__.get("return") == "Optional[int]"
    assert Proctab.admit.__annotations__.get("return") == "ProcessDescriptor"

    assert "set_asid_allocator" not in geos_proctab.__all__
    assert "get_asid_allocator" not in geos_proctab.__all__
    assert set(geos_proctab.__all__) == {
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
    }
    assert geos_aspace.get_asid_allocator is get_asid_allocator
