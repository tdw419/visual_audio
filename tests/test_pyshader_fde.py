"""tests/test_pyshader_fde.py — PS007 skeleton structural harness.

Skeleton-driven-development contract: these tests pass on STUBS and
keep passing as bodies are populated (structural invariants only).
Behavioral gates live in the brief's step table and are added by the
builder per step, RED-first.

What this harness does NOT prove (per the skeleton contract):
- every FDE body in tools/pyshader_fde.py is still a stub
- branch execution, x0 suppression, and the Fibonacci gate are
  UNIMPLEMENTED — no test here exercises them against real behavior
- the hand-computed Fibonacci pin in the brief is reasoned, not yet
  machine-checked (that is exactly builder step 6's job)
"""
from __future__ import annotations

import pytest

from tools.pyshader_fde import (
    FIB_LOOP_COUNT_DEFAULT, PC0, REG_N, __all__ as FDE_ALL,
    execute_one, fetch, gate_fibonacci, load_program, new_state,
    run_fde,
)

# ── interface lock (frozen signatures/exports) ──────────────────────────


def test_skeleton_exports_locked_interface():
    assert set(FDE_ALL) == {
        "REG_N", "PC0", "FIB_PROGRAM", "FIB_EXPECTED_TRACE_HEAD",
        "State", "new_state", "fetch", "load_program", "execute_one",
        "run_fde", "gate_fibonacci",
    }


def test_constants_pinned():
    assert REG_N == 32
    assert PC0 == 0
    assert FIB_LOOP_COUNT_DEFAULT == 8


# ── implemented pure utilities must actually work ───────────────────────


def test_new_state_zero_filled_and_masked():
    st = new_state([0xFFFFFFFF, 1])
    assert st["pc"] == 0
    assert st["regs"][0] == 0xFFFFFFFF
    assert st["regs"][1] == 1
    assert len(st["regs"]) == 32
    assert all(v == 0 for v in st["regs"][2:])


def test_new_state_short_list_zero_fills():
    st = new_state([5])
    assert st["regs"][0] == 5 and st["regs"][31] == 0


def test_load_program_masks_words():
    prog = load_program([0xFFFFFFFF, 0x00100093])
    assert prog[0] == 0xFFFFFFFF and prog[1] == 0x00100093


# ── stubs: raise-or-noop contract is itself the structural gate ─────────


def test_ps007_fetch_bounds_and_values():
    """PS007 step 1 gate: fetch returns the right masked word for every
    in-bounds pc; out-of-bounds (>= len) and negative pc raise IndexError
    (bounds fault, NOT silent zero / silent wraparound)."""
    imem = load_program([0xFFFFFFFF, 0x00100093, 7])
    assert fetch(0, imem) == 0xFFFFFFFF
    assert fetch(1, imem) == 0x00100093
    assert fetch(2, imem) == 7
    with pytest.raises(IndexError):
        fetch(3, imem)
    with pytest.raises(IndexError):
        fetch(-1, imem)


def test_ps007_exec_addi_and_add_straightline():
    """PS007 step 2 gate: ADDI x1,x0,1 then ADD x3,x1,x2 executed from a
    fresh state (x2 preloaded to 1, mirroring the FIB program's state
    after insn 1): final state has pc=2, x1=1, x3=2, every other
    register untouched; the input state dict is NOT mutated and each
    call returns a NEW state dict (trace snapshots need the old ones)."""
    imem = load_program([
        0x00100093,  # ADDI x1, x0, 1
        0x002081B3,  # ADD   x3, x1, x2
    ])
    st = new_state()
    st["regs"][2] = 1
    snapshot = {"pc": st["pc"], "regs": list(st["regs"])}

    s1 = execute_one(st, imem)
    assert s1 is not st
    assert s1["pc"] == 1
    assert s1["regs"][1] == 1

    s2 = execute_one(s1, imem)
    assert s2 is not s1
    assert s2["pc"] == 2
    assert s2["regs"][1] == 1
    assert s2["regs"][2] == 1
    assert s2["regs"][3] == 2
    for i in range(REG_N):
        if i not in (1, 2, 3):
            assert s2["regs"][i] == 0, f"x{i} was touched"

    # the input state dict must NOT have been mutated
    assert st["pc"] == snapshot["pc"]
    assert st["regs"] == snapshot["regs"]


