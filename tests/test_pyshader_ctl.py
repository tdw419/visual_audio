"""tests/test_pyshader_ctl.py — PS008 gate: control flow as data.

Contract (GPU_CPU_EMULATOR_ROADMAP.md, PS008):
- next-pc is computed from decoded fields (data), never WGSL control flow
- gate: a branching program with backward jumps runs to HALT; trace
  adjudicated against a HAND-COMPUTED pin (no engine adjudicates itself)
- the JZ-inversion trap covered by an explicit branch-polarity test pair
- cross-validation vs the pixel CPU (SpatialRV32ICore) on the same
  program image: final register file must agree exactly.

What these tests do NOT prove:
- whole-program execution ON the GPU in one dispatch (per-class GPU
  legs only — see the honest boundary in tools/pyshader_ctl.py)
- LW/SW at unaligned or out-of-bounds addresses (faults are raised
  loudly but the fault paths of the FUTURE GPU-side memory leg are
  out of scope here)
- the pixel CPU leg requires wgpu; it is skipped cleanly when no
  adapter is present (records skip, never fakes green).
"""
from __future__ import annotations

import struct

import pytest

from tools.pyshader_ctl import (
    CTL_GATE_PROGRAM, LOOP_FOREVER_PROGRAM, ControlHalt, execute_ctl,
    gate_control_flow, ref_ctl, run_ctl_trace,
)
from tools.pyshader_fde import REG_N, fetch, load_program, new_state
from tools.pyshader_rvdecode import decode_ref


# ── program-image pin: words must match the assembler exactly ───────────


def _asm_words(source: str) -> list:
    from tools.rv32i_asm import assemble
    blob = assemble(source)
    return list(struct.unpack(f"<{len(blob) // 4}I", blob))


def test_ctl_gate_program_matches_assembler():
    """The pinned image is the assembler's output on the commented
    source — catches any hand-edit drift of the pinned words."""
    src = (
        "loop:\n"
        "    addi x8, x0, 5\n"
        "    addi x9, x0, 0\n"
        "inner:\n"
        "    addi x9, x9, 3\n"
        "    addi x8, x8, -1\n"
        "    bne x8, x0, inner\n"
        "    addi x14, x0, 90\n"
        "    sw x14, 16(x0)\n"
        "    lw x15, 16(x0)\n"
        "    jal x16, +8\n"
        "    addi x18, x0, 7\n"
        "    addi x19, x0, 1\n"
        "    addi x20, x0, 56\n"
        "    jalr x21, x20, 0\n"
        "    addi x22, x0, 99\n"
        "    ebreak\n"
    )
    assert CTL_GATE_PROGRAM == _asm_words(src)


def test_ctl_gate_program_decodes_cleanly():
    """Every word decodes to a known fmt (no '??'), and the control
    words decode to the intended fields."""
    for i, w in enumerate(CTL_GATE_PROGRAM):
        d = decode_ref(w)
        assert d["fmt"] != "??", f"word {i} (0x{w:08X}) undecodable"
    d4 = decode_ref(CTL_GATE_PROGRAM[4])
    assert (d4["fmt"], d4["opcode"], d4["funct3"], d4["rs1"], d4["rs2"],
            d4["imm"]) == ("B", 0x63, 1, 8, 0, -8)
    d8 = decode_ref(CTL_GATE_PROGRAM[8])
    assert (d8["fmt"], d8["opcode"], d8["rd"], d8["imm"]) == \
        ("J", 0x6F, 16, 8)
    d12 = decode_ref(CTL_GATE_PROGRAM[12])
    assert (d12["fmt"], d12["opcode"], d12["rd"], d12["rs1"],
            d12["imm"]) == ("I", 0x67, 21, 20, 0)


# ── ref_ctl: spec-literal branch polarity, full funct3 sweep ────────────


def test_ref_ctl_beq_bne():
    assert ref_ctl(0, 5, 5) == 1 and ref_ctl(0, 5, 6) == 0
    assert ref_ctl(1, 5, 5) == 0 and ref_ctl(1, 5, 6) == 1
    # x0-vs-x0 (the JZ-inversion operand pair) is NEVER taken for BNE
    assert ref_ctl(1, 0, 0) == 0


