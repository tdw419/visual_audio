#!/usr/bin/env python3
"""DEFECT-23-ROOT step 1 gate: instrument the low-byte PTE acceptance misread at the paged walk.

See .builder_queue/brief_defect23root_pte_acceptance.md,
.builder_queue/RULING_defect23_pfn_ceiling.md, and
systems/GLYPH_SELF_HOSTING_ROADMAP.md:360.

This gate does NOT fix the engine (acceptance rule is Jericho's seat).
It instruments the decode defect with RED-first hypothesis tests (strict xfail L1/L2)
and non-vacuity / mechanism pin / containment legs (L3/L4/L5).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from tools.glyph_isa_v2 import PAGE_TABLE_TAG
except ImportError:
    PAGE_TABLE_TAG = 0x505447

from tools.glyph_isa_v2 import (  # noqa: E402
    FAULT_ADDR_ADDR,
    GlyphAssemblerV2,
    GlyphCPUv2,
    MODE_SUPER,
    MODE_USER,
    PAGE_TABLE_ADDR,
    OpcodeMapV2,
)

RAM_WORDS = 16384
PT_BASE = 120
VPN = 5
OFFSET = 0x5A
VADDR = (VPN << 8) | OFFSET  # 1370
VAL = 0xDEADBEEF
COLS = 16
LEGIT_FRAME_WORD = 5 * 256 + OFFSET  # 1370
BOGUS_FRAME_WORD = 9 * 256 + OFFSET  # 2394


def _drive(
    op: str,
    pte: int,
    val: int = VAL,
    mode: int = MODE_SUPER,
    pre_seed: dict[int, int] | None = None,
    tag: int | None = PAGE_TABLE_TAG,
) -> GlyphCPUv2:
    """Execute one paged LD or ST instruction using the public cpu.run()."""
    assembler = GlyphAssemblerV2(OpcodeMapV2())
    lines = [f"{op} r10 r11"] + ["HALT"] * (COLS - 1)
    image = assembler.assemble(lines, width_instrs=COLS)

    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=COLS)
    cpu.memory = [0] * RAM_WORDS
    cpu.memory[PAGE_TABLE_ADDR >> 2] = PT_BASE
    if tag is not None:
        cpu.memory[PT_BASE - 1] = tag
    cpu.memory[PT_BASE + VPN] = pte
    if pre_seed:
        for k, v in pre_seed.items():
            cpu.memory[k] = v
    cpu.mode = mode
    cpu.pc = (0, 0)
    if op == "ST":
        cpu.registers[10] = VADDR  # address in rs1
        cpu.registers[11] = val    # value in rs2
    elif op == "LD":
        cpu.registers[10] = 0      # rd
        cpu.registers[11] = VADDR  # address in rs2
    cpu.run(image, max_instructions=1)
    return cpu


@pytest.mark.xfail(
    strict=True,
    reason="DEFECT-23-ROOT step 3: engine walk unchanged (flag-bit trust); in-window slot vector closed by producer-side bake-time validate_page_table (seat ruling .builder_queue/RULING_defect23root_step3_inwindow_slots.md)",
)
def test_l1_small_pfn_garbage_st_desired_contract():
    # L1: Desired contract: a store through 0x00000907 (pfn 9, below the ceiling)
    # must fault and must leave memory[2394] != VAL.
    # Measured today: inside a tagged window, small-pfn garbage still translates.
    # Option 1 does NOT close in-window slot misdirection (seat ruling); strict xfail retained.
    cpu = _drive("ST", 0x00000907, val=VAL, mode=MODE_SUPER)
    assert cpu.faulted, "store through non-PTE word 0x00000907 must fault"
    assert cpu.memory[BOGUS_FRAME_WORD] != VAL, (
        f"store through non-PTE word 0x00000907 must not land at bogus frame {BOGUS_FRAME_WORD}"
    )


@pytest.mark.xfail(
    strict=True,
    reason="DEFECT-23-ROOT step 3: engine walk unchanged (flag-bit trust); in-window slot vector closed by producer-side bake-time validate_page_table (seat ruling .builder_queue/RULING_defect23root_step3_inwindow_slots.md)",
)
def test_l2_small_pfn_garbage_ld_desired_contract():
    # L2: Strict xfail, LD twin: an LD through 0x00000907 inside a tagged window.
    # Measured today: inside a tagged window, LD silently returns the bogus frame's word.
    cpu = _drive(
        "LD",
        0x00000907,
        mode=MODE_SUPER,
        pre_seed={LEGIT_FRAME_WORD: 0x12345678, BOGUS_FRAME_WORD: 0xCAFEBABE},
    )
    assert cpu.faulted, "load through non-PTE word 0x00000907 must fault"
    assert cpu.registers[10] != 0xCAFEBABE, (
        "load through non-PTE word 0x00000907 must not read bogus frame word"
    )


def test_l3_legit_identity_pte_stores_and_loads():
    # L3: Green non-vacuity: the legit identity PTE 0x507 stores/loads at word 1370
    # exactly, no fault, no growth — a guard that refuses legitimate mappings is not a guard.
    cpu_st = _drive("ST", (VPN << 8) | 0x7, val=VAL, mode=MODE_SUPER)
    assert not cpu_st.faulted, "legitimate identity store must not fault"
    assert len(cpu_st.memory) == RAM_WORDS, "memory must not grow for in-RAM frame"
    assert cpu_st.memory[LEGIT_FRAME_WORD] == VAL, f"word {LEGIT_FRAME_WORD} must hold VAL"

    cpu_ld = _drive(
        "LD",
        (VPN << 8) | 0x7,
        mode=MODE_SUPER,
        pre_seed={LEGIT_FRAME_WORD: 0x12345678},
    )
    assert not cpu_ld.faulted, "legitimate identity load must not fault"
    assert len(cpu_ld.memory) == RAM_WORDS, "memory must not grow for in-RAM frame"
    assert cpu_ld.registers[10] == 0x12345678, "registers[10] must hold loaded value"


def test_l4_user_mode_mechanism_pin():
    # L4: Green mechanism pin (post-ruling Option 1): in USER mode within a validly tagged
    # window, 0x01080906 (missing PTE_U) refuses while 0x01080907 (PTE_U set) translates.
    # NOTE: Post-ruling rule pins that once the window container tag is verified,
    # acceptance proceeds to flag verification (PTE_V, PTE_W, PTE_U).
    cpu_refuse = _drive("LD", 0x01080906, mode=MODE_USER)
    cpu_trans = _drive("LD", 0x01080907, mode=MODE_USER)
    assert cpu_refuse.faulted, "USER mode LD with 0x01080906 (missing PTE_U) must refuse"
    assert not cpu_trans.faulted, "USER mode LD with 0x01080907 (PTE_U set) is translated"

    # ST twin mechanism check: 0x01080906 is refused at the PTE walk, and the
    # walk site NAMES the fault (Pillar 1.2 five-site pass, landed 26a29b7:
    # LD/ST pte_invalid branches set fault_reason like their tag-mismatch
    # siblings). The reason string must identify the WALK site (pte_invalid,
    # op=ST) and must NOT be the extend-site ceiling reason — an extend-site
    # string would mean the refusal fired at the wrong site.
    # (This pin previously asserted fault_reason is None, which was true before
    # 26a29b7 named the branch; caught stale by orchestrator 2026-09-16 —
    # RED at fd24c76 before this update, see .builder_queue/DEFECT-30_*.md.)
    cpu_st_refuse = _drive("ST", 0x01080906, val=VAL, mode=MODE_USER)
    assert cpu_st_refuse.faulted, "USER mode ST with 0x01080906 (missing PTE_U) must refuse at PTE walk"
    reason = getattr(cpu_st_refuse, "fault_reason", None)
    assert reason is not None, "walk-site refusal must be named (Pillar 1.2 five-site pass)"
    assert "pte_invalid" in reason, f"reason must say pte_invalid, got {reason!r}"
    assert "op=ST" in reason, f"reason must say op=ST, got {reason!r}"
    assert "ceiling" not in reason, (
        f"refusal must be at the PTE walk, not the extend-site ceiling guard; got {reason!r}"
    )


def test_l5_ceiling_containment_still_holds():
    # L5: Green: the ceiling containment still holds for 0x01080907 (fault + len(memory) <= 16384).
    # NOTE: Pointing at tests/test_defect23_pfn_ceiling.py so containment legs are not duplicated.
    cpu = _drive("ST", 0x01080907, val=VAL, mode=MODE_SUPER)
    assert len(cpu.memory) <= RAM_WORDS, (
        f"memory grew to {len(cpu.memory)} words — ceiling containment failed"
    )
    assert cpu.faulted, "store through pfn=67593 must fault at the ceiling"
    assert cpu.fault_reason is not None and "ceiling=65536" in cpu.fault_reason, (
        f"fault_reason must report ceiling=65536, got {cpu.fault_reason}"
    )
    assert cpu.memory[FAULT_ADDR_ADDR >> 2] == (VADDR << 2) & 0xFFFFFFFF


def test_l6_untagged_window_refuses_with_named_mismatch():
    # L6: Option 1 gate — an untagged window (missing or corrupt tag at pt_base - 1)
    # must refuse through the fault path with fault_reason naming the mismatch.
    # Proves the container tag check is REQUIRED and non-vacuous.
    cpu_untagged_st = _drive("ST", (VPN << 8) | 0x7, val=VAL, mode=MODE_SUPER, tag=None)
    assert cpu_untagged_st.faulted, "store through untagged window must fault"
    assert cpu_untagged_st.fault_reason is not None, "fault_reason must be set on tag mismatch"
    assert "pt_tag_mismatch" in cpu_untagged_st.fault_reason, (
        f"fault_reason must report pt_tag_mismatch, got {cpu_untagged_st.fault_reason}"
    )
    assert cpu_untagged_st.memory[LEGIT_FRAME_WORD] != VAL, "store through untagged window must not land"

    # LD twin: untagged window must fault
    cpu_untagged_ld = _drive(
        "LD",
        (VPN << 8) | 0x7,
        mode=MODE_SUPER,
        pre_seed={LEGIT_FRAME_WORD: 0x12345678},
        tag=None,
    )
    assert cpu_untagged_ld.faulted, "load through untagged window must fault"
    assert cpu_untagged_ld.fault_reason is not None, "fault_reason must be set on tag mismatch"
    assert "pt_tag_mismatch" in cpu_untagged_ld.fault_reason, (
        f"fault_reason must report pt_tag_mismatch, got {cpu_untagged_ld.fault_reason}"
    )
    assert cpu_untagged_ld.registers[10] != 0x12345678, "load through untagged window must not read frame"

    # Corrupt tag: wrong tag must also refuse with mismatch named
    cpu_bad_tag = _drive("ST", (VPN << 8) | 0x7, val=VAL, mode=MODE_SUPER, tag=0xBAD000)
    assert cpu_bad_tag.faulted, "store through corrupt tag window must fault"
    assert cpu_bad_tag.fault_reason is not None
    assert "pt_tag_mismatch" in cpu_bad_tag.fault_reason
