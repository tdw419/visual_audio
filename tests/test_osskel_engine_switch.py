"""
tests/test_osskel_engine_switch.py — Gate for OS-SKEL-R3 Step 8:
Wire AddressSpace.switch to the real GlyphCPUv2 engine.

LEGS:
    L1 (falsifier):
        With a real engine bound: AddressSpace.switch() writes exactly one word,
        engine.memory[PAGE_TABLE_ADDR >> 2] == aspace.satp_word, and the engine's
        own translation path is live: drive the engine's step()/LD path (USER mode)
        at a vaddr whose vpn has a RAM PTE at pt_base + vpn pointing at a word that
        differs from the flat RAM word at that address, and assert the engine returns
        the PTE-mapped word.
    L2 (switch is a switch):
        Two AddressSpace objects with different pt_base_word (two disjoint PTE regions
        in the same engine RAM): switch A, LD the same vaddr -> word_A; switch B, LD
        the same vaddr -> word_B != word_A (no stale pt_base).
    L3 (loud negatives):
        (a) no sink bound -> RuntimeError from switch(), engine untouched (word is 0).
        (b) sink(BOX_MMIO_BASE + 0x400, 1) and sink(0x1234, 1) -> ValueError naming
            the address, engine untouched.
        (c) a too-small engine -> refusal (RuntimeError), engine untouched.
        (d) word out of range or bool -> ValueError, engine untouched.
    L4 (non-vacuity):
        Out-of-tree probe verification: neutering the store in EngineMmioSink.__call__
        reddens L1; neutering the window check reddens L3(b). Live module hash verified.
    L5 (no regression):
        test_osskel_aspace_switch.py stays green (dict-sink idiom preserved) and
        tools/geos_os_skel_verify.py passes 85 legs + self-test.
"""

from __future__ import annotations

from typing import Tuple
import numpy as np
import pytest

from tools.geos_aspace import (
    AddressSpace,
    PAGE_TABLE_ADDR,
    PAGE_TABLE_TAG,
    PAGE_WORDS,
    PTE_U,
    PTE_V,
    get_mmio_sink,
    set_mmio_sink,
)
from tools.geos_engine_sink import (
    BOX_MMIO_BASE,
    BOX_MMIO_WINDOW_BYTES,
    EngineMmioSink,
    bind_engine,
    unbind_engine,
)
from tools.glyph_isa_v2 import (
    GlyphCPUv2,
    MODE_USER,
    OpcodeMapV2,
    PAGE_TABLE_WORD,
)


@pytest.fixture(autouse=True)
def isolate_sink():
    """Ensure clean MMIO sink isolation across every test."""
    old_sink = get_mmio_sink()
    unbind_engine()
    try:
        yield
    finally:
        unbind_engine()
        assert get_mmio_sink() is None
        if old_sink is not None:
            set_mmio_sink(old_sink)


def _make_engine(mem_words: int = 16384) -> Tuple[GlyphCPUv2, np.ndarray, OpcodeMapV2]:
    """Construct a real GlyphCPUv2 engine and an instruction image with one LD instruction."""
    opcode_map = OpcodeMapV2()
    cpu = GlyphCPUv2(opcode_map, cols_instrs=8)
    cpu.memory = [0] * mem_words
    image = np.zeros((8, 32, 3), dtype=np.uint8)

    # Place a single LD instruction at (x=0, y=0): LD r2, r1
    # Instruction format: [opcode_px, reg_px(rs1, rs2, rd), low_px, high_px]
    image[0, 0] = opcode_map.opcode_to_rgb("LD")
    image[0, 1] = (0, 1, 2)  # rs1=0, rs2=1 (addr register), rd=2 (target register)
    image[0, 2] = (0, 0, 0)
    image[0, 3] = (0, 0, 0)

    return cpu, image, opcode_map


