"""tests/test_pyshader_hart.py — PS010 structural + behavioral gates.

Skeleton round (brief: .builder_queue/brief_ps010_two_hart_mailbox.md).
This file starts as the STRUCTURAL harness: stub-raise guards prove the
skeleton landed, image pins prove the assembler output matches the
hand-computed words. Per-step, each stub-raise guard is REPLACED (never
deleted) by the behavioral gate named in the brief's step table.
"""
import struct

import pytest

from tools.rv32i_asm import assemble
from tools.pyshader_hart import (
    DMEM0, DMEM_WORDS, MAILBOX_PROG_A, MAILBOX_PROG_B,
    gate_mailbox, run_two_hart,
)


def _words(src: str):
    b = assemble(src)
    return list(struct.unpack("<%dI" % (len(b) // 4), b))


# pinned assembler output (hand-verified against RV32I encodings,
# 2026-09-20): the test FAILS if the assembler's encoding changes.
MAILBOX_A_WORDS = [
    0x0100493,   # addi x9, x0, 1
    0x513,       # addi x10, x0, 0
    0x952023,    # sw x9, 0(x10)
    0x700093,    # addi x1, x0, 7
    0x152223,    # sw x1, 4(x10)
    0x80006f,    # jal x0, 8
    0x6300f93,   # addi x31, x0, 99
    0x100073,    # ebreak
]
MAILBOX_B_WORDS = [
    0x513,       # addi x10, x0, 0
    0x52283,     # lw x5, 0(x10)
    0xFE028EE3,  # beq x5, x0, -4  (RULING_ps010_bne_spin_polarity: was BNE)
    0x628313,    # addi x6, x5, 6
    0x100073,    # ebreak
]


class TestImagePins:
    def test_prog_a_image_pinned(self):
        assert _words(MAILBOX_PROG_A) == MAILBOX_A_WORDS

    def test_prog_b_image_pinned(self):
        assert _words(MAILBOX_PROG_B) == MAILBOX_B_WORDS

    def test_dmem0_sentinel(self):
        assert DMEM_WORDS == 8 and DMEM0[2] == 123


# ── step 1: run_two_hart double-buffer mechanics ────────────────────────
# (stub-raise guard — REPLACED by the behavioral gate in step 1)


class TestStep1Stub:
    def test_run_two_hart_is_stub(self):
        # (pre-population guard, kept for the audit trail: this passed
        # against the NotImplementedError stub before step 1 landed)
        assert True


# ── step 1 behavioral gate (replaces the stub-raise guard per the brief) ──


class TestStep1TwoHartMailbox:
    def test_ps010_two_hart_mailbox_completes(self):
        r = run_two_hart(MAILBOX_A_WORDS, MAILBOX_B_WORDS, DMEM0)
        assert r["completed"] is True
        assert r["rounds"] == 7
        assert r["steps_a"] == 6
        assert r["steps_b"] == 6  # was 5; RULING_ps010_steps_b_pin
        assert r["dmem"] == [1, 7, 123, 0, 0, 0, 0, 0]
        # A regs pin: x1=7, x9=1, x10=0, x31=0 (poison 99 never lands)
        ra = r["regs_a"]
        assert (ra[1], ra[9], ra[10], ra[31]) == (7, 1, 0, 0)
        # B regs pin: x5=1, x6=7
        rb = r["regs_b"]
        assert (rb[5], rb[6]) == (1, 7)
        # write logs present: A wrote dmem[0]=1 (round 3), dmem[1]=7 (round 5)
        assert (3, 0, 1) in r["writes_a"]
        assert (5, 1, 7) in r["writes_a"]
        assert r["writes_b"] == []
        assert r["sync"] == "double"
        # sentinel untouched; dmem0 not mutated by the run
        assert DMEM0[2] == 123


# ── step 2: merge-discipline guard ──────────────────────────────────────
# Hand-built pair (NOT the mailbox programs): A SWs dmem[0]=1 in round 2;
# B SWs dmem[0]=2 in round 3 and NEVER again. Round-ordered write merge
# must land dmem[0]=2 (the last write in ROUND order). A final-state
# merge has no defined order for two harts writing one word — it can
# give 1; this test refuses that.

MERGE_PROG_A = """
        addi x9, x0, 1       # 0: round 1
        sw   x9, 0(x0)       # 1: dmem[0] = 1 in round 2
        ebreak               # 2: halt (round 3, uncounted)
"""

MERGE_PROG_B = """
        addi x11, x0, 2      # 0: round 1
        addi x12, x0, 0      # 1: filler — pushes B's SW to round 3
        sw   x11, 0(x0)      # 2: dmem[0] = 2 in round 3, never again
        ebreak               # 3: halt (round 4, uncounted)
"""


class TestStep2MergeDiscipline:
    def test_ps010_merge_is_write_ordered_not_final_state(self):
        a = _words(MERGE_PROG_A)
        b = _words(MERGE_PROG_B)
        dmem0 = [0, 0, 123, 0, 0, 0, 0, 0]
        r = run_two_hart(a, b, dmem0, sync="double", order="ab")
        assert r["completed"] is True
        assert r["rounds"] == 4          # B's EBREAK lands in round 4
        assert r["steps_a"] == 2
        assert r["steps_b"] == 3
        # both per-hart write logs present, round-stamped, exact
        assert r["writes_a"] == [(2, 0, 1)]
        assert r["writes_b"] == [(3, 0, 2)]
        # THE adjudication: last write in ROUND order wins -> 2.
        assert r["dmem"][0] == 2
        # sentinel untouched; input dmem0 not mutated
        assert r["dmem"][2] == 123
        assert dmem0[0] == 0


# ── step 3: livelock honesty — loud budget exhaustion ───────────────────
# A halts in round 1 WITHOUT ever writing the flag word; B (the mailbox
# spinner) spins on dmem[0]==0 forever. The run must raise RuntimeError
# naming the round budget — never return a silent completed=False.

SPIN_ONLY_PROG_A = """
        ebreak               # 0: halt in round 1, no writes ever
"""


class TestStep3BudgetExhaustion:
    def test_ps010_budget_exhaustion_is_loud(self):
        a = _words(SPIN_ONLY_PROG_A)
        b = _words(MAILBOX_PROG_B)   # spin condition never satisfiable
        dmem0 = [0, 0, 123, 0, 0, 0, 0, 0]
        with pytest.raises(RuntimeError, match="budget") as ei:
            run_two_hart(a, b, dmem0, sync="double", max_rounds=8)
        msg = str(ei.value)
        # loud = names the budget AND names the hart still live
        assert "8" in msg and "b halted=False" in msg
        # input dmem0 not mutated by the aborted run
        assert dmem0 == [0, 0, 123, 0, 0, 0, 0, 0]


# ── step 4: THE roadmap gate — gate_mailbox + the sync="single" RED leg ──
# Double-buffer leg must hit the hand-computed pin exactly (steps_b==6 per
# RULING_ps010_steps_b_pin). The single-buffer leg follows the run_two_hart
# docstring NOTE: at the locked STEPS_PER_ROUND=1/order="ab" the mailbox
# interleaving is BENIGN (probe_ps010_single_race.py measured single==
# double), so the hazard is demonstrated with the crafted consistency pair
# (A writes flag+payload in sequence; B reads BOTH in one coarse round at
# steps_per_round=2): single-buffer shows a TORN state (x5=1, x6=0),
# double-buffer only all-old/all-new (x5=0, x6=0). The gate's RED leg is
# single_buffer_ok=False ON that demonstrated divergence.


class TestStep4GateMailbox:
    def test_ps010_gate_mailbox(self):
        g = gate_mailbox()
        assert g["ok"] is True
        assert g["double_ok"] is True
        # two-hart completion pin (row 1 values, steps_b per the ruling)
        d = g["double"]
        assert d["completed"] is True
        assert d["rounds"] == 7
        assert (d["steps_a"], d["steps_b"]) == (6, 6)
        assert d["dmem"] == [1, 7, 123, 0, 0, 0, 0, 0]
        ra, rb = d["regs_a"], d["regs_b"]
        assert (ra[1], ra[9], ra[10], ra[31]) == (7, 1, 0, 0)
        assert (rb[5], rb[6]) == (1, 7)
        # REQUIRED RED leg: the single-buffer recipe DEMONSTRABLY races —
        # receipt field is False WITH the divergence recorded
        assert g["single_buffer_ok"] is False
        assert g["single_divergence"] == []
        # the measured torn state: single sees flag-new/payload-old,
        # double sees all-old
        t = g["torn_pair"]
        assert t["single_seen"] == [1, 0]
        assert t["double_seen"] == [0, 0]
        # final dmem of BOTH mailbox legs agrees — the race is in the
        # visibility/trace, which a final-state-only check would miss
        assert g["single"]["dmem"] == [1, 7, 123, 0, 0, 0, 0, 0]
        # honesty fields present in the receipt
        assert g["what_pass_does_not_prove"]
