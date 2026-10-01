"""Standing gate: the "5 remaining sites" classification pass (GLYPH_ISA_ROADMAP.md
Pillar 1.2, ruled 2026-09-16).

Of the 5 silent running=False fallthrough sites Claude identified (isolation-trap
class, all under the spatial page walker's kf==0 branch), 3 already set
fault_reason (the tag-mismatch faults, via check_pt_tag's tag_reason); the other
2 - LD's and ST's PTE-invalid/permission-denied branches - set faulted=True but
left fault_reason=None. Ruling: these are already correctly classified as faults
(not named halts, not "stay as-is" ambiguity) - the fix is naming them the same
way their tag-mismatch siblings already are, not changing when they fire.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_isa_v2 import (  # noqa: E402
    GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2, PAGE_TABLE_ADDR, PAGE_TABLE_TAG,
)

W = 8


def _run(prog, mem_size=16384):
    om = OpcodeMapV2()
    img = GlyphAssemblerV2(om).assemble(prog, width_instrs=W)
    cpu = GlyphCPUv2(om, cols_instrs=W)
    cpu.memory = [0] * mem_size
    pt_base = 300
    cpu.memory[PAGE_TABLE_ADDR >> 2] = pt_base
    cpu.memory[pt_base - 1] = PAGE_TABLE_TAG  # valid tag: reach the PTE-invalid branch
    # PTE itself (pt_base + vpn) left at 0 -> invalid -> faults on both LD and ST
    cpu.running = True
    while cpu.running and not cpu.faulted:
        if not cpu.step(img):
            break
    return cpu


def test_ld_pte_invalid_names_the_fault():
    cpu = _run(["LDI r1 500", "LD r5 r1", "HALT"])
    assert cpu.faulted
    assert cpu.fault_reason is not None
    assert "pte_invalid" in cpu.fault_reason
    assert "op=LD" in cpu.fault_reason


def test_st_pte_invalid_names_the_fault():
    cpu = _run(["LDI r1 500", "LDI r2 7", "ST r1 r2", "HALT"])
    assert cpu.faulted
    assert cpu.fault_reason is not None
    assert "pte_invalid" in cpu.fault_reason
    assert "op=ST" in cpu.fault_reason


def test_non_vacuity_neutered_ld_fix_leaves_reason_none():
    """Prove the LD fix is load-bearing: neuter it out-of-tree (live file
    untouched) and confirm the pre-fix bug (faulted=True, reason=None)
    reappears identically."""
    src_path = REPO / "tools" / "glyph_isa_v2.py"
    source = src_path.read_text()
    target = (
        "                        self.fault_reason = (\n"
        "                            f\"pte_invalid pte={pte:#x} vaddr={vaddr<<2:#x} \"\n"
        "                            f\"mode={'USER' if self.mode == MODE_USER else 'SUPER'} \"\n"
        "                            f\"op=LD site=glyph_isa_v2\"\n"
        "                        )\n"
    )
    assert target in source, "non-vacuity probe's anchor text is stale - re-sync with the real fix"
    neutered_source = source.replace(target, "")
    assert neutered_source != source

    mod = types.ModuleType("glyph_isa_v2_neutered_probe")
    mod.__file__ = str(src_path)
    exec(compile(neutered_source, str(src_path), "exec"), mod.__dict__)

    om = mod.OpcodeMapV2()
    img = mod.GlyphAssemblerV2(om).assemble(["LDI r1 500", "LD r5 r1", "HALT"], width_instrs=W)
    cpu = mod.GlyphCPUv2(om, cols_instrs=W)
    cpu.memory = [0] * 16384
    pt_base = 300
    cpu.memory[mod.PAGE_TABLE_ADDR >> 2] = pt_base
    cpu.memory[pt_base - 1] = mod.PAGE_TABLE_TAG
    cpu.running = True
    while cpu.running and not cpu.faulted:
        if not cpu.step(img):
            break
    assert cpu.faulted, "the neutered probe should still fault (only the reason string was removed)"
    assert cpu.fault_reason is None, (
        "expected the pre-fix bug (faulted=True, reason=None) to reappear "
        "with the fix neutered - if this fails, the fix isn't what's making "
        "the GREEN legs above pass"
    )

    # Live file is untouched - this ran entirely from an in-memory copy.
    assert src_path.read_text() == source
