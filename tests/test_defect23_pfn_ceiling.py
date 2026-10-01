#!/usr/bin/env python3
"""DEFECT-23 option-2 gate — the pfn ceiling at the extend site.

Implementation of `.builder_queue/RULING_defect23_pfn_ceiling.md` (ruled 2026-09-14,
seat-CONFIRMED by Jericho same day, commit f217992). NOTE: the ruling text says
"enforce at tools/glyph_isa_v2.py:740-743"; the real extend site is the paged-ST
fallback (the only ``memory.extend`` in the engine, ~:762-764). The fault-vector
code at :740-743 is NOT the extend site — corrected in the ruling addendum.

L1 (the RED leg / falsifier): a paged store through an accidental PTE with
    pfn=526602 (one of the two bad decodes measured by
    ``.builder_queue/probe_defect23_pt_slot_writer.py``) must FAULT and must NOT
    grow ``memory`` past RAM_WORDS. On a pre-guard (or guard-deleted) tree this
    exact store materialises 526602*256 = 134,810,112 words (~1.08 GB of bare
    Python list) — the original DEFECT-23 measurement — so deleting the guard
    turns this leg RED by growth, not by exception.

L2 (legit growth survives): a store through a *legitimate* pfn=100 (paddr 25,600
    words, past RAM end) must still grow memory to cover the frame and land the
    value. The guard must bound accidental decodes, not kill grow-on-demand paging.

L3 (in-RAM identity): a store through pfn=3 (paddr inside RAM) must land with no
    growth and no fault.

What a PASS does NOT prove: the low-byte PTE validity misread (root cause) is fixed —
it is not; this is containment only. The WGSL twin is untouched (it delivers no ticks
and is not on this path; parity suites never exceed the ceiling).
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
    PAGE_TABLE_ADDR,
    PAGE_WORDS,
    OpcodeMapV2,
)

RAM_WORDS = 16384      # conventional engine RAM (see test_defect23_pt_identity.py)
CEILING_PFN = 65536    # RULING_defect23_pfn_ceiling.md — 16.7M words = 64 MiB
COLS = 16
PT_BASE = 120          # page-table base word (inside RAM, away from MMIO)
VPN = 5
OFFSET = 0x5A
VADDR = (VPN << 8) | OFFSET
VAL = 0xDEADBEEF


def _make_pte(pfn: int) -> int:
    """Plain RAM frame PTE: V|W set, no PIX/HILB, pfn in the high bits."""
    return ((pfn & 0xFFFFFF) << 8) | 0x7


def _drive(pfn: int, val: int) -> GlyphCPUv2:
    """One paged ST through a hand-installed PTE, executed via the public run()."""
    assembler = GlyphAssemblerV2(OpcodeMapV2())
    lines = ["ST r10 r11"] + ["HALT"] * (COLS - 1)
    image = assembler.assemble(lines, width_instrs=COLS)

    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=COLS)
    cpu.memory = [0] * RAM_WORDS
    cpu.memory[PAGE_TABLE_ADDR >> 2] = PT_BASE
    cpu.memory[PT_BASE - 1] = PAGE_TABLE_TAG
    cpu.memory[PT_BASE + VPN] = _make_pte(pfn)
    cpu.mode = MODE_SUPER
    cpu.pc = (0, 0)
    cpu.registers[10] = VADDR   # ST r10 r11: address in rs1, value in rs2
    cpu.registers[11] = val
    cpu.run(image, max_instructions=1)
    return cpu


def test_l1_accidental_pfn_faults_and_does_not_grow():
    cpu = _drive(526602, VAL)
    # Growth is the falsifier — assert containment FIRST, so a silent 1.08 GB
    # extend can never hide behind a later assert (it did exactly that in the
    # first RED run of this gate).
    assert len(cpu.memory) <= RAM_WORDS, (
        f"memory grew to {len(cpu.memory)} words — ceiling guard did not contain "
        "the accidental decode"
    )
    assert cpu.faulted, "store through pfn=526602 must fault at the ceiling"
    assert not cpu.running, "with no kernel handler installed the engine must halt"
    assert cpu.memory[FAULT_ADDR_ADDR >> 2] == (VADDR << 2) & 0xFFFFFFFF


def test_l2_legitimate_growth_still_lands():
    pfn = 100
    paddr = pfn * PAGE_WORDS + OFFSET  # intra-frame offset stays linear (GH-25 comment)
    cpu = _drive(pfn, VAL)
    assert not cpu.faulted, "legitimate growth past RAM must not fault"
    assert len(cpu.memory) == paddr + PAGE_WORDS
    assert cpu.memory[paddr] == VAL


def test_l3_in_ram_store_untouched():
    pfn = 3
    paddr = pfn * PAGE_WORDS + OFFSET
    cpu = _drive(pfn, VAL)
    assert not cpu.faulted
    assert len(cpu.memory) == RAM_WORDS
    assert cpu.memory[paddr] == VAL