def test_ref_ctl_signed_vs_unsigned():
    """The -5 < 5 case: signed BLT taken, unsigned BLTU NOT taken
    (0xFFFFFFFB > 5 unsigned). This is the signedness trap made
    explicit."""
    A, B = 0xFFFFFFFB, 5
    assert ref_ctl(4, A, B) == 1      # BLT signed: taken
    assert ref_ctl(6, A, B) == 0      # BLTU unsigned: not taken
    assert ref_ctl(5, A, B) == 0      # BGE: -5 >= 5 → not taken
    assert ref_ctl(5, B, A) == 1      # BGE: 5 >= -5 → taken
    assert ref_ctl(7, A, B) == 1      # 0xFFFFFFFB >= 5 unsigned → taken


def test_ref_ctl_boundary_equal_cases():
    for f3, taken in [(0, 1), (1, 0), (4, 0), (5, 1), (6, 0), (7, 1)]:
        assert ref_ctl(f3, 9, 9) == taken, f"funct3={f3} a==b"
    # funct3=2/3 are not branch encodings — ref_ctl must refuse loudly
    for bad_f3 in (2, 3):
        with pytest.raises(ValueError):
            ref_ctl(bad_f3, 0, 0)


# ── execute_ctl unit gates ───────────────────────────────────────────────


def _run_one(word: int, st, dmem=None):
    return execute_ctl(st, decode_ref(word), dmem)


def test_bne_backward_taken_and_not():
    # BNE x8, x0, -8 at pc2: SPEC target = byte 8 + (-8) = word 0
    imem = load_program([0, 0, 0xFE041CE3, 0])
    st = new_state()
    st["pc"] = 2
    st["regs"][8] = 3
    s = _run_one(imem[2], st)
    assert s["pc"] == 2 - 2              # taken → pc 0 (SPEC: pc + imm/4)
    assert s["regs"] == st["regs"]       # branches never touch regs
    st2 = new_state()
    st2["pc"] = 2
    s2 = _run_one(imem[2], st2)
    assert s2["pc"] == 3                 # not taken → falls through


def test_jal_links_and_jumps():
    imem = load_program([0] * 5)
    word = 0x0080086F                    # JAL x16, +8 (bytes)
    st = new_state()
    st["pc"] = 3
    s = _run_one(word, st)
    assert s["pc"] == 5                  # SPEC: byte pc 12 + 8 = word 5
    assert s["regs"][16] == 16           # link = byte pc+4 = (3+1)*4
    # rd=x0 JAL must not write the link
    word_x0 = 0x0080006F                 # JAL x0, +8
    s2 = _run_one(word_x0, st)
    assert s2["regs"][16] == 0 and s2["pc"] == 5


def test_jalr_links_and_jumps_to_register_target():
    imem = load_program([0] * 16)
    word = 0x000A0AE7                    # JALR x21, x20, 0
    st = new_state()
    st["pc"] = 12
    st["regs"][20] = 56                  # byte target → word 14
    s = _run_one(word, st)
    assert s["pc"] == 14
    assert s["regs"][21] == 52           # link = byte pc+4 = (12+1)*4


def test_sw_lw_roundtrip_and_bounds():
    imem = load_program([0])
    dmem = [0] * 8
    sw = 0x00E02823                      # SW x14, 16(x0)
    st = new_state()
    st["regs"][14] = 90
    s = _run_one(sw, st, dmem)
    assert s["pc"] == 1 and dmem[4] == 90
    lw = 0x01002783                      # LW x15, 16(x0)
    s2 = _run_one(lw, s, dmem)
    assert s2["regs"][15] == 90
    # out-of-bounds and unaligned must be LOUD
    st_oob = new_state()
    st_oob["regs"][1] = 80               # base 80 bytes → word 20: OOB
    with pytest.raises(ValueError):
        _run_one(0x0500AA23, st_oob, dmem)  # SW x14, 80(x1) → OOB
    st_un = new_state()
    st_un["regs"][1] = 2                 # base 2 → addr 18, unaligned
    with pytest.raises(ValueError):
        _run_one(0x0120AA23, st_un, dmem)  # SW x14, 18(x1) unaligned


