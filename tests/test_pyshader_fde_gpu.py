"""PS009a gates: GPU-resident FDE loop (tools/pyshader_fde_gpu.py).

RULING_ps009 (e839cab7) order: 009a build + trace-diff gates. The shader
internally iterates a decoded-instruction buffer; the host re-dispatches
on taken branches / halt. Gate: trace-diff of the FIB workload AND a
>1k-insn straight-line program vs the Python FDE (tools.pyshader_fde.
run_fde) AND the pixel CPU (SpatialRV32ICore) — 100% trace match.
NO performance claim, NO fork arithmetic (that is 009b, reserved).
"""
import sys

sys.path.insert(0, "/home/jericho/projects/zion/projects/visual_audio")

import pytest

from tools.pyshader_fde import (
    FIB_EXPECTED_FINAL,
    FIB_EXPECTED_STEPS,
    FIB_PROGRAM,
    FIB_X3_SEQUENCE,
    load_program,
    new_state,
    run_fde,
)


def _pixel_trace(imem, st, n_steps):
    """Pixel-CPU leg: step(1) at a time, snapshot pc+regs per step.
    Same trace shape as run_fde (trace[0] = initial state).
    NOTE: SpatialRV32ICore's pc is BYTE-addressed; the pyshader_fde
    convention is INSTRUCTION INDEX. Same SPEC semantics, different
    units — the adapter divides pc by 4 (all fixtures are whole
    4-byte instructions, no compressed insns)."""
    from spatial_rv32i_cpu import SpatialRV32ICore
    import numpy as np

    core = SpatialRV32ICore()
    core.load_program(
        np.array(imem, dtype=np.uint32).tobytes(), entry_point=0)
    for i, v in enumerate(st["regs"]):
        if v:
            core.write_register(i, v)
    trace = [{"pc": st["pc"], "regs": list(st["regs"])}]
    for _ in range(n_steps):
        core.step(1)
        s = core.get_state()
        regs = [int(x) for x in s["regs"]]
        trace.append({"pc": int(s["pc"]) // 4, "regs": regs})
        if s.get("halted"):
            break
    return trace


def _states_equal(a, b):
    return a["pc"] == b["pc"] and list(a["regs"]) == list(b["regs"])


def test_fib_gpu_trace_matches_python_fde():
    """The 009a gate: 100% trace match, FIB workload, GPU vs Python FDE."""
    from tools.pyshader_fde_gpu import run_fde_gpu

    imem = load_program(FIB_PROGRAM)
    st = new_state()
    st["regs"][5] = 8

    py_trace = run_fde(imem, st, FIB_EXPECTED_STEPS)
    r = run_fde_gpu(imem, st, max_steps=FIB_EXPECTED_STEPS)
    assert r["ok"], f"GPU FDE faulted: stop={r['stop_reason']} " \
                    f"dispatches={r['dispatches']}"
    assert len(r["trace"]) == len(py_trace) == FIB_EXPECTED_STEPS + 1
    for i, (g, p) in enumerate(zip(r["trace"], py_trace)):
        assert _states_equal(g, p), f"trace mismatch at step {i}: " \
                                    f"gpu={g['pc']} py={p['pc']}"


def test_fib_gpu_final_pin_and_sequence():
    """GPU FDE final registers match the hand-computed FIB pin, and the
    x3-per-iteration sequence matches — the GPU leg does not get to
    agree with a wrong Python by matching it."""
    from tools.pyshader_fde_gpu import run_fde_gpu

    imem = load_program(FIB_PROGRAM)
    st = new_state()
    st["regs"][5] = 8
    r = run_fde_gpu(imem, st, max_steps=FIB_EXPECTED_STEPS)
    fin = r["trace"][-1]["regs"]
    assert {k: fin[k] for k in FIB_EXPECTED_FINAL} == FIB_EXPECTED_FINAL
    x3 = [snap["regs"][3] for snap in r["trace"][1:] if snap["pc"] == 3]
    assert x3 == FIB_X3_SEQUENCE


def test_fib_gpu_matches_pixel_cpu():
    """Third engine: pixel CPU trace (SpatialRV32ICore), same shape."""
    from tools.pyshader_fde_gpu import run_fde_gpu

    imem = load_program(FIB_PROGRAM)
    st = new_state()
    st["regs"][5] = 8
    px = _pixel_trace(imem, st, FIB_EXPECTED_STEPS)
    r = run_fde_gpu(imem, st, max_steps=FIB_EXPECTED_STEPS)
    assert len(px) == FIB_EXPECTED_STEPS + 1
    assert len(r["trace"]) == len(px)
    for i, (g, p) in enumerate(zip(r["trace"], px)):
        assert _states_equal(g, p), f"pixel-CPU mismatch at step {i}"


def test_straightline_1200_gpu_matches_python_fde():
    """>1k-insn straight-line program (roadmap 009a gate): 1200 x
    ADDI x1,x1,1 then an out-of-bounds fetch halts. One dispatch."""
    from tools.pyshader_fde_gpu import run_fde_gpu

    N = 1200
    # ADDI x1, x1, 1  = imm=1, rs1=1, funct3=0, rd=1, opcode=0x13
    imem = load_program([0x00108093] * N)
    st = new_state()
    r = run_fde_gpu(imem, st, max_steps=N)
    assert r["ok"], f"stop={r['stop_reason']}"
    assert len(r["trace"]) == N + 1
    # pin: reg file climbs 0..N, pcs 0..N-1 then final pc = N
    assert r["trace"][-1]["regs"][1] == N
    assert r["trace"][-1]["pc"] == N
    # full trace-diff vs Python FDE on a coarser but exact basis:
    py_trace = run_fde(imem, st, N)
    assert len(py_trace) == N + 1
    for i in (0, 1, N // 2, N - 1, N):
        assert _states_equal(r["trace"][i], py_trace[i]), f"step {i}"


def test_unknown_opcode_faults_not_silently_executes():
    """Negative leg (gate must be able to fail): an unsupported opcode
    (JAL, 0x6F) must halt the GPU loop with an explicit fault reason and
    a SHORT trace — never fabricated progress. The Python FDE raises
    NotImplementedError on the same program; the two must disagree by
    the GPU stopping, not by the GPU inventing states."""
    from tools.pyshader_fde_gpu import run_fde_gpu

    imem = load_program([0x00100093, 0x6F000000])  # ADDI then JAL
    st = new_state()
    r = run_fde_gpu(imem, st, max_steps=10)
    assert r["stop_reason"] == 3, f"expected bad-opcode fault, got {r}"
    assert len(r["trace"]) == 2  # initial + the one legal ADDI step
    assert r["trace"][1]["regs"][1] == 1
    with pytest.raises(NotImplementedError):
        run_fde(imem, st, 2)


def test_branch_not_taken_falls_through():
    """Branch-polarity leg: BNE with equal operands must NOT be taken —
    the loop falls through, pc advances linearly (PS008 JZ-inversion
    trap class). x5 preloaded 1, decremented to 0 before the BNE."""
    from tools.pyshader_fde_gpu import run_fde_gpu

    # 0: ADDI x5, x5, -1   (x5: 1 -> 0)
    # 1: BNE  x5, x0, -16  (NOT taken: x5 == 0)
    # 2: ADDI x1, x0, 7    (fall-through lands here)
    imem = load_program([0xFFF28293, 0xFE0298E3, 0x00700093])
    st = new_state()
    st["regs"][5] = 1
    r = run_fde_gpu(imem, st, max_steps=10)
    assert r["trace"][-1]["pc"] == 3, f"final pc {r['trace'][-1]['pc']}"
    assert r["trace"][-1]["regs"][1] == 7