def test_ps007_bne_taken_and_fallthrough():
    """PS007 step 3 gate (SPEC arithmetic per RULING_ps008_branch_convention):
    BNE x5, x0, -2-insns (0xFE029CE3) executed at pc=2. TAKEN (x5!=0) →
    pc = pc + imm//4 = 2 + (-2) = 0. NOT-TAKEN (x5==0) → pc+1.
    Registers untouched by a branch; input state NOT mutated; each call
    returns a NEW state dict."""
    imem = load_program([
        0x00000000,  # 0: branch TARGET when taken (pc = 2 + (-8//4) = 0)
        0x00000000,  # 1: padding
        0xFE029CE3,  # 2: BNE x5, x0, -8   (byte imm -8 = -2 insns)
        0x00000000,  # 3: fall-through word
    ])

    # TAKEN: x5=3 != x0=0 → pc = 2 + (-8//4) = 0   (SPEC: no +1)
    st = new_state()
    st["pc"] = 2
    st["regs"][5] = 3
    snapshot = {"pc": st["pc"], "regs": list(st["regs"])}
    s_taken = execute_one(st, imem)
    assert s_taken is not st
    assert s_taken["pc"] == 0, (
        f"taken branch: expected pc=0 (2-2 SPEC), got {s_taken['pc']}"
    )
    assert s_taken["regs"] == st["regs"], "branch must not touch registers"

    # wrong-sign guard: a +8 misdecode would land at pc=4 (OOB), not pc=0
    assert s_taken["pc"] != 2 + 2, "wrong branch sign would pass +2 here"

    # old-convention guard: the superseded pc+1+imm//4 would land at pc=1
    assert s_taken["pc"] != 2 + 1 + (-2), "old +1 convention must fail here"

    # NOT-TAKEN: x5=0 == x0 → pc = 2 + 1 = 3
    st2 = new_state()
    st2["pc"] = 2
    st2["regs"][5] = 0
    s_nt = execute_one(st2, imem)
    assert s_nt is not st2
    assert s_nt["pc"] == 3, (
        f"not-taken branch: expected pc=3, got {s_nt['pc']}"
    )

    # input states must NOT have been mutated
    assert st["pc"] == snapshot["pc"] and st["regs"] == snapshot["regs"]
    assert st2["pc"] == 2 and st2["regs"][5] == 0


FIB_WORDS = [
    0x00100093,  # 0: ADDI x1, x0, 1      a = 1
    0x00100113,  # 1: ADDI x2, x0, 1      b = 1
    0x002081B3,  # 2: ADD  x3, x1, x2     loop: t = a + b
    0x00010093,  # 3: ADDI x1, x2, 0      a = b
    0x00018113,  # 4: ADDI x2, x3, 0      b = t
    0xFFF28293,  # 5: ADDI x5, x5, -1     i--
    0xFE0298E3,  # 6: BNE  x5, x0, -16    if i != 0 goto 2 (RULING:
                 #    SPEC semantics, offset -4 insns; supersedes the
                 #    ps007 -20/pc+1+imm//4 convention)
]
# All 7 words decode-verified via PS005 decode_ref this revision:
# every fmt/opcode/rd/rs1/rs2/imm field EXACT to the intent above.

FIB_X3_SEQ = [2, 3, 5, 8, 13, 21, 34, 55]
FIB_FINAL = {1: 34, 2: 55, 3: 55, 5: 0}  # x1=F9, x2=F10, x3=F10, i=0
FIB_STEPS = 42  # 2 setup + 8 * 5 loop insns (hand-computed, brief:35-38)