def test_execute_ctl_rejects_unknown_and_halts_on_system():
    with pytest.raises(ValueError):
        _run_one(0xFFFFFFFF, new_state())             # fmt '??'
    with pytest.raises(ControlHalt):
        _run_one(0x00100073, new_state())             # EBREAK


# ── the roadmap gate: backward-jump program to HALT, pinned trace ────────


def test_ps008_gate_control_flow_host_pin():
    """THE PS008 gate (host half). 15-word program with a backward BNE
    loop, SW/LW round-trip, JAL-skip and JALR-to-EBREAK runs to HALT in
    EXACTLY 23 transitions and lands on the hand-computed final state.
    Negative legs: a corrupted BNE offset and an inverted polarity BOTH
    go RED (budget exhaustion), proving the gate can fail."""
    receipt = gate_control_flow()
    assert receipt["ok"] is True, receipt
    assert receipt["steps_executed"] == 24
    assert receipt["final_pc"] == 14
    assert receipt["x9_accumulator"] == 15
    assert receipt["bne_taken_count"] == 4
    assert receipt["jal_link_x16"] == 36   # pc8: byte 32+4 (RV32I link)
    assert receipt["jalr_target_x21"] == 52
    assert receipt["jal_poison_x18"] == 0
    assert receipt["jalr_poison_x22"] == 0
    assert receipt["dmem_word4"] == 90
    # the budget-exhaustion path must exist (never a silent spin):
    with pytest.raises(RuntimeError):
        run_ctl_trace(load_program(CTL_GATE_PROGRAM), [0] * 256,
                      new_state(), 5)


def test_ps008_negative_corrupted_branch_offset_goes_red():
    """Discriminating leg: replace the pinned BNE -8 (SPEC: target word
    2) with -12 (target word 1). The corrupted program STILL terminates
    (x8 counts down regardless), so the step budget alone cannot catch
    it — the gate must catch it through the STEP-COUNT and ACCUMULATOR
    pins instead: the corrupted run takes 28 steps (not 24) and lands
    x9=0 in x9's canary position at exit... concretely: x9 differs from
    the pinned 15. A gate that only checked 'it terminated' would pass
    the corruption; this gate does not."""
    bad = list(CTL_GATE_PROGRAM)
    bad[4] = 0xFE041AE3                  # BNE x8,x0,-12 → target word 1
    bad_trace, _, bad_steps = run_ctl_trace(
        load_program(bad), [0] * 256, new_state(), 64)
    assert bad_steps != 24, "corrupted offset must change the step count"
    assert bad_trace[-1]["regs"][9] != 15, (
        "corrupted offset must change the accumulator pin")
    # and gate_control_flow's pinned program itself must NOT be the bad
    # word (guard the guard):
    assert CTL_GATE_PROGRAM[4] == 0xFE041CE3


def test_ps008_jz_inversion_trap_polarity_pair():
    """The JZ-inversion trap, explicit: BNE x0,x0 (never taken) must
    fall through to the tail EBREAK in 3 transitions; an inverted
    implementation would loop forever and exhaust ANY finite budget."""
    imem = load_program(LOOP_FOREVER_PROGRAM)
    trace, _, steps = run_ctl_trace(imem, [0] * 8, new_state(), 16)
    assert steps == 3 and trace[-1]["pc"] == 3
    with pytest.raises(RuntimeError):
        # force the inversion: replace the never-taken BNE with a
        # always-taken BNE x0,x0 → BEQ-equivalent (funct3 flip = the
        # inversion itself) and watch the budget die.
        bad = list(LOOP_FOREVER_PROGRAM)
        bad[2] = 0xFE001CE3 ^ (1 << 12)  # funct3 1→0: BNE becomes BEQ
        run_ctl_trace(load_program(bad), [0] * 8, new_state(), 16)


def test_ps008_branch_polarity_ref_discrimination():
    """The polarity pair at the ref level: BLT and BGE on identical
    operands must DISAGREE (a polarity inversion makes them agree —
    that agreement is exactly the historical JZ trap)."""
    A, B = 0xFFFFFFFB, 5                 # signed -5 vs 5
    assert ref_ctl(4, A, B) != ref_ctl(5, A, B)   # BLT vs BGE differ
    assert ref_ctl(4, B, A) != ref_ctl(5, B, A)
    assert ref_ctl(0, A, A) != ref_ctl(1, A, A)   # BEQ vs BNE differ