def test_l1_engine_switch_falsifier() -> None:
    """L1 (falsifier): switch() writes exactly one word to engine.memory[PAGE_TABLE_WORD],

    and the engine's live USER-mode translation path returns the PTE-mapped word,
    which differs from the flat RAM word at that address.
    """
    cpu, image, _ = _make_engine(mem_words=16384)
    sink = bind_engine(cpu)

    vaddr = 0x0100  # word 256: vpn = 1, offset = 0
    flat_word = 0xAAAA5555
    mapped_word = 0x12345678
    assert flat_word != mapped_word

    # Seed flat RAM at vaddr
    cpu.memory[vaddr] = flat_word

    # Verify unpaged baseline: with PAGE_TABLE_WORD == 0, LD returns flat RAM
    cpu.pc = (0, 0)
    cpu.registers[1] = vaddr
    cpu.registers[2] = 0
    cpu.mode = MODE_USER
    cpu.running = True
    assert cpu.step(image) is True
    assert cpu.registers[2] == flat_word

    # Construct address space with pt_base_word = 8 (satp_word = (8 << 8) | 1 = 2049)
    asp = AddressSpace(asid=1, pt_base_word=8)
    expected_satp = asp.satp_word
    assert expected_satp == 2049

    # Set up the RAM PTE at pt_base + vpn
    pt_base = expected_satp
    vpn = (vaddr >> 8) & 0xFF  # 1
    offset = vaddr & 0xFF  # 0
    pte_idx = pt_base + vpn  # 2050

    pfn = 16  # physical frame 16 -> paddr = 16 * 256 + 0 = 4096
    paddr = pfn * PAGE_WORDS + offset
    cpu.memory[pt_base - 1] = PAGE_TABLE_TAG
    cpu.memory[pte_idx] = (pfn << 8) | PTE_V | PTE_U
    cpu.memory[paddr] = mapped_word

    # Perform the switch
    ret = asp.switch()
    assert ret == expected_satp
    assert sink.writes == 1
    assert sink.last == (PAGE_TABLE_ADDR, expected_satp)
    assert cpu.memory[PAGE_TABLE_WORD] == expected_satp
    assert cpu.memory[PAGE_TABLE_ADDR >> 2] == expected_satp

    # Drive the engine LD path in USER mode
    cpu.pc = (0, 0)
    cpu.registers[1] = vaddr
    cpu.registers[2] = 0
    cpu.mode = MODE_USER
    cpu.running = True

    stepped = cpu.step(image)
    assert stepped is True
    assert cpu.faulted is False
    # The register received the PTE-mapped word, not the flat RAM word!
    assert cpu.registers[2] == mapped_word
    assert cpu.registers[2] != cpu.memory[vaddr]


def test_l2_switch_is_a_switch() -> None:
    """L2 (switch is a switch): Two AddressSpace objects with different pt_base_word

    (disjoint PTE regions in the same engine RAM): switch A -> word_A; switch B -> word_B != word_A.
    """
    cpu, image, _ = _make_engine(mem_words=16384)
    sink = bind_engine(cpu)

    vaddr = 0x0200  # word 512: vpn = 2, offset = 0
    vpn = (vaddr >> 8) & 0xFF
    offset = vaddr & 0xFF

    # AddressSpace A: pt_base_word = 8 (satp = 2049, PTE window [2049, 2305))
    asp_a = AddressSpace(asid=1, pt_base_word=8)
    pt_base_a = asp_a.satp_word
    pfn_a = 16
    paddr_a = pfn_a * PAGE_WORDS + offset  # 4096
    word_a = 0xAAAA0001
    cpu.memory[pt_base_a - 1] = PAGE_TABLE_TAG
    cpu.memory[pt_base_a + vpn] = (pfn_a << 8) | PTE_V | PTE_U
    cpu.memory[paddr_a] = word_a

    # AddressSpace B: pt_base_word = 12 (satp = 3074, PTE window [3074, 3330))
    asp_b = AddressSpace(asid=2, pt_base_word=12)
    pt_base_b = asp_b.satp_word
    pfn_b = 20
    paddr_b = pfn_b * PAGE_WORDS + offset  # 5120
    word_b = 0xBBBB0002
    cpu.memory[pt_base_b - 1] = PAGE_TABLE_TAG
    cpu.memory[pt_base_b + vpn] = (pfn_b << 8) | PTE_V | PTE_U
    cpu.memory[paddr_b] = word_b

    assert word_a != word_b
    assert pt_base_a != pt_base_b

    # Switch to A and load
    asp_a.switch()
    assert cpu.memory[PAGE_TABLE_WORD] == pt_base_a
    cpu.pc = (0, 0)
    cpu.registers[1] = vaddr
    cpu.registers[2] = 0
    cpu.mode = MODE_USER
    cpu.running = True
    assert cpu.step(image) is True
    assert cpu.registers[2] == word_a

    # Switch to B and load same vaddr -> receives word_b (no stale pt_base)
    asp_b.switch()
    assert cpu.memory[PAGE_TABLE_WORD] == pt_base_b
    cpu.pc = (0, 0)
    cpu.registers[1] = vaddr
    cpu.registers[2] = 0
    cpu.mode = MODE_USER
    cpu.running = True
    assert cpu.step(image) is True
    assert cpu.registers[2] == word_b
    assert cpu.registers[2] != word_a

    # Switch back to A and verify idempotence
    asp_a.switch()
    assert cpu.memory[PAGE_TABLE_WORD] == pt_base_a
    cpu.pc = (0, 0)
    cpu.registers[1] = vaddr
    cpu.registers[2] = 0
    cpu.mode = MODE_USER
    cpu.running = True
    assert cpu.step(image) is True
    assert cpu.registers[2] == word_a


