#!/usr/bin/env python3
"""tests/test_glyph_engine_coverage_lint.py — gate for
tools/glyph_engine_coverage_lint.py.

Falsifiable per the tool's own bug shape (see its module docstring):
two things that are supposed to move together silently stopped agreeing,
and the checker must actually fire when that happens -- not just stay
quiet because today's files happen to be clean.

Note: ROTR was previously flagged as an unimplemented-on-WGSL finding
by this checker. It is now fully implemented in wgsl_glyph_isa_v2.py
with byte-identical parity against GlyphCPUv2, bringing cross-engine
coverage to 100% clean.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_engine_coverage_lint import (              # noqa: E402
    check_opcode_coverage, check_mmio_symmetry,
    _check_mmio_symmetry_in_text, _DIFFERENT_ENGINE_ALLOWLIST,
)
from tools.glyph_gpt.baker import bake_image                # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner              # noqa: E402

# A minimal synthetic WGSL snippet with walk_st correctly box_mmio-aware
# and walk_ld NOT -- i.e. exactly BK-2's real bug, reproduced in text so
# the detector's regex/brace-matching logic is proven against a KNOWN
# corrupted case, not just today's (already-fixed) real file.
_CORRUPTED_SNIPPET = """
fn walk_ld(addr: u32, is_super: bool) -> u32 {
    let pt_base = box_mmio[PAGE_TABLE_WORD - BOX_MMIO_WORD_LO];
    if (pt_base == 0u) {
        return mem_read(addr);
    }
    return mem_read(addr);
}

fn walk_st(addr: u32, value: u32, is_super: bool) {
    let pt_base = box_mmio[PAGE_TABLE_WORD - BOX_MMIO_WORD_LO];
    if (addr >= BOX_MMIO_WORD_LO && addr < BOX_MMIO_WORD_LO + BOX_MMIO_SPAN) {
        box_mmio[addr - BOX_MMIO_WORD_LO] = value;
    } else {
        mem_write(addr, value);
    }
}
"""

_FIXED_SNIPPET = """
fn walk_ld(addr: u32, is_super: bool) -> u32 {
    if (addr >= BOX_MMIO_WORD_LO && addr < BOX_MMIO_WORD_LO + BOX_MMIO_SPAN) {
        return box_mmio[addr - BOX_MMIO_WORD_LO];
    }
    return mem_read(addr);
}

fn walk_st(addr: u32, value: u32, is_super: bool) {
    if (addr >= BOX_MMIO_WORD_LO && addr < BOX_MMIO_WORD_LO + BOX_MMIO_SPAN) {
        box_mmio[addr - BOX_MMIO_WORD_LO] = value;
    } else {
        mem_write(addr, value);
    }
}
"""


def test_mmio_symmetry_detector_fires_on_the_real_bk2_bug_shape():
    """The detector must actually catch a walk_ld/walk_st asymmetry --
    proven against a synthetic reproduction of the real BK-2 bug, not
    against today's already-fixed file."""
    findings = _check_mmio_symmetry_in_text(_CORRUPTED_SNIPPET)
    assert len(findings) == 1, findings
    assert findings[0].check == "mmio_symmetry"
    assert "walk_ld" in findings[0].detail


def test_mmio_symmetry_detector_stays_quiet_on_symmetric_code():
    """Non-vacuity in the other direction: correctly-symmetric code must
    NOT be flagged (otherwise the check is just noise)."""
    assert _check_mmio_symmetry_in_text(_FIXED_SNIPPET) == []


def test_mmio_symmetry_clean_on_the_real_engine_file():
    """Regression guard: the ACTUAL wgsl_glyph_isa_v2.py, post BK-2,
    must be clean. This is the check that would have caught BK-2's bug
    before it shipped, wired to the real file."""
    assert check_mmio_symmetry() == []


def test_opcode_coverage_allowlist_never_flags_the_parallel_family():
    """The PARALLEL_* opcodes live in a different WGSL engine on
    purpose (tools/wgsl_spatial_glyph_engine.py) -- must never appear as
    findings regardless of what else the checker finds."""
    findings = check_opcode_coverage()
    flagged = {f.detail.split("'")[1] for f in findings}
    assert not (flagged & _DIFFERENT_ENGINE_ALLOWLIST), (
        f"allowlisted opcodes wrongly flagged: {flagged & _DIFFERENT_ENGINE_ALLOWLIST}")


def test_opcode_coverage_clean_on_real_engine_files():
    """All CPU opcodes in OpcodeMapV2 must have WGSL equivalents or be on the
    different-engine allowlist. Post-ROTR implementation, coverage is 100% clean."""
    assert check_opcode_coverage() == []


def test_opcode_coverage_detector_fires_on_missing_opcode(monkeypatch):
    """Falsifiability guard: verify that the opcode coverage check actually
    flags an opcode if it is removed from WGSL _OPCODE_ORDER."""
    import tools.glyph_engine_coverage_lint as lint_mod
    real_order = lint_mod._wgsl_opcode_order()
    assert "ROTR" in real_order
    mock_order = [op for op in real_order if op != "ROTR"]
    monkeypatch.setattr(lint_mod, "_wgsl_opcode_order", lambda: mock_order)
    findings = lint_mod.check_opcode_coverage()
    flagged = {f.detail.split("'")[1] for f in findings}
    assert "ROTR" in flagged, "detector must flag ROTR when absent from WGSL _OPCODE_ORDER"


def test_rotr_cpu_wgsl_gpu_parity():
    """ROTR parity gate: ROTR executes byte-identically on GlyphCPUv2 and WGSL GPU.
    Tests zero rotation, small shift (4), wrap shift (31), and mod-32 shift (36)."""
    prog = """
    :__entry
    LDI r10 0x12345678
    LDI r11 4
    ROTR r10 r11
    LDI r12 0x00000001
    LDI r13 31
    ROTR r12 r13
    LDI r14 0x12345678
    LDI r15 36
    ROTR r14 r15
    LDI r16 0xA5A5A5A5
    LDI r17 0
    ROTR r16 r17
    HALT
    """
    with tempfile.TemporaryDirectory() as td:
        png_path = Path(td) / "rotr_test.glyph.png"
        bake_image(prog, cols_instrs=8, out_path=png_path)

        rec_cpu = GlyphRunner(png_path).run()
        rec_wgsl = GlyphRunner(png_path).run_wgsl(max_steps=100)

        assert rec_cpu["halted"] is True
        assert rec_wgsl["halted"] is True
        assert rec_cpu["registers_full"] == rec_wgsl["registers_full"], (
            f"ROTR CPU vs WGSL register mismatch:\n"
            f"CPU:  {rec_cpu['registers_full']}\n"
            f"WGSL: {rec_wgsl['registers_full']}"
        )
        assert rec_wgsl["registers_full"][10] == 0x81234567
        assert rec_wgsl["registers_full"][12] == 0x00000002
        assert rec_wgsl["registers_full"][14] == 0x81234567
        assert rec_wgsl["registers_full"][16] == 0xA5A5A5A5