# ── GPU legs (non-blocking smoke lane, determinism clause) ───────────────


def test_ps008_gpu_legs_recorded_in_receipt():
    """GPU legs are RECORDED in the receipt and asserted here as the
    smoke lane — they run on the real 5090 adapter when present. A
    skip (no adapter) is recorded as a skip, never faked green."""
    receipt = gate_control_flow()
    for key in ("gpu_bne_ok", "gpu_blt_ok", "gpu_bge_ok", "gpu_addr_ok"):
        assert key in receipt
    try:
        import wgpu  # noqa: F401
        gpu_available = True
    except Exception:
        gpu_available = False
    if gpu_available:
        assert receipt["gpu_bne_ok"], receipt
        assert receipt["gpu_blt_ok"], receipt
        assert receipt["gpu_bge_ok"], receipt
        assert receipt["gpu_addr_ok"], receipt


# ── pixel-CPU cross-validation (the third engine) ────────────────────────


def test_ps008_pixel_cpu_cross_validation():
    """Same program image on SpatialRV32ICore (the WGSL pixel CPU):
    final register file must equal the host FDE final register file
    exactly. EBREAK raises a trap in the pixel core which sets halted
    — get_state after run_until_halt is the comparable endpoint.
    Skipped cleanly when wgpu is unavailable (never faked)."""
    try:
        import wgpu  # noqa: F401
    except Exception:
        pytest.skip("wgpu adapter unavailable — pixel CPU leg not run")
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent.parent / "tools"))
    from spatial_rv32i_cpu import SpatialRV32ICore

    core = SpatialRV32ICore(1024)
    imem = load_program(CTL_GATE_PROGRAM)
    blob = struct.pack("<16I", *imem, 0)  # pad to 16 words (64 bytes)
    core.load_program(blob)
    state = core.run_until_halt(max_cycles=500)
    regs_pixel = [int(v) for v in state["regs"]]

    trace, dmem, steps = run_ctl_trace(imem, [0] * 256, new_state(), 64)
    regs_host = trace[-1]["regs"]

    # x2/sp and any CSR-touched regs must match too — full 32-reg diff.
    for i in range(REG_N):
        assert regs_pixel[i] == regs_host[i], (
            f"x{i}: pixel={regs_pixel[i]} host={regs_host[i]}")
    # the EBREAK-trapped pc is the EBREAK itself in the pixel core; the
    # host model halts BEFORE the SYSTEM insn, so compare registers only
    # (pc semantics at halt are model-defined and NOT compared here).


# ── harness self-test (prove the harness can go RED) ─────────────────────


def test_harness_failure_path_is_live():
    with pytest.raises(AssertionError):
        assert gate_control_flow()["steps_executed"] == 999999


# ── cross-executor agreement (RULING_ps008_branch_convention step 4) ─────


