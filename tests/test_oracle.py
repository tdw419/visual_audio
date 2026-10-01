#!/usr/bin/env python3
"""Tests for oracle.run_oracle — the GH-12 execution-verification gate.

The oracle is the contract gate in the escalation loop: candidate .glyph
text assembled, executed on GlyphCPUv2, checked word-exactly. These tests
pin: (1) a trivially correct program passes, (2) a wrong-result program
fails with the exact reg triple, (3) an assemble-fault candidate fails
cleanly (never raises), (4) a non-halting candidate is caught, (5) seed
memory reaches the program (argv pattern).
"""
import sys
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_TOOLS))
sys.path.insert(0, str(_TOOLS / "tools"))

from glyph_gpt.oracle import OracleResult, run_oracle  # noqa: E402


POP_R1_INTO_R2 = """
; contract: popcount(r1) -> r2  (loop, shift, add)
LDI r2 0
LDI r3 32
:__loop
JZ :__done r1
SHR r1 r1 1
SLT r4 r31 r1
ADD r2 r2 r1
ADDI r3 r3 -1
JNZ :__loop r3
:__done
HALT
"""


def test_oracle_happy_path_assembles_executes_and_passes():
    res = run_oracle("LDI r2 42\nHALT\n", expect_registers={2: 42})
    assert res.passed, res.error
    assert res.steps >= 2
    assert res.registers[2] == 42
    assert res.memory_hash, "memory hash (VCC) must be present on pass"


def test_oracle_wrong_result_fails_with_exact_triple():
    res = run_oracle("LDI r2 42\nHALT\n", expect_registers={2: 43})
    assert not res.passed
    # exact golden/got/step triple so the drafting model self-corrects
    assert res.error == "contract: expected r2=0x0000002b, got 0x0000002a at step 2", res.error


def test_oracle_assemble_fault_fails_cleanly_never_raises():
    res = run_oracle("BOGUS r1 r2 r9\n", expect_registers={1: 1})
    assert not res.passed
    assert res.error and res.error.startswith("assemble:"), res.error


def test_oracle_non_halting_program_is_caught():
    res = run_oracle(":__spin\nJMP :__spin\n", max_instructions=500)
    assert not res.passed
    assert "no-halt" in res.error, res.error


def test_oracle_seed_memory_reaches_program():
    # load word[100] (seeded 0xDEADBEEF) and store to word[101]
    src = (
        "LDI r10 100\n"
        "LD r11 r10\n"
        "LDI r12 101\n"
        "ST r12 r11\n"
        "HALT\n"
    )
    res = run_oracle(src, seed_memory={100: 0xDEADBEEF},
                     expect_registers={11: 0xDEADBEEF})
    assert res.passed, res.error
