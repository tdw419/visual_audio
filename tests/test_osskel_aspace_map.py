"""
tests/test_osskel_aspace_map.py — Gate for OS-SKEL-R2 Phase 3 Step 1: AddressSpace.map / unmap.
"""

import pytest
from tools.geos_aspace import (
    AddressSpace,
    AsidAllocator,
    PTE_V,
    PTE_W,
    PTE_U,
    pte_pack,
    pte_unpack,
)


def _make_aspace() -> AddressSpace:
    alloc = AsidAllocator()
    return AddressSpace(asid=alloc.alloc(), pt_base_word=1536)


def test_l1_map_readback() -> None:
    """L1: map -> read back the PTE in entries[vpn] and unpack matches."""
    asp = _make_aspace()
    flags = PTE_V | PTE_W | PTE_U
    expected_pte = pte_pack(7, flags)
    ret = asp.map(5, 7, flags)
    assert ret is None
    assert 5 in asp.entries
    assert asp.entries[5] == expected_pte
    assert pte_unpack(asp.entries[5]) == (7, flags)


def test_l2_remap_without_unmap_raises() -> None:
    """L2: remap of a live entry WITHOUT unmap raises RuntimeError; original PTE unchanged."""
    asp = _make_aspace()
    flags1 = PTE_V | PTE_U
    flags2 = PTE_V | PTE_W | PTE_U
    asp.map(5, 7, flags1)
    original_pte = pte_pack(7, flags1)
    assert asp.entries[5] == original_pte

    with pytest.raises(RuntimeError):
        asp.map(5, 8, flags2)

    assert asp.entries[5] == original_pte
    assert pte_unpack(asp.entries[5]) == (7, flags1)


def test_l3_vpn_bounds() -> None:
    """L3: vpn >= 256 raises ValueError (test 256 and large); legal vpn 255 succeeds."""
    asp = _make_aspace()
    flags = PTE_V | PTE_U

    with pytest.raises(ValueError):
        asp.map(256, 1, flags)

    with pytest.raises(ValueError):
        asp.map(1000, 1, flags)

    with pytest.raises(ValueError):
        asp.map(-1, 1, flags)

    # Legal vpn 255 succeeds
    asp.map(255, 1, flags)
    assert 255 in asp.entries
    assert pte_unpack(asp.entries[255]) == (1, flags)


def test_l4_remap_after_unmap() -> None:
    """L4: legitimate remap-after-unmap: map -> unmap (returns previous PTE) -> map new pfn succeeds."""
    asp = _make_aspace()
    flags = PTE_V | PTE_W | PTE_U
    pte1 = pte_pack(7, flags)
    pte2 = pte_pack(9, flags)

    asp.map(5, 7, flags)
    assert asp.entries[5] == pte1

    # unmap returns previous PTE, not None, not the new one
    unmapped = asp.unmap(5)
    assert unmapped == pte1
    assert unmapped is not None
    assert unmapped != pte2
    assert 5 not in asp.entries

    # Unmapping an absent vpn returns None
    assert asp.unmap(5) is None

    # remap succeeds with different pfn
    asp.map(5, 9, flags)
    assert asp.entries[5] == pte2
    assert pte_unpack(asp.entries[5]) == (9, flags)


def test_discriminator_stub_fails() -> None:
    """Discriminator: verifies that map populates entries and unmap removes them."""
    asp = _make_aspace()
    assert len(asp.entries) == 0
    asp.map(10, 20, PTE_V)
    assert 10 in asp.entries
    popped = asp.unmap(10)
    assert popped == pte_pack(20, PTE_V)
    assert 10 not in asp.entries
