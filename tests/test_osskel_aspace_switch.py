"""
tests/test_osskel_aspace_switch.py — Gate for OS-SKEL-R2 Phase 3 Step 2: AddressSpace.switch.
"""

from typing import List, Tuple
import pytest

from tools.geos_aspace import (
    AddressSpace,
    PAGE_TABLE_ADDR,
    PFN_SHIFT,
    get_mmio_sink,
    set_mmio_sink,
)


@pytest.fixture(autouse=True)
def restore_mmio_sink():
    """Ensure sink isolation across tests and verify it is unbound after each test."""
    old_sink = get_mmio_sink()
    set_mmio_sink(None)
    try:
        yield
    finally:
        set_mmio_sink(old_sink)
        assert get_mmio_sink() is None


def test_l1_one_write() -> None:
    """L1: bind recording sink; switch() returns satp_word and records exactly one (PAGE_TABLE_ADDR, satp_word)."""
    with pytest.raises(TypeError):
        set_mmio_sink(123)  # type: ignore
    with pytest.raises(TypeError):
        set_mmio_sink("not-a-callable")  # type: ignore

    records: List[Tuple[int, int]] = []
    set_mmio_sink(lambda addr, word: records.append((addr, word)))
    try:
        asp = AddressSpace(asid=1, pt_base_word=1536)
        expected_satp = (1536 << PFN_SHIFT) | 1
        assert asp.satp_word == expected_satp

        ret = asp.switch()
        assert ret == expected_satp
        assert len(records) == 1
        assert records[0] == (PAGE_TABLE_ADDR, expected_satp)
    finally:
        set_mmio_sink(None)
        assert get_mmio_sink() is None


def test_l2_idempotent_value_repeatable_call() -> None:
    """L2: switching twice records two writes, both to PAGE_TABLE_ADDR with the same word."""
    records: List[Tuple[int, int]] = []
    set_mmio_sink(lambda addr, word: records.append((addr, word)))
    try:
        asp = AddressSpace(asid=2, pt_base_word=1792)
        expected_satp = (1792 << PFN_SHIFT) | 2

        ret1 = asp.switch()
        ret2 = asp.switch()
        assert ret1 == expected_satp
        assert ret2 == expected_satp
        assert len(records) == 2
        assert records[0] == (PAGE_TABLE_ADDR, expected_satp)
        assert records[1] == (PAGE_TABLE_ADDR, expected_satp)
        assert records[0] == records[1]
    finally:
        set_mmio_sink(None)
        assert get_mmio_sink() is None


def test_l3_refusal_when_unbound() -> None:
    """L3: with no sink bound, switch() raises RuntimeError (non-vacuity vs the stub)."""
    set_mmio_sink(None)
    assert get_mmio_sink() is None
    asp = AddressSpace(asid=3, pt_base_word=1536)
    with pytest.raises(RuntimeError, match="no MMIO sink bound"):
        asp.switch()


def test_l4_addressing_and_satp_encoding() -> None:
    """L4: recorded address is PAGE_TABLE_ADDR (0x804C) and word is (pt_base_word << 8) | (asid & 0xFF)."""
    records: List[Tuple[int, int]] = []
    set_mmio_sink(lambda addr, word: records.append((addr, word)))
    try:
        assert PAGE_TABLE_ADDR == 0x8000 + 0x4C == 0x804C

        asp1 = AddressSpace(asid=0x12, pt_base_word=0x0600)
        expected_word1 = (0x0600 << 8) | 0x12
        assert asp1.satp_word == expected_word1
        asp1.switch()
        assert len(records) == 1
        assert records[0] == (PAGE_TABLE_ADDR, expected_word1)

        asp2 = AddressSpace(asid=0x34, pt_base_word=0x0700)
        expected_word2 = (0x0700 << 8) | 0x34
        assert asp2.satp_word == expected_word2
        asp2.switch()
        assert len(records) == 2
        assert records[1] == (PAGE_TABLE_ADDR, expected_word2)

        # Proves the sink gets this space's word, not a constant
        assert records[0] != records[1]
        assert records[0][0] == PAGE_TABLE_ADDR
        assert records[1][0] == PAGE_TABLE_ADDR
        assert records[0][1] == expected_word1
        assert records[1][1] == expected_word2
    finally:
        set_mmio_sink(None)
        assert get_mmio_sink() is None


def test_l5_failed_write_propagates() -> None:
    """L5: failed write in sink is not swallowed; switch() propagates the exception."""
    def failing_sink(addr: int, word: int) -> None:
        raise OSError("MMIO bus error")

    set_mmio_sink(failing_sink)
    try:
        asp = AddressSpace(asid=5, pt_base_word=1536)
        with pytest.raises(OSError, match="MMIO bus error"):
            asp.switch()
    finally:
        set_mmio_sink(None)
        assert get_mmio_sink() is None
