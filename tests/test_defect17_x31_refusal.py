#!/usr/bin/env python3
"""tests/test_defect17_x31_refusal.py — DEFECT-17 option (d) loud refusal gate for RV x31 (t6).

Ruling: .builder_queue/RULING_20260912_defect18_a_defect17_d.md § Decision 2.
Defect: .builder_queue/REPAIR_PENDING_defect17_x31_hw_stack.md.

Glyph ISA r31 is the dedicated hardware call stack pointer (CALL/RET/PUSH/POP).
Under the transpiler's identity register map (RV xN -> Glyph rN), any instruction
referencing RV x31 (t6) lowers onto r31 and destroys the hardware call stack.
Option (d) enforces a loud refusal gate: transpile_rv32i_to_glyph() statically
scans text section instructions and loudly refuses x31 references with
RVX31RefusalError, following the REFUSAL: RV x31 discipline.

Gate Legs:
  L1: Library refusal — hand-assembled RV32I words for `li t6, 90; ret` raise
      RVX31RefusalError, message contains "REFUSAL: RV x31", names pc/word/role.
      Catchable as distinct type. All operand roles (dest, src1, src2) verified.
  L2: No false positive / no regression — clean inputs transpile without raising;
      post-change emission matches pre-scan goldens byte-for-byte across multiple
      real corpus inputs.
  L3: CLI refusal — subprocess CLI on x31 fixture exits non-zero with "REFUSAL: RV x31"
      on stderr; on clean fixture exits 0 with output on stdout.
  L4: Corpus stays clean tripwire — measured scan over real gate corpora (BK-1 C main
      + rt0 shim, BK-11 coreutils tools) reports 0 x31 references over >1,000 instructions.
"""

from __future__ import annotations

import struct
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List

import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import rv64i_to_glyph as r2g
from rv64i_to_glyph import (
    RVX31Record,
    RVX31RefusalError,
    parse_elf,
    scan_rv_x31_references,
    transpile_elf_to_glyph,
    transpile_rv32i_to_glyph,
)

FIXTURES_DIR = _REPO / "tests" / "fixtures"


# ==============================================================================
# Helpers
# ==============================================================================

def _encode_addi(rd: int, rs1: int, imm: int) -> int:
    """Encode RV32I addi instruction."""
    imm12 = imm & 0xFFF
    return (imm12 << 20) | ((rs1 & 0x1F) << 15) | (0 << 12) | ((rd & 0x1F) << 7) | 0x13


def _encode_add(rd: int, rs1: int, rs2: int) -> int:
    """Encode RV32I add instruction."""
    return (0 << 25) | ((rs2 & 0x1F) << 20) | ((rs1 & 0x1F) << 15) | (0 << 12) | ((rd & 0x1F) << 7) | 0x33


def _encode_ret() -> int:
    """Encode RV32I ret (jalr x0, 0(x1))."""
    return (0 << 20) | (1 << 15) | (0 << 12) | (0 << 7) | 0x67


# ==============================================================================
# Leg 1: Library refusal on hand-assembled RV32I words
# ==============================================================================

def test_l1_library_refusal_hazard_x31_dest():
    """L1: `li t6, 90; ret` (hazard on rd=x31) raises RVX31RefusalError."""
    # Hand-assembled RV32I words:
    # addi x31, x0, 90 (0x05a00f93)
    # jalr x0, 0(x1)   (0x00008067)
    w_hazard = _encode_addi(rd=31, rs1=0, imm=90)
    w_ret = _encode_ret()
    hazard_bytes = struct.pack("<II", w_hazard, w_ret)

    # Distinct exception type catchable via pytest.raises
    with pytest.raises(RVX31RefusalError) as exc_info:
        transpile_rv32i_to_glyph(hazard_bytes, entry_symbol=None, use_ir=False, cols_instrs=16)

    err = exc_info.value
    msg = str(err)

    # Literal substring required by specification
    assert "REFUSAL: RV x31" in msg, f"Missing literal refusal prefix in: {msg}"

    # Names offending pc, hex word, and role
    assert "0x0" in msg, f"Offending pc not named in: {msg}"
    assert "0x05a00f93" in msg, f"Offending hex word not named in: {msg}"
    assert "dest" in msg, f"Offending role not named in: {msg}"
    assert "hardware call stack" in msg, f"Explanation missing in: {msg}"

    # Verify structured record details
    assert len(err.violations) == 1
    rec = err.violations[0]
    assert rec.pc == 0
    assert rec.word == w_hazard
    assert rec.op == "addi"
    assert rec.roles == ("dest",)
    assert rec.role == "dest"


