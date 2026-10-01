"""tests/test_pyshader_multihart.py — PS010c structural harness.

Step 0 (this commit): image pins + stub-raise guards. The behavioral
gates REPLACE the guards one row per builder run (never delete).
"""
import sys

sys.path.insert(0, ".")

import pytest

from tools.pyshader_multihart import (
    DIVERGENT_PROG, EBREAK_WORD, GATE_LEGS, GATE_NS, HART_BLOCK_WORDS,
    LOW_PROG, MIX_PROG_LONG, MIX_PROG_SHORT, PC_OFF, RUNNING_OFF,
    STOP_BAD_OPCODE, STOP_IMEM_OOB, WG_SIZE,
    _cell_pins, _analytic_steps, gate_multihart_parity, host_reference,
    run_multihart_gpu)


def test_locked_program_texts_present():
    # The four pinned ASM texts import from the PS010b skeleton — the
    # same words, no re-derivation.
    for t in (LOW_PROG, MIX_PROG_SHORT, MIX_PROG_LONG, DIVERGENT_PROG):
        assert isinstance(t, str) and "ebreak" in t


def test_layout_constants_pinned():
    assert PC_OFF == 32 and RUNNING_OFF == 33
    assert HART_BLOCK_WORDS == 37
    assert WG_SIZE == 64
    assert EBREAK_WORD == 0x00100073
    assert STOP_IMEM_OOB == 2 and STOP_BAD_OPCODE == 3
    assert GATE_LEGS == ("uniform", "static_mix", "adversarial")
    assert GATE_NS == (2, 8, 64, 4096, 65536)


def test_host_reference_divergent_pins():
    # Behavioral gate (PS010c step 1, replaces the stub-raise guard):
    # DIVERGENT_PROG taken (x5=4): bne -> pc 3 (imm//4 spec semantics),
    # blt x0,x1 not taken (x1=0), ebreak. x1 stays 0, x5 unchanged.
    ref = host_reference(DIVERGENT_PROG, x5=4)
    assert ref["regs"][5] == 4
    assert ref["regs"][1] == 0
    # Not-taken (x5=0): the BLT spin drains x1 to 0 — same final regs.
    ref0 = host_reference(DIVERGENT_PROG, x5=0)
    assert ref0["regs"][5] == 0
    assert ref0["regs"][1] == 0


def test_ps010c_uniform_parity_n8():
    # THE step-1 gate clause (brief_ps010c_gpu_multihart.md row 1):
    # N=8 harts, all LOW_PROG, no x5 inits: rounds==5, every hart
    # steps==5, stops empty, and EVERY hart's final 32 registers are
    # bit-for-bit equal to host_reference(LOW_PROG, x5=0)'s regs.
    n = 8
    receipt = run_multihart_gpu([LOW_PROG] * n)
    assert receipt["n"] == n
    assert receipt["rounds"] == 5
    assert receipt["steps"] == [5] * n
    assert receipt["stops"] == []
    ref = host_reference(LOW_PROG, 0)
    ref_regs = [v & 0xFFFFFFFF for v in ref["regs"]]
    assert len(receipt["regs"]) == n
    for regs in receipt["regs"]:
        assert regs == ref_regs  # full 32-reg equality, not a sampled lane
    # No input mutation (texts are compiled to fresh word lists).
    assert isinstance(LOW_PROG, str)


def test_ps010c_static_mix_parity_n8():
    # THE step-2 gate clause (brief_ps010c_gpu_multihart.md row 2):
    # N=8, harts 0-3 MIX_PROG_SHORT (1 transition), harts 4-7
    # MIX_PROG_LONG (17 transitions): rounds==17, useful==4*1+4*17=72,
    # per-hart steps == [1,1,1,1,17,17,17,17], stops empty, and every
    # hart's final regs bit-for-bit == host_reference of its own
    # program.
    n = 8
    programs = [MIX_PROG_SHORT] * 4 + [MIX_PROG_LONG] * 4
    receipt = run_multihart_gpu(programs)
    assert receipt["n"] == n
    assert receipt["rounds"] == 17
    assert receipt["steps"] == [1, 1, 1, 1, 17, 17, 17, 17]
    assert sum(receipt["steps"]) == 72  # useful == 4*1 + 4*17
    assert receipt["stops"] == []
    ref_short = [v & 0xFFFFFFFF
                 for v in host_reference(MIX_PROG_SHORT, 0)["regs"]]
    ref_long = [v & 0xFFFFFFFF
                for v in host_reference(MIX_PROG_LONG, 0)["regs"]]
    assert len(receipt["regs"]) == n
    for i, regs in enumerate(receipt["regs"]):
        ref_regs = ref_short if i < 4 else ref_long
        assert regs == ref_regs  # full 32-reg equality, per own program
    # Non-vacuity leg: the swapped assignment MUST fail the per-hart
    # steps pin. (Honest boundary: both MIX programs halt with all-zero
    # regs, so the reg-equality pin alone cannot discriminate program
    # assignment — the steps pin carries the discrimination, and this
    # leg proves it can fail.)
    swapped = run_multihart_gpu([MIX_PROG_LONG] * 4 + [MIX_PROG_SHORT] * 4)
    assert swapped["steps"] != [1, 1, 1, 1, 17, 17, 17, 17]
    assert swapped["steps"] == [17, 17, 17, 17, 1, 1, 1, 1]
    # No input mutation.
    assert isinstance(MIX_PROG_SHORT, str) and isinstance(MIX_PROG_LONG, str)