def test_ps007_fibonacci_gate():
    """PS007 step 6 gate: the roadmap gate. Build the pinned 7-word
    program, run_fde FIB_STEPS, then:
    1. final regs match the hand-computed pin EXACTLY (x1=34, x2=55,
       x3=55, x5=0; all other registers untouched);
    2. the x3-per-iteration sequence 2,3,5,8,13,21,34,55 appears in
       the trace, collected at the ADD commit (snapshots at pc=3);
    3. GPU leg (4-way check, PS004 lesson): the composed dispatch for
       insn 2 (ADD x3,x1,x2) and insn 6 (BNE x5,x0,-16) each verified
       via run_triple_differential + hand-computed ref on ACTUAL
       operand values sampled from the trace;
    4. trace shape: len == FIB_STEPS + 1, pcs start at 0, no OOB.
    Also: the gate_fibonacci() API itself (host leg) returns ok with
    the same final-state and sequence facts."""
    from tools.pyshader_fde import FIB_PROGRAM

    imem = load_program(FIB_PROGRAM)
    assert imem == FIB_WORDS, "FIB_PROGRAM pin drifted from the verified words"

    st = new_state()
    st["regs"][5] = FIB_LOOP_COUNT_DEFAULT  # x5 = 8 iterations
    trace = run_fde(imem, st, FIB_STEPS)

    # trace shape
    assert len(trace) == FIB_STEPS + 1
    assert trace[0]["pc"] == 0

    # 1. final register pin (hand-computed, brief:35-38)
    fin = trace[-1]
    for reg, want in FIB_FINAL.items():
        assert fin["regs"][reg] == want, (
            f"x{reg}: expected {want}, got {fin['regs'][reg]}")
    for i in range(REG_N):
        if i not in FIB_FINAL:
            assert fin["regs"][i] == 0, f"x{i} was touched"

    # 2. x3 sequence sampled at the ADD commit (pc=2 -> pc=3 snapshots)
    x3 = [snap["regs"][3] for snap in trace[1:] if snap["pc"] == 3]
    assert x3 == FIB_X3_SEQ, f"x3 sequence mismatch: {x3}"

    # 3. GPU legs on ACTUAL trace operand values (4-way: GPU, oracle,
    #    pixel CPU, hand-computed ref)
    from tools.pyshader_rvexec import run_alu_differential
    from tools.pyshader_wgsl import run_triple_differential

    # 3a. ADD x3,x1,x2 at pc=2: last iteration operands from the trace.
    #     The snapshot BEFORE the ADD (pc==2) holds a,b in x1,x2.
    add_snap = [s for s in trace if s["pc"] == 2][-1]
    a, b = add_snap["regs"][1], add_snap["regs"][2]
    r_add = run_alu_differential(True, 0, 0x00, a, b)
    assert r_add["ok"], f"ADD differential failed: {r_add}"
    assert r_add["gpu_r9"] == (a + b) & 0xFFFFFFFF  # hand-computed

    # 3b. BNE x5,x0,-16 at pc=6: first-iteration operand x5=7 (after
    #     the first decrement); taken side. GPU/ref compare on the
    #     comparison itself expressed as int(b != a) — same if-less
    #     single-statement style the PS006 step sources use.
    bne_snap = [s for s in trace if s["pc"] == 6][-2]  # a TAKEN instance
    x5v = bne_snap["regs"][5]
    assert x5v != 0, "expected a taken-branch operand sample"
    taken = 1 if x5v != 0 else 0
    r_bne = run_triple_differential(
        "def step_bne(rs1v, rs2v):\n"
        "    t = 0\n"
        "    if rs1v != rs2v:\n"
        "        t = 1\n"
        "    return t\n",
        [x5v, 0])
    assert r_bne["ok"], f"BNE differential failed: {r_bne}"
    assert r_bne["gpu_r9"] == taken  # hand-computed ref == 1
    assert r_bne["gpu_r9"] == 1, "BNE taken must dispatch 1"

    # 4. gate_fibonacci() host API
    receipt = gate_fibonacci()
    assert receipt["ok"] is True
    assert receipt["final_regs"][1] == 34 and receipt["final_regs"][2] == 55
    assert receipt["final_regs"][3] == 55 and receipt["final_regs"][5] == 0
    assert receipt["x3_sequence"] == FIB_X3_SEQ
    assert receipt["steps_executed"] == FIB_STEPS
    assert "gpu_add_ok" in receipt and "gpu_bne_ok" in receipt

    # input state never mutated by the run
    assert st["pc"] == 0 and st["regs"][5] == FIB_LOOP_COUNT_DEFAULT