def test_l1_library_refusal_nonzero_base_pc():
    """L1: Scan accurately accounts for base_addr in reported pc."""
    w_hazard = _encode_addi(rd=31, rs1=0, imm=42)
    w_ret = _encode_ret()
    hazard_bytes = struct.pack("<II", w_ret, w_hazard)  # hazard at offset +4
    base = 0x80000000

    with pytest.raises(RVX31RefusalError) as exc_info:
        transpile_rv32i_to_glyph(hazard_bytes, base_addr=base, entry_symbol=None, use_ir=False, cols_instrs=16)

    err = exc_info.value
    msg = str(err)
    expected_pc_hex = hex(base + 4)
    assert expected_pc_hex in msg
    assert err.first_violation is not None
    assert err.first_violation.pc == base + 4


def test_l1_library_refusal_all_roles():
    """L1: Scan detects x31 in dest (rd), src1 (rs1), src2 (rs2), and combined."""
    # 1. src1 role: addi a0, x31, 1
    w_src1 = _encode_addi(rd=10, rs1=31, imm=1)
    b_src1 = struct.pack("<II", w_src1, _encode_ret())
    with pytest.raises(RVX31RefusalError) as exc_info:
        transpile_rv32i_to_glyph(b_src1, entry_symbol=None, use_ir=False, cols_instrs=16)
    assert "src1" in exc_info.value.violations[0].roles

    # 2. src2 role: add a0, x0, x31
    w_src2 = _encode_add(rd=10, rs1=0, rs2=31)
    b_src2 = struct.pack("<II", w_src2, _encode_ret())
    with pytest.raises(RVX31RefusalError) as exc_info:
        transpile_rv32i_to_glyph(b_src2, entry_symbol=None, use_ir=False, cols_instrs=16)
    assert "src2" in exc_info.value.violations[0].roles

    # 3. dest + src1 + src2 combined: add x31, x31, x31
    w_all = _encode_add(rd=31, rs1=31, rs2=31)
    b_all = struct.pack("<II", w_all, _encode_ret())
    with pytest.raises(RVX31RefusalError) as exc_info:
        transpile_rv32i_to_glyph(b_all, entry_symbol=None, use_ir=False, cols_instrs=16)
    assert exc_info.value.violations[0].roles == ("dest", "src1", "src2")


def test_l1_scan_skips_unsupported_or_data():
    """L1: decode_instruction returning None is skipped, never treated as a hit."""
    # 0x00000000 is invalid / unmapped in rv64i_decode
    unknown_word = 0x00000000
    ret_word = _encode_ret()
    b = struct.pack("<II", unknown_word, ret_word)
    # Scan should not find any x31 references
    violations = scan_rv_x31_references(b)
    assert len(violations) == 0


# ==============================================================================
# Leg 2: No false positive & byte-exact golden regression
# ==============================================================================

def test_l2_clean_hand_assembled_no_false_positive():
    """L2: Same program without x31 (addi a0, x0, 90; ret) transpiles without raising."""
    w_clean = _encode_addi(rd=10, rs1=0, imm=90)
    w_ret = _encode_ret()
    clean_bytes = struct.pack("<II", w_clean, w_ret)

    out = transpile_rv32i_to_glyph(clean_bytes, entry_symbol=None, use_ir=False, cols_instrs=16)
    golden_path = FIXTURES_DIR / "defect17_clean_raw_golden.glyph"
    expected = golden_path.read_text()
    assert out == expected, "Post-change output differed from pre-change golden!"


def test_l2_clean_elf_fixture_byte_exact():
    """L2: Committed clean ELF fixture matches pre-change golden byte-for-byte."""
    clean_elf_path = FIXTURES_DIR / "defect17_clean.elf"
    assert clean_elf_path.exists(), f"Missing clean fixture ELF: {clean_elf_path}"

    out = transpile_elf_to_glyph(clean_elf_path)
    golden_path = FIXTURES_DIR / "defect17_clean_golden.glyph"
    expected = golden_path.read_text()
    assert out == expected, "Transpiled clean ELF did not match golden output!"


def test_l2_bk1_argv_c_main_golden_byte_exact():
    """L2: BK-1 C main + rt0 shim transpiles byte-identical to pre-scan golden."""
    import tests.test_bk1_argv as bk1

    with tempfile.TemporaryDirectory() as td:
        base, text, symbols = bk1._compile_c_elf(Path(td))
        symbols_f = {a: n for a, n in symbols.items() if not n.startswith("$")}
        out = transpile_rv32i_to_glyph(
            text_bytes=text,
            symbols=symbols_f,
            base_addr=base,
            entry_symbol="_start",
            cols_instrs=bk1.COLS_INSTRS,
            use_ir=False,
        )

    golden_path = FIXTURES_DIR / "defect17_bk1_golden.glyph"
    expected = golden_path.read_text()
    assert out == expected, "BK-1 argv transpilation output changed from golden!"