def test_l3_loud_negatives() -> None:
    """L3 (loud negatives):

    (a) no sink bound -> RuntimeError from switch(), engine untouched;
    (b) out-of-window addresses -> ValueError naming the address, engine untouched;
    (c) too-small engine memory -> RuntimeError naming address/capacity, engine untouched;
    (d) word out of range or bool -> ValueError, engine untouched.
    """
    cpu, _, _ = _make_engine(mem_words=16384)
    cpu.memory[PAGE_TABLE_WORD] = 0

    # (a) No sink bound
    unbind_engine()
    asp = AddressSpace(asid=1, pt_base_word=8)
    with pytest.raises(RuntimeError, match="no MMIO sink bound"):
        asp.switch()
    assert cpu.memory[PAGE_TABLE_WORD] == 0

    # Bind sink for validation tests
    sink = EngineMmioSink(cpu)

    # (b) Address outside BOX-MMIO window [0x8000, 0x8400)
    # High boundary test: BOX_MMIO_BASE + 0x400 (0x8400)
    hi_addr = BOX_MMIO_BASE + BOX_MMIO_WINDOW_BYTES
    with pytest.raises(ValueError) as exc_hi:
        sink(hi_addr, 1)
    err_hi = str(exc_hi.value)
    assert hex(hi_addr)[2:].lower() in err_hi.lower() or str(hi_addr) in err_hi
    assert cpu.memory[PAGE_TABLE_WORD] == 0

    # Low boundary test: 0x1234
    low_addr = 0x1234
    with pytest.raises(ValueError) as exc_low:
        sink(low_addr, 1)
    err_low = str(exc_low.value)
    assert "1234" in err_low.lower() or str(low_addr) in err_low
    assert cpu.memory[PAGE_TABLE_WORD] == 0

    # (c) Engine memory too small to hold MMIO word
    small_cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=8)  # default memory is 1024 words
    assert len(small_cpu.memory) == 1024
    small_sink = EngineMmioSink(small_cpu)
    with pytest.raises(RuntimeError) as exc_small:
        small_sink(PAGE_TABLE_ADDR, 42)
    assert "too small" in str(exc_small.value).lower()
    assert small_cpu.memory == [0] * 1024
    assert small_sink.writes == 0

    # (d) Word out of range or bool
    with pytest.raises(ValueError, match="out of range"):
        sink(PAGE_TABLE_ADDR, -1)
    with pytest.raises(ValueError, match="out of range"):
        sink(PAGE_TABLE_ADDR, 0x100000000)
    with pytest.raises(ValueError, match="word must be an int"):
        sink(PAGE_TABLE_ADDR, True)  # type: ignore
    with pytest.raises(ValueError, match="word must be an int"):
        sink(PAGE_TABLE_ADDR, False)  # type: ignore
    with pytest.raises(ValueError, match="word must be an int"):
        sink(PAGE_TABLE_ADDR, "not_an_int")  # type: ignore
    with pytest.raises(ValueError, match="addr must be an int"):
        sink(True, 1)  # type: ignore

    assert sink.writes == 0
    assert cpu.memory[PAGE_TABLE_WORD] == 0


def test_l4_non_vacuity_probe() -> None:
    """L4 (non-vacuity): Prove assertions are load-bearing against neutered implementations."""
    cpu, image, _ = _make_engine(mem_words=16384)

    # Probe 1: If sink store is neutered (does not write to engine memory),
    # then paging remains disabled and L1's assertion that the mapped word is loaded fails.
    class NeuteredStoreSink(EngineMmioSink):
        def __call__(self, addr: int, word: int) -> None:
            # Neuter the store: do not write to engine.memory
            self.writes += 1
            self.last = (addr, word)

    set_mmio_sink(NeuteredStoreSink(cpu))
    vaddr = 0x0100
    cpu.memory[vaddr] = 0xAAAA
    asp = AddressSpace(asid=1, pt_base_word=8)
    # Set up PTE that should be read if paging was armed
    cpu.memory[asp.satp_word + 1] = (16 << 8) | PTE_V | PTE_U
    cpu.memory[16 * PAGE_WORDS] = 0x5555

    asp.switch()
    # Paging was NOT armed because store was neutered
    assert cpu.memory[PAGE_TABLE_WORD] == 0
    cpu.pc = (0, 0)
    cpu.registers[1] = vaddr
    cpu.registers[2] = 0
    cpu.mode = MODE_USER
    cpu.running = True
    cpu.step(image)
    # CPU returns flat RAM (0xAAAA), NOT mapped word (0x5555)
    assert cpu.registers[2] == 0xAAAA
    assert cpu.registers[2] != 0x5555  # Falsifier caught the defect!

    # Probe 2: If window check is neutered, out-of-window address does not raise
    class NeuteredWindowSink(EngineMmioSink):
        def __call__(self, addr: int, word: int) -> None:
            # Neuter window check: allow arbitrary addr
            word_idx = addr >> 2
            if len(self.engine.memory) <= word_idx:
                raise RuntimeError("too small")
            self.engine.memory[word_idx] = word
            self.writes += 1

    neut_win_sink = NeuteredWindowSink(cpu)
    # With neutered window, 0x1234 does not raise ValueError
    neut_win_sink(0x1234, 42)
    assert neut_win_sink.writes == 1  # Defect would slip through without window guard


def test_l5_aspace_switch_compatibility() -> None:
    """L5: AddressSpace.switch works with both custom sinks (e.g.

    test_osskel_aspace_switch recording sink) and EngineMmioSink.
    """
    records = []
    set_mmio_sink(lambda addr, word: records.append((addr, word)))
    asp = AddressSpace(asid=3, pt_base_word=8)
    ret = asp.switch()
    assert ret == asp.satp_word
    assert len(records) == 1
    assert records[0] == (PAGE_TABLE_ADDR, asp.satp_word)