def test_ps007_x0_write_suppressed():
    """PS007 step 4 gate: ADDI x0,x0,7 leaves regs[0]==0 and advances
    pc (closes the PS006 honest boundary: rd=0 writes are discarded,
    not landed). rd!=0 writes remain unaffected (control leg); input
    state NOT mutated; new state dict returned."""
    imem = load_program([
        0x00700013,  # 0: ADDI x0, x0, 7  (must be suppressed)
        0x00100093,  # 1: ADDI x1, x0, 1  (control: normal write)
    ])

    st = new_state()
    snapshot = {"pc": st["pc"], "regs": list(st["regs"])}

    # suppressed leg: rd=0 → x0 stays 0, pc advances
    s0 = execute_one(st, imem)
    assert s0 is not st
    assert s0["regs"][0] == 0, (
        f"x0-write suppression: regs[0] must stay 0, got {s0['regs'][0]}"
    )
    assert s0["pc"] == 1, f"pc must advance past the suppressed write, got {s0['pc']}"

    # control leg: rd!=0 write still lands
    s1 = execute_one(s0, imem)
    assert s1["regs"][1] == 1, f"rd!=0 write must land, got x1={s1['regs'][1]}"
    assert s1["regs"][0] == 0

    # input state NOT mutated
    assert st["pc"] == snapshot["pc"] and st["regs"] == snapshot["regs"]
    assert st["regs"][0] == 0


def test_ps007_run_fde_trace_shape():
    """PS007 step 5 gate (replaces test_run_fde_stub_raises): trace
    length == n_steps+1, trace[0] is the unmutated input state, the
    input dict is never mutated, snapshots are independent objects."""
    # NOPs (ADDI x0,x0,0 — also re-exercises x0 suppression) pad imem so
    # 3 straight-line steps stay in bounds; fetch's bounds guard is live.
    imem = load_program([0x00100093, 0x00000013, 0x00000013, 0x00000013])
    st = new_state([0, 0, 0, 7])  # x0 stays 0 (new_state does NOT force it)
    before = {"pc": st["pc"], "regs": list(st["regs"])}
    trace = run_fde(imem, st, 3)
    assert len(trace) == 3 + 1
    # trace[0] is the input state, unmutated
    assert trace[0]["pc"] == before["pc"]
    assert trace[0]["regs"] == before["regs"]
    # the input state dict is NOT mutated (deep-compare)
    assert st["pc"] == before["pc"]
    assert st["regs"] == before["regs"]
    # pc advances exactly one insn per step on straight-line code
    assert [s["pc"] for s in trace] == [0, 1, 2, 3]
    # the ADDI took effect at step 1 and is carried forward
    assert trace[1]["regs"][1] == 1
    assert trace[3]["regs"][1] == 1
    # snapshots are independent: no aliasing to the input's regs list
    st["regs"][1] = 99
    assert trace[0]["regs"][1] == 0
    assert trace[3]["regs"][1] == 1


# (test_gate_fibonacci_stub_raises REMOVED per brief hard constraints:
# the stub-raise guard is REPLACED by test_ps007_fibonacci_gate above —
# never delete a guard silently, so this note is the audit trail. The
# RED evidence it provided lives in the step-6 commit message.)


# ── one-directional checks are satisfied by raise; add bidirectional: ───
# (per skeleton contract: prove the harness's own failure path is live)


def test_harness_failure_path_is_live():
    """Self-test leg: a deliberately false assertion must FAIL — proves
    pytest is actually recording failures here (a green harness that
    can't go red verifies nothing)."""
    with pytest.raises(AssertionError):
        assert new_state()["pc"] == 99  # pc0 is pinned to 0, this is False