# ==============================================================================
# Leg 3: CLI refusal leg via subprocess
# ==============================================================================

def test_l3_cli_refusal_on_hazard_elf():
    """L3: CLI on x31 fixture ELF exits non-zero and writes REFUSAL: RV x31 to stderr."""
    hazard_elf = FIXTURES_DIR / "defect17_hazard_x31.elf"
    assert hazard_elf.exists()

    proc = subprocess.run(
        [sys.executable, str(_REPO / "tools" / "rv64i_to_glyph.py"), str(hazard_elf)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0, f"Expected non-zero exit, got {proc.returncode}"
    assert "REFUSAL: RV x31" in proc.stderr, f"Expected refusal on stderr, got: {proc.stderr}"
    assert "0x0" in proc.stderr
    assert "hardware call stack" in proc.stderr


def test_l3_cli_refusal_on_hazard_raw():
    """L3: CLI with --raw on x31 raw fixture exits non-zero with refusal on stderr."""
    hazard_raw = FIXTURES_DIR / "defect17_hazard_x31_raw.bin"
    assert hazard_raw.exists()

    proc = subprocess.run(
        [sys.executable, str(_REPO / "tools" / "rv64i_to_glyph.py"), "--raw", str(hazard_raw)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "REFUSAL: RV x31" in proc.stderr


def test_l3_cli_success_on_clean_elf():
    """L3: CLI on clean fixture ELF exits 0 with message on stdout."""
    clean_elf = FIXTURES_DIR / "defect17_clean.elf"
    assert clean_elf.exists()

    with tempfile.TemporaryDirectory() as td:
        out_file = Path(td) / "out.glyph"
        proc = subprocess.run(
            [sys.executable, str(_REPO / "tools" / "rv64i_to_glyph.py"), str(clean_elf), "-o", str(out_file)],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, f"Clean CLI failed: {proc.stderr}"
        assert "Transpiled Glyph assembly saved to" in proc.stdout
        assert out_file.exists()
        golden = (FIXTURES_DIR / "defect17_clean_golden.glyph").read_text()
        assert out_file.read_text() == golden


# ==============================================================================
# Leg 4: Corpus stays clean tripwire (measured count, not comment)
# ==============================================================================

def test_l4_corpus_stays_clean_tripwire():
    """L4: Scan reports zero x31 references on gate corpus inputs (>1,000 instrs scanned)."""
    import tests.test_bk1_argv as bk1
    import tools.glyph_gpt.coreutils_port as cp

    total_instructions_scanned = 0
    total_violations = 0

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # 1. BK-1 C main + rt0 shim
        base, text, symbols = bk1._compile_c_elf(tmp)
        violations_bk1 = scan_rv_x31_references(text, base_addr=base)
        n_bk1 = len(text) // 4
        total_instructions_scanned += n_bk1
        total_violations += len(violations_bk1)
        assert len(violations_bk1) == 0, f"BK-1 unexpectedly referenced x31: {violations_bk1}"

        # 2. BK-11 coreutils tools: cat, echo, wc, cmp, head across fixtures
        tools_to_check = ["cat", "echo", "wc", "cmp", "head"]
        for tool in tools_to_check:
            for fx_name in cp.COREUTILS_FIXTURES[tool]:
                elf_bytes = cp.coreutils_tool_elf(tool, fx_name, tmp)
                base_addr, text_bytes, syms = parse_elf(elf_bytes)
                violations = scan_rv_x31_references(text_bytes, base_addr=base_addr)
                n_instrs = len(text_bytes) // 4
                total_instructions_scanned += n_instrs
                total_violations += len(violations)
                assert len(violations) == 0, f"{tool}/{fx_name} referenced x31: {violations}"

    # Falsifiability tripwire check:
    # Must have measured a non-trivial corpus (> 1,000 instructions)
    assert total_instructions_scanned > 1000, (
        f"Tripwire corpus too small: scanned only {total_instructions_scanned} instructions"
    )
    # Must have zero x31 references across the entire gate corpus
    assert total_violations == 0, f"Found {total_violations} x31 references in gate corpus"

    # Tripwire sensitivity check: if x31 is present, scan MUST report non-zero
    dummy_hazard = struct.pack("<I", _encode_addi(31, 0, 1))
    assert len(scan_rv_x31_references(dummy_hazard)) == 1
