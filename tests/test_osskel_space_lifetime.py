"""
tests/test_osskel_space_lifetime.py — Gate for OS-SKEL-R3 Step 9:
Space lifetime ownership (ruled OPTION 1, refcount-only teardown).

Authority: .builder_queue/RULING_oskel_step9_space_lifetime.md
Roadmap:   systems/GLYPH_SELF_HOSTING_ROADMAP.md row OS-SKEL-R3-S9

Gate legs:
  L1: single free at 1->0 (counting allocator double records exactly 1 free call)
  L2: shared space survives (refcount 2, reap process -> asid still live, second drop_reference frees it)
  L3: second release still refuses (release / drop_reference on freed space raises loudly)
  L4: no double free transitively across spawn -> exit -> reap
"""

from __future__ import annotations

from typing import Dict, Optional
import pytest

from tools.geos_aspace import (
    AddressSpace,
    AsidAllocator,
    drop_reference,
    get_asid_allocator,
    get_space_source,
    set_asid_allocator,
    set_space_source,
)
from tools.geos_caps import CAP_SPAWN, CapTable, set_granter_mask
from tools.geos_devtab import Devtab
from tools.geos_proctab import (
    ProcessDescriptor,
    Proctab,
    STATE_RUNNING,
    STATE_ZOMBIE,
)
from tools.geos_spawn import BoxAllocator, spawn


class CountingAsidAllocator(AsidAllocator):
    """Allocator double recording free() calls per asid."""

    def __init__(self, capacity: int = 256) -> None:
        super().__init__(capacity)
        self.free_counts: Dict[int, int] = {}

    def free(self, asid: int) -> None:
        self.free_counts[asid] = self.free_counts.get(asid, 0) + 1
        super().free(asid)


@pytest.fixture(autouse=True)
def clean_hooks():
    """Ensure hooks are cleanly reset before and after each test."""
    old_alloc = get_asid_allocator()
    set_asid_allocator(None)
    try:
        old_source = get_space_source()
    except NameError:
        old_source = None
    if "set_space_source" in globals():
        set_space_source(None)
    set_granter_mask(None)
    try:
        yield
    finally:
        set_asid_allocator(old_alloc)
        if "set_space_source" in globals():
            set_space_source(old_source)
        set_granter_mask(None)


def test_l1_single_free_at_one_to_zero() -> None:
    """L1: space at refcount 1, reap the owning process -> asid is gone from
    allocator.live() and counting allocator double records exactly 1 free call.
    """
    alloc = CountingAsidAllocator()
    set_asid_allocator(alloc)

    asid = alloc.alloc()
    space = AddressSpace(asid=asid, pt_base_word=1536)
    set_space_source(lambda a: space if a == asid else None)

    tab = Proctab()
    desc = tab.admit(ProcessDescriptor(pid=0, asid=asid, box=0, meta={"aspace": space}))
    tab.transition(0, STATE_RUNNING)
    tab.mark_exited(0, 42)

    assert tab.reap(0) == 42
    assert asid not in alloc.live()
    assert alloc.free_counts.get(asid, 0) == 1


def test_l2_shared_space_survives() -> None:
    """L2: space at refcount 2 (second holder), reap the process -> asid still live;
    the second drop_reference frees it.
    """
    alloc = CountingAsidAllocator()
    set_asid_allocator(alloc)

    asid = alloc.alloc()
    space = AddressSpace(asid=asid, pt_base_word=1536)
    ret_pin = space.pin()
    assert ret_pin == 2
    assert space.refcount == 2

    set_space_source(lambda a: space if a == asid else None)

    tab = Proctab()
    desc = tab.admit(ProcessDescriptor(pid=0, asid=asid, box=0, meta={"aspace": space}))
    tab.transition(0, STATE_RUNNING)
    tab.mark_exited(0, 42)

    # Reaping process drops 1 reference (refcount 2 -> 1).
    assert tab.reap(0) == 42
    assert asid in alloc.live()
    assert alloc.free_counts.get(asid, 0) == 0
    assert space.refcount == 1

    # Second drop_reference frees it (refcount 1 -> 0).
    rem = drop_reference(asid)
    assert rem == 0
    assert asid not in alloc.live()
    assert alloc.free_counts.get(asid, 0) == 1
    assert space.refcount == 0


def test_l3_second_release_still_refuses() -> None:
    """L3: release() / drop_reference on a freed space still raises loudly."""
    alloc = CountingAsidAllocator()
    set_asid_allocator(alloc)

    asid = alloc.alloc()
    space = AddressSpace(asid=asid, pt_base_word=1536)
    set_space_source(lambda a: space if a == asid else None)

    # First release frees the space
    assert space.release() == 0
    assert asid not in alloc.live()

    # Second release() on the freed space refuses loudly with RuntimeError
    with pytest.raises(RuntimeError):
        space.release()

    # drop_reference on freed space also refuses loudly
    with pytest.raises((RuntimeError, KeyError)):
        drop_reference(asid)


def test_l4_no_double_free_transitively() -> None:
    """L4: across a spawn -> exit -> reap sequence with a counting allocator double,
    free is called at most once per asid, ever.
    """
    alloc = CountingAsidAllocator()
    set_asid_allocator(alloc)
    set_granter_mask(CAP_SPAWN)

    proctab = Proctab()
    captab = CapTable()
    devtab = Devtab()
    box_alloc = BoxAllocator()

    desc = spawn(proctab, captab, devtab, box_alloc, caps=CAP_SPAWN)
    asid = desc.asid
    space = desc.meta["aspace"]

    set_space_source(lambda a: space if a == asid else None)

    proctab.transition(desc.pid, STATE_RUNNING)
    proctab.mark_exited(desc.pid, 0)
    assert proctab.reap(desc.pid) == 0

    assert asid not in alloc.live()
    assert alloc.free_counts.get(asid, 0) == 1

    # Subsequent release on the space raises and does not call free a second time
    with pytest.raises(RuntimeError):
        space.release()

    assert alloc.free_counts.get(asid, 0) == 1


def test_l5_spaceless_process_refuses_loudly() -> None:
    """L5 (I5): the space owns the asid, so a descriptor that names no space is a
    malformed process — reap refuses loudly with KeyError and mutates nothing (it
    must NOT invent a default space for it, and must not free the asid)."""
    alloc = CountingAsidAllocator()
    set_asid_allocator(alloc)
    set_space_source(None)  # nothing can be resolved for this asid

    asid = alloc.alloc()
    tab = Proctab()
    tab.admit(ProcessDescriptor(pid=0, asid=asid, box=0))  # no meta["aspace"]
    tab.transition(0, STATE_RUNNING)
    tab.mark_exited(0, 7)

    with pytest.raises(KeyError, match="address space"):
        tab.reap(0)

    assert tab.procs[0].state == STATE_ZOMBIE
    assert tab.pids.live() == [0]
    assert alloc.live() == [asid]
    assert alloc.free_counts.get(asid, 0) == 0
