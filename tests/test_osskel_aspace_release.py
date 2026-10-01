"""
tests/test_osskel_aspace_release.py — Gate for OS-SKEL-R2 Phase 3 Step 3: AddressSpace.release + AsidAllocator wiring.
"""

import pytest

from tools.geos_aspace import (
    AddressSpace,
    AsidAllocator,
    get_asid_allocator,
    set_asid_allocator,
)


@pytest.fixture(autouse=True)
def restore_asid_allocator():
    """Ensure allocator isolation across tests and verify it is unbound after each test."""
    old_allocator = get_asid_allocator()
    set_asid_allocator(None)
    try:
        yield
    finally:
        set_asid_allocator(old_allocator)
        assert get_asid_allocator() is None


def test_l1_refcount_descent() -> None:
    """L1: alloc = AsidAllocator(); asp = AddressSpace(asid=alloc.alloc(), pt_base_word=1536);
    asp.pin() -> 2; release() -> 1 and the asid is still in alloc.live();
    release() -> 0 and the asid is gone from alloc.live().
    """
    alloc = AsidAllocator()
    set_asid_allocator(alloc)
    try:
        asid = alloc.alloc()
        asp = AddressSpace(asid=asid, pt_base_word=1536)
        assert asp.refcount == 1
        assert asid in alloc.live()

        # pin() -> 2
        ret_pin = asp.pin()
        assert ret_pin == 2
        assert asp.refcount == 2
        assert asid in alloc.live()

        # release() -> 1 and asid is still in alloc.live()
        ret_rel1 = asp.release()
        assert ret_rel1 == 1
        assert asp.refcount == 1
        assert asid in alloc.live()

        # release() -> 0 and asid is gone from alloc.live()
        ret_rel2 = asp.release()
        assert ret_rel2 == 0
        assert asp.refcount == 0
        assert asid not in alloc.live()
    finally:
        set_asid_allocator(None)
        assert get_asid_allocator() is None


def test_l2_freed_asid_reused_first() -> None:
    """L2: alloc three spaces (asids 0, 1, 2); release the middle one to zero;
    the next alloc() returns 1 (lowest free) — not 3 — and live() is [0, 2, 1]-as-a-set plus the new one.
    """
    alloc = AsidAllocator()
    set_asid_allocator(alloc)
    try:
        asp0 = AddressSpace(asid=alloc.alloc(), pt_base_word=1536)
        asp1 = AddressSpace(asid=alloc.alloc(), pt_base_word=1792)
        asp2 = AddressSpace(asid=alloc.alloc(), pt_base_word=2048)
        assert (asp0.asid, asp1.asid, asp2.asid) == (0, 1, 2)
        assert alloc.live() == [0, 1, 2]

        # Release the middle one (asp1) to zero
        ret = asp1.release()
        assert ret == 0
        assert asp1.refcount == 0
        assert alloc.live() == [0, 2]

        # Next alloc() returns 1 (lowest free) — not 3
        new_asid = alloc.alloc()
        assert new_asid == 1
        asp1_new = AddressSpace(asid=new_asid, pt_base_word=2304)
        assert set(alloc.live()) == {0, 1, 2}
        assert alloc.live() == [0, 1, 2]
    finally:
        set_asid_allocator(None)
        assert get_asid_allocator() is None


def test_l3_below_zero_release_raises() -> None:
    """L3: a space already at refcount 0 -> release() raises RuntimeError and the
    allocator's live() is unchanged (no double free, no state damage).
    """
    alloc = AsidAllocator()
    set_asid_allocator(alloc)
    try:
        asp = AddressSpace(asid=alloc.alloc(), pt_base_word=1536)
        other = AddressSpace(asid=alloc.alloc(), pt_base_word=1792)
        assert set(alloc.live()) == {0, 1}

        # Release asp to zero
        assert asp.release() == 0
        assert asp.refcount == 0
        assert alloc.live() == [1]

        # Space already at refcount 0: release() raises RuntimeError
        with pytest.raises(RuntimeError, match="released more times than acquired"):
            asp.release()

        # Refcount remains 0 and allocator's live() is unchanged
        assert asp.refcount == 0
        assert alloc.live() == [1]
    finally:
        set_asid_allocator(None)
        assert get_asid_allocator() is None


def test_l4_loud_refusal_unbound() -> None:
    """L4: fresh space (refcount 1), set_asid_allocator(None) -> release() raises RuntimeError
    and the refcount is unchanged — proven by binding a real allocator afterwards and
    getting a normal 1 -> 0 release that returns 0 and frees the asid.
    """
    alloc = AsidAllocator()
    asid = alloc.alloc()
    asp = AddressSpace(asid=asid, pt_base_word=1536)
    assert asp.refcount == 1
    assert asid in alloc.live()

    set_asid_allocator(None)
    assert get_asid_allocator() is None

    # release() raises RuntimeError naming the condition
    with pytest.raises(RuntimeError, match="no asid allocator bound"):
        asp.release()

    # refcount is unchanged (remains 1) and asid still in alloc.live()
    assert asp.refcount == 1
    assert asid in alloc.live()

    # Proven by binding a real allocator afterwards and getting normal 1 -> 0 release
    set_asid_allocator(alloc)
    try:
        ret = asp.release()
        assert ret == 0
        assert asp.refcount == 0
        assert asid not in alloc.live()
    finally:
        set_asid_allocator(None)
        assert get_asid_allocator() is None


def test_l5_allocator_contract_propagates() -> None:
    """L5: space whose asid the bound allocator never allocated (AddressSpace(asid=7, ...))
    -> release to zero raises KeyError from the allocator (propagated).
    """
    alloc = AsidAllocator()
    allocated_asid = alloc.alloc()
    assert allocated_asid == 0
    assert 7 not in alloc.live()

    set_asid_allocator(alloc)
    try:
        asp = AddressSpace(asid=7, pt_base_word=1536)
        assert asp.refcount == 1
        with pytest.raises(KeyError, match="not live"):
            asp.release()

        # Free failed, so refcount is NOT decremented to 0
        assert asp.refcount == 1
        assert alloc.live() == [0]
    finally:
        set_asid_allocator(None)
        assert get_asid_allocator() is None


def test_l6_binding_hygiene() -> None:
    """L6: get_asid_allocator() is None before binding, the bound object after
    set_asid_allocator(alloc), and None again after set_asid_allocator(None);
    set_asid_allocator(42) raises TypeError.
    """
    set_asid_allocator(None)
    assert get_asid_allocator() is None

    alloc = AsidAllocator()
    set_asid_allocator(alloc)
    assert get_asid_allocator() is alloc

    set_asid_allocator(None)
    assert get_asid_allocator() is None

    with pytest.raises(TypeError):
        set_asid_allocator(42)  # type: ignore

    with pytest.raises(TypeError):
        set_asid_allocator("not-an-allocator")  # type: ignore

    with pytest.raises(TypeError):
        set_asid_allocator(object())  # type: ignore

    assert get_asid_allocator() is None