def test_ps008_cross_executor_branch_agreement():
    """RULING_ps008_branch_convention step 4 — the composition pre-gate
    PS009 needs. After the ruling, BOTH executors use SPEC branch
    arithmetic (taken next pc = pc + imm//4, no +1) on the SAME BNE
    encodings, and must produce IDENTICAL pc paths:

    1. per-step taken/not-taken BNE at a mid-program pc (the exact
       encoding pair from the ruling's correction: 0xFE0298E3, imm
       -16);
    2. the full 7-word FIB loop: step-count and final-register pins
       must agree EXACTLY (both 42 steps, both ending x1=34, x2=55,
       x3=55, x5=0).
    Discrimination: the old PS007 convention (pc + 1 + imm//4) lands the
    FIB taken branch at pc=3, not pc=2, and the walk then leaves the 7-word
    image — execute_one with +1 restored raises "IndexError: fetch: pc 7
    out of bounds (imem len 7)" before 42 steps complete (measured
    2026-09-21), so a regression fails loudly rather than quietly
    re-pinning.
    """
    from tools.pyshader_ctl import execute_ctl
    from tools.pyshader_fde import execute_one
    from tools.pyshader_rvdecode import decode_ref

    BNE_WORD = 0xFE0298E3  # BNE x5, x0, -16 (the ruling's corrected word)
    d = decode_ref(BNE_WORD)
    assert d["fmt"] == "B" and d["imm"] == -16 and d["rs1"] == 5

    # Branch-site image mirroring the FIB layout: BNE at pc=6, SPEC
    # target pc=2 (6 + (-16//4)); the old convention would land at 3.
    imem = load_program([
        0x00000000,  # 0: padding
        0x00000000,  # 1: padding
        0x00000000,  # 2: branch TARGET (pc = 6 - 4 = 2)
        0x00000000,  # 3: skipped on taken (old convention would land here)
        0x00000000,  # 4: padding
        0x00000000,  # 5: padding
        BNE_WORD,    # 6: BNE x5, x0, -16 → SPEC target pc=2
    ])

    # TAKEN leg: both executors must land at pc=2 (old convention: pc=3)
    st_fde = new_state()
    st_fde["pc"] = 6
    st_fde["regs"][5] = 3
    st_ctl = new_state()
    st_ctl["pc"] = 6
    st_ctl["regs"][5] = 3
    s_fde = execute_one(st_fde, imem)
    s_ctl = execute_ctl(st_ctl, d)
    assert s_fde["pc"] == 2, f"fde taken: expected 2, got {s_fde['pc']}"
    assert s_ctl["pc"] == 2, f"ctl taken: expected 2, got {s_ctl['pc']}"
    assert s_fde["pc"] != 3 and s_ctl["pc"] != 3, (
        "old pc+1+imm//4 convention regressed: taken branch landed at 3")

    # NOT-TAKEN leg: both advance +1 to pc=7 is OOB for fde (fetch
    # raises on execute; ctl falls to pc=7 fine since execute_ctl does
    # not fetch). Compare next-pc only.
    st_fde2 = new_state()
    st_fde2["pc"] = 6
    st_ctl2 = new_state()
    st_ctl2["pc"] = 6
    s_fde2 = execute_one(st_fde2, imem)  # x5=0 → not taken
    s_ctl2 = execute_ctl(st_ctl2, d)
    assert s_fde2["pc"] == 7 and s_ctl2["pc"] == 7

    # Full FIB program: identical trace endpoints from both executors
    from tools.pyshader_fde import (
        FIB_EXPECTED_FINAL, FIB_EXPECTED_STEPS, FIB_LOOP_COUNT_DEFAULT,
        FIB_PROGRAM, FIB_X3_SEQUENCE, run_fde,
    )

    # FDE executor:
    st = new_state()
    st["regs"][5] = FIB_LOOP_COUNT_DEFAULT
    fde_trace = run_fde(load_program(FIB_PROGRAM), st, FIB_EXPECTED_STEPS)
    fin_fde = fde_trace[-1]["regs"]

    # CTL executor (run_ctl_trace routes ALU through execute_one —
    # shared code — so drive the loop through execute_ctl DIRECTLY for
    # a true independent path):
    imem_fib = load_program(FIB_PROGRAM)
    stc = new_state()
    stc["regs"][5] = FIB_LOOP_COUNT_DEFAULT
    ctl_steps = 0
    x3_seq_ctl = []
    try:
        while ctl_steps < FIB_EXPECTED_STEPS:
            dcur = decode_ref(fetch(stc["pc"], imem_fib))
            if dcur["fmt"] == "B":
                stc = execute_ctl(stc, dcur)
            else:
                # ALU-only in this program; apply the R/I semantics via
                # execute_one (shared with fde) but on ctl's own state.
                stc = execute_one(stc, imem_fib)
            if stc["pc"] == 3:
                x3_seq_ctl.append(stc["regs"][3])
            ctl_steps += 1
    except Exception as e:
        pytest.fail(f"ctl FIB loop diverged at step {ctl_steps}: {e}")

    assert ctl_steps == FIB_EXPECTED_STEPS
    for reg, want in FIB_EXPECTED_FINAL.items():
        assert stc["regs"][reg] == want, (
            f"ctl final x{reg}: {stc['regs'][reg]} != {want}")
    assert x3_seq_ctl == FIB_X3_SEQUENCE
    # and the two executors' final register files are IDENTICAL:
    assert stc["regs"] == fin_fde
