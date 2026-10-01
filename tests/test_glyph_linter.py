#!/usr/bin/env python3
"""tests/test_glyph_linter.py — gate for tools/glyph_linter.py.

Falsifiable unit tests covering all 4 recurring bug classes:
1. Packet Framing / Checksum validation (Bug 5 shape).
2. Preemption tick-window register isolation (Bug 8 shape).
3. Syscall convention enforcement (Bug 7 shape).
4. Geometry and canvas bounds checking.
5. Real file regression on agent_resident.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_linter import (
    validate_packet_word,
    check_packet_framing_text,
    check_tick_register_isolation,
    check_syscall_abi,
    check_geometry_bounds,
    lint_glyph_source,
    lint_file,
)


# ── Leg 1: Packet Framing (Bug 5 shape) ────────────────────────────────────

def test_packet_framing_validates_gh22_format():
    """validate_packet_word validates (cksum<<24)|(op<<8)|payload format."""
    # Known valid vector: op=0x11, payload=0x2A -> cksum = (17 + 42) & 0xFF = 59 = 0x3B
    valid_word = (0x3B << 24) | (0x11 << 8) | 0x2A  # 0x3B00112A
    assert validate_packet_word(valid_word) is True

    # Bug 5 corrupted literal: 0x002A112A (cksum is 0, but op=0x11, payload=0x2A)
    bug5_word = 0x002A112A
    assert validate_packet_word(bug5_word) is False


def test_packet_framing_catches_bug5_in_source():
    """Linter detects corrupted packet constant in source text."""
    corrupted_source = """
    # Bug 5: hand-packed constant without checksum
    RES_ARGV_SEED0 = 0x002A112A
    """
    findings = check_packet_framing_text(corrupted_source)
    assert len(findings) == 1
    assert findings[0].check == "packet_framing"
    assert findings[0].severity == "ERROR"
    assert "RES_ARGV_SEED0" in findings[0].detail

    fixed_source = """
    # Fixed: properly checksummed GH-22 packet (cksum = (17 + 42) & 0xFF = 0x3B)
    RES_ARGV_SEED0 = 0x3B00112A
    """
    assert check_packet_framing_text(fixed_source) == []


# ── Leg 2: Preemption Tick Register Isolation (Bug 8 shape) ────────────────

def test_tick_register_isolation_catches_bug8():
    """Tick handler writing outside r25..r28 must be flagged."""
    # Corrupted tick handler writing r15 and r13 (exact Bug 8 shape)
    bug8_tick = """
    :__entry
    JMP :__kmain
    :__ktick
    LDI r15 732
    LD r13 r15
    LDI r14 1
    ADD r13 r14
    ST r15 r13
    LDI r15 8210
    LD r30 r15
    JMPR r30
    """
    findings = check_tick_register_isolation(bug8_tick)
    assert len(findings) >= 1
    checks = [f.check for f in findings]
    assert all(c == "tick_register_isolation" for c in checks)
    details = " ".join(f.detail for f in findings)
    assert "r15" in details or "r13" in details


def test_tick_register_isolation_passes_gh16_compliant():
    """Tick handler using ONLY r25..r28 passes cleanly."""
    compliant_tick = """
    :__entry
    JMP :__kmain
    :__ktick
    LDI r25 732
    LD r26 r25
    LDI r27 1
    ADD r26 r27
    ST r25 r26
    LDI r25 8210
    LD r28 r25
    JMPR r28
    """
    assert check_tick_register_isolation(compliant_tick) == []


# ── Leg 3: Syscall ABI Enforcement (Bug 7 shape) ───────────────────────────

def test_syscall_abi_catches_missing_r17():
    """SYSCALL without preceding LDI r17 must be flagged as ERROR."""
    # Bug 7 shape: immediate given on SYSCALL, but r17 never marshaled
    bug7_task = """
    :__task_a
    LDI r10 42
    SYSCALL r12 6
    """
    findings = check_syscall_abi(bug7_task)
    assert len(findings) == 1
    assert findings[0].check == "syscall_abi"
    assert findings[0].severity == "ERROR"
    assert "r17" in findings[0].detail


def test_syscall_abi_warns_on_immediate_divergence():
    """Flag warning if SYSCALL immediate disagrees with r17."""
    divergent_task = """
    :__task_a
    LDI r17 7
    SYSCALL r12 6
    """
    findings = check_syscall_abi(divergent_task)
    assert len(findings) == 1
    assert findings[0].check == "syscall_abi"
    assert findings[0].severity == "WARNING"
    assert "disagrees" in findings[0].detail


def test_syscall_abi_passes_compliant():
    """Properly marshaled SYSCALL passes with zero findings."""
    compliant_task = """
    :__task_a
    LDI r17 6
    LDI r10 42
    SYSCALL r12 6
    """
    assert check_syscall_abi(compliant_task) == []


# ── Leg 3b: Control Flow & Unused CMP ──────────────────────────────────────

def test_unused_cmp_catches_missing_jz():
    """CMP without a subsequent JZ branch must be warned as abandoned comparison."""
    missing_jz_prog = """
    :__entry
    LDI r1 10
    LDI r2 10
    CMP r1 r2
    LDI r3 42
    HALT
    """
    from tools.glyph_linter import check_unused_cmp
    findings = check_unused_cmp(missing_jz_prog)
    assert len(findings) == 1
    assert findings[0].check == "control_flow"
    assert "never tested by JZ" in findings[0].detail

    proper_branch_prog = """
    :__entry
    LDI r1 10
    LDI r2 10
    CMP r1 r2
    JZ :__done
    LDI r3 42
    :__done
    HALT
    """
    assert check_unused_cmp(proper_branch_prog) == []


# ── Leg 4: Geometry Bounds ─────────────────────────────────────────────────

def test_geometry_bounds_detects_undefined_jump_target():
    """Jump to undefined label must be flagged as ERROR."""
    prog = """
    :__entry
    JMP :__nowhere
    HALT
    """
    findings = check_geometry_bounds(prog)
    assert len(findings) == 1
    assert findings[0].check == "geometry_bounds"
    assert findings[0].severity == "ERROR"
    assert ":__nowhere" in findings[0].detail


def test_geometry_bounds_detects_max_rows_overflow():
    """Program exceeding max_rows hard capacity must be flagged."""
    # Generate 40 instructions; at cols_instrs=4, max_rows=8 capacity is 32
    instrs = [":__entry"] + ["LDI r1 1"] * 40 + ["HALT"]
    prog = "\n".join(instrs)
    findings = check_geometry_bounds(prog, cols_instrs=4, min_rows=8, max_rows=8)
    assert any(f.severity == "ERROR" and "exceeding max_rows" in f.detail for f in findings)


# ── Leg 5: Real File Regression ────────────────────────────────────────────

def test_linter_clean_on_live_agent_resident():
    """Post-Bug 1..8 agent_resident.py module must pass tick isolation and syscall checks."""
    p = _REPO / "tools" / "glyph_gpt" / "agent_resident.py"
    if not p.exists():
        pytest.skip("agent_resident.py not present")
    findings = lint_file(p)
    # Filter for tick isolation and syscall errors in the resident module
    critical_errors = [
        f for f in findings
        if f.severity == "ERROR" and f.check in ("tick_register_isolation", "syscall_abi")
    ]
    assert critical_errors == [], f"Unexpected critical linter errors: {critical_errors}"