def test_ps010c_adversarial_parity_n8():
    # THE step-3 gate clause (brief_ps010c_gpu_multihart.md row 3):
    # N=8, all harts DIVERGENT_PROG, x5 preloads [4,4,4,4,0,0,0,0].
    # Taken harts (x5=4): 2 counted transitions (bne taken -> blt not
    # taken -> ebreak). Not-taken harts (x5=0): 18 (the BLT spin drains
    # x1 to 0). rounds==18, useful==4*2+4*18=80, stops empty, and every
    # hart's final regs bit-for-bit == host_reference(DIVERGENT_PROG,
    # its own x5).
    #
    # RED evidence (pre-ruling GPU fault at HEAD 429b3b7a, reproduced in
    # RULING_ps010c_blt_in_divergent_prog.md): BNE-only shader faulted
    # every hart on the BLT — steps [1,1,1,1,3,3,3,3], rounds 3,
    # stops 8x (hart, 3). Unblock: commit 1de7ee86 extended the shader
    # B-type to all six funct3 verbatim from ref_ctl.
    n = 8
    x5_inits = [4, 4, 4, 4, 0, 0, 0, 0]
    receipt = run_multihart_gpu([DIVERGENT_PROG] * n, x5_inits=x5_inits)
    assert receipt["n"] == n
    assert receipt["rounds"] == 18
    assert receipt["steps"] == [2, 2, 2, 2, 18, 18, 18, 18]
    assert sum(receipt["steps"]) == 80  # useful == 4*2 + 4*18
    assert receipt["stops"] == []
    ref_taken = [v & 0xFFFFFFFF
                 for v in host_reference(DIVERGENT_PROG, 4)["regs"]]
    ref_not = [v & 0xFFFFFFFF
               for v in host_reference(DIVERGENT_PROG, 0)["regs"]]
    assert ref_taken[5] == 4 and ref_not[5] == 0  # the split IS observable
    assert len(receipt["regs"]) == n
    for i, regs in enumerate(receipt["regs"]):
        ref_regs = ref_taken if i < 4 else ref_not
        assert regs == ref_regs  # full 32-reg equality, per own x5
    # Non-vacuity leg: swapping the x5 assignment MUST swap the split —
    # proves the per-hart x5 preload actually reaches the shader (a
    # preload that silently lands as zeros would pin all harts at 18).
    swapped = run_multihart_gpu([DIVERGENT_PROG] * n,
                                x5_inits=x5_inits[::-1])
    assert swapped["stops"] == []
    assert swapped["steps"] == [18, 18, 18, 18, 2, 2, 2, 2]
    # No input mutation.
    assert isinstance(DIVERGENT_PROG, str)


def test_ps010c_gate_multihart_parity():
    # THE step-4 gate clause (brief_ps010c_gpu_multihart.md row 4):
    # gate_multihart_parity runs 3 legs x N in GATE_NS and returns a
    # receipt dict (never raises on pin mismatch). Pins:
    # (a) parity_ok True at every cell (sampled harts 0, N/2, N-1
    #     bit-for-bit vs host_reference + step-sum exact vs analytic);
    # (b) rounds match the probe pins (5/17/18) at every N;
    # (c) wall_seconds REPORTED per cell (informational — never gated).
    # The N=65536 cells must RUN (buffer ~65536*37*4 bytes) — assert the
    # cell exists with n==65536, i.e. the full buffer completed.
    receipt = gate_multihart_parity()
    assert receipt["pin_failures"] == []
    assert receipt["ok"] is True
    cells = {(c["leg"], c["n"]): c for c in receipt["cells"]}
    assert set(cells) == {(leg, n)
                          for leg in GATE_LEGS for n in GATE_NS}
    rounds_pin = {"uniform": 5, "static_mix": 17, "adversarial": 18}
    for (leg, n), c in cells.items():
        assert c["parity_ok"] is True, (leg, n, receipt["pin_failures"])
        assert c["rounds"] == rounds_pin[leg], (leg, n)
        assert c["slots"] == n * c["rounds"]
        assert c["useful"] == sum(_analytic_steps(leg, n)), (leg, n)
        assert c["wall_seconds"] >= 0.0  # pin (c): reported, not gated
    for leg in GATE_LEGS:
        big = cells[(leg, 65536)]
        assert big["n"] == 65536 and big["rounds"] == rounds_pin[leg]
    # what PASS does NOT prove: no wall-clock verdict (measurement rung),
    # no shared-dmem ordering, no divergence-cost number exists yet.


def test_gate_rejects_hardcoded_parity_mutant():
    # NON-VACUITY (brief row 4): a run that reports parity_ok hardcoded
    # True with WRONG register values must be rejected by pin (a).
    # Reproduce one real cell, corrupt a sampled hart's register, and
    # show the pin evaluator names the parity failure.
    receipt = run_multihart_gpu([LOW_PROG] * 8)
    assert _cell_pins("uniform", 8, receipt) == []
    mutant = dict(receipt)
    mutant["regs"] = [list(regs) for regs in receipt["regs"]]
    mutant["regs"][0][1] = 0xDEAD  # corrupt hart 0's x1 (a sampled hart)
    failures = _cell_pins("uniform", 8, mutant)
    assert failures, "mutant with wrong regs must NOT pass pin (a)"
    assert any("parity" in f for f in failures)
    # and the step-sum pin discriminates independently of the reg pin:
    mutant2 = dict(receipt)
    mutant2["steps"] = [4] * 8
    failures2 = _cell_pins("uniform", 8, mutant2)
    assert any("step-sum" in f for f in failures2)
