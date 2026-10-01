"""tests/test_pyshader_golden.py — PS011 skeleton structural harness.

10 legs on the STUB bodies: signatures exist, stubs raise
NotImplementedError (loud, never silent), the pinned program shape
constants are present. Per the skeleton-handoff-contract: these are
GUARDS — each step's population REPLACES its stub-raise leg with the
behavioral gate test named in the brief, never deletes it silently.
"""

import importlib
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

golden = importlib.import_module("tools.pyshader_golden")


# ── legs 1-2: module + locked interface surface ──────────────────────────

def test_ps011_module_imports_clean():
    assert golden.__name__ == "tools.pyshader_golden"
    assert golden.GOLDEN_MIN_TRANSITIONS == 1000


def test_ps011_signatures_locked():
    sig_gt = inspect.signature(golden.golden_trace)
    assert list(sig_gt.parameters) == ["imem", "dmem", "state", "max_steps"]
    sig_pt = inspect.signature(golden.pixel_trace)
    assert list(sig_pt.parameters) == ["imem", "n_steps"]
    sig_dt = inspect.signature(golden.diff_traces)
    assert list(sig_dt.parameters) == ["ref", "imp", "ignore_regs"]
    sig_bg = inspect.signature(golden.build_gate_program)
    assert list(sig_bg.parameters) == []
    sig_gg = inspect.signature(golden.gate_golden_trace)
    assert list(sig_gg.parameters) == []


# ── legs 3-7: every stub raises loudly (guards; replaced per step) ──────

def test_ps011_golden_trace_shape_and_pins():
    """PS011 step 1 (behavioral gate, replaces the stub-raise guard).

    Gate clause (brief_ps011_golden_trace.md step 1):
    - pinned 8-word program assembled via rv32i_asm.assemble (words NOT
      yet pin-verified — that is step 4);
    - trace length == 1253 (initial snapshot + 1252 transitions,
      measured not hoped);
    - trace[0] == {'pc': 0, 'instr': decoded word-0, 'regs': fresh
      state};
    - final regs match hand-derived pins x1==31375, x2==0;
    - input state not mutated;
    - max_steps exhaustion raises RuntimeError.
    """
    import struct

    from tools.pyshader_fde import REG_N, new_state
    from tools.rv32i_asm import assemble

    # The pinned 8-word loop program, verbatim from the skeleton
    # docstring (tools/pyshader_golden.py:45-53). Assembled, never
    # hand-encoded.
    SRC = """\
        ADDI x1, x0, 0
        ADDI x2, x0, 250
loop:   SW   x1, 0(x0)
        LW   x3, 0(x0)
        ADD  x1, x1, x2
        ADDI x2, x2, -1
        BNE  x2, x0, loop
        EBREAK
"""
    blob = assemble(SRC)
    imem = list(struct.unpack("<%dI" % (len(blob) // 4), blob))
    assert len(imem) == 8

    dmem = [0] * 16
    st = new_state()
    st_snap = {"pc": st["pc"], "regs": list(st["regs"])}

    trace = golden.golden_trace(imem, dmem, st, max_steps=2000)

    # Length: 1 initial snapshot + 1252 executed transitions.
    assert len(trace) == 1253, len(trace)

    # Entry shape: {'pc', 'instr', 'regs'}; regs always 32 wide.
    for entry in (trace[0], trace[1], trace[-1]):
        assert set(entry) == {"pc", "instr", "regs"}
        assert len(entry["regs"]) == REG_N

    # trace[0] is the fresh initial snapshot.
    assert trace[0]["pc"] == 0
    assert trace[0]["regs"] == st_snap["regs"]
    # instr is the RAW word at that pc — ADDI x1, x0, 0 assembles to
    # 0x00000093 (imm=0); pin against the assembled image, never a
    # hand-typed constant (this leg caught exactly that typo).
    assert trace[0]["instr"] == imem[0]
    assert trace[0]["instr"] == 0x00000093
    d0 = golden.decode_ref(trace[0]["instr"])
    assert d0["fmt"] == "I" and d0["rd"] == 1 and d0["imm"] == 0

    # Hand-derived pins: x1 = sum(1..250) = 31375, x2 = 0.
    fin = trace[-1]["regs"]
    assert fin[1] == 31375, fin[1]
    assert fin[2] == 0, fin[2]

    # Input state never mutated.
    assert st == st_snap

    # Budget exhaustion is loud.
    try:
        golden.golden_trace(imem, dmem, new_state(), max_steps=100)
    except RuntimeError as e:
        assert "exhaust" in str(e).lower()
    else:
        raise AssertionError("max_steps exhaustion must raise RuntimeError")


def test_ps011_pixel_trace_smoke_lane():
    """PS011 step 2 (behavioral gate, replaces the stub-raise guard
    test_pixel_trace_stub_raises — removal noted here per the brief's
    keep-guards-live constraint).

    Gate clause (brief_ps011_golden_trace.md step 2):
    - same pinned 8 words through SpatialRV32ICore;
    - entries in the SAME {'pc','instr','regs'} shape;
    - SMOKE LANE: SKIPS with the measured reason string when wgpu
      device acquisition fails or the GPU is absent — never fails the
      suite on hardware (determinism clause);
    - asserts ONLY shape invariants when the device IS present (length
      >= 2, keys present); the ref-vs-pixel diff is printed as a record
      and NEVER asserted here.
    """
    import struct

    import pytest

    from tools.rv32i_asm import assemble

    SRC = """\
        ADDI x1, x0, 0
        ADDI x2, x0, 250
loop:   SW   x1, 0(x0)
        LW   x3, 0(x0)
        ADD  x1, x1, x2
        ADDI x2, x2, -1
        BNE  x2, x0, loop
        EBREAK
"""
    blob = assemble(SRC)
    imem = list(struct.unpack("<%dI" % (len(blob) // 4), blob))
    assert len(imem) == 8

    try:
        trace = golden.pixel_trace(imem, 2000)
    except RuntimeError as e:
        if "wgpu device acquisition failed" in str(e):
            pytest.skip(str(e))
        raise

    # Shape invariants ONLY (smoke lane).
    assert len(trace) >= 2, len(trace)
    for entry in trace:
        assert set(entry) == {"pc", "instr", "regs"}
        assert len(entry["regs"]) == 32
        assert isinstance(entry["pc"], int)
        assert entry["instr"] == imem[entry["pc"]]
    assert trace[0]["pc"] == 0

    # Record (never gate): first mismatch vs the golden trace, for the
    # step receipt. Failures here are REPORTED, not asserted.
    from tools.pyshader_fde import new_state

    dmem = [0] * 16
    ref = golden.golden_trace(imem, dmem, new_state(), max_steps=2000)
    first = None
    for i, (r, p) in enumerate(zip(ref, trace)):
        if r["pc"] != p["pc"] or list(r["regs"]) != list(p["regs"]):
            first = (i, r["pc"], p["pc"],
                     [j for j in range(32)
                      if r["regs"][j] != p["regs"][j]][:4])
            break
    else:
        if len(ref) != len(trace):
            first = ("len", len(ref), len(trace), None)
    print("PS011 smoke-lane record: ref_len=%d pixel_len=%d "
          "first_mismatch=%r" % (len(ref), len(trace), first))


def test_ps011_diff_traces_spec_verdicts():
    """PS011 step 3 (behavioral gate, replaces the stub-raise guard
    test_diff_traces_stub_raises — removal noted here per the brief's
    keep-guards-live constraint).

    Gate clause (brief_ps011_golden_trace.md step 3):
    (a) identical traces -> ok=True, compared==len, spec_verdict None;
    (b) one wrong register value -> ok=False, first_mismatch names
        index + reg, spec_verdict is a NON-EMPTY string citing the
        SPEC rule (never an engine name);
    (c) length mismatch -> ok=False with a named verdict;
    (d) x0 violated on one side -> DETECTED (x0 is NOT excluded);
    (e) ignore_regs mechanism works when explicitly passed.
    """
    import copy
    import struct

    from tools.pyshader_fde import new_state
    from tools.rv32i_asm import assemble

    # The pinned program, counter=3 variant (short, keeps the test
    # fast); the ref side comes from the real step-1 engine.
    SRC = """\
        ADDI x1, x0, 0
        ADDI x2, x0, 3
loop:   SW   x1, 0(x0)
        LW   x3, 0(x0)
        ADD  x1, x1, x2
        ADDI x2, x2, -1
        BNE  x2, x0, loop
        EBREAK
"""
    blob = assemble(SRC)
    imem = list(struct.unpack("<%dI" % (len(blob) // 4), blob))
    dmem = [0] * 16
    ref = golden.golden_trace(imem, dmem, new_state(), max_steps=50)
    assert len(ref) >= 2

    # (a) identical traces -> ok
    r = golden.diff_traces(ref, copy.deepcopy(ref))
    assert r["ok"] is True
    assert r["compared"] == len(ref)
    assert r["spec_verdict"] is None
    assert r["first_mismatch"] is None

    # (b) mutant with one wrong register value -> named spec verdict
    imp_b = copy.deepcopy(ref)
    imp_b[4]["regs"][1] += 1  # wrong x1 at entry 4
    r = golden.diff_traces(ref, imp_b)
    assert r["ok"] is False
    assert r["first_mismatch"]["index"] == 4
    assert r["first_mismatch"]["reg"] == 1
    v = r["spec_verdict"]
    assert isinstance(v, str) and len(v) > 0, v
    assert "SPEC" in v, v
    # Adjudication cites the SPEC, never an engine name (PS004 lesson).
    for engine in ("golden", "pixel", "ref", "imp"):
        assert engine not in v.lower(), v

    # (c) length mismatch -> named verdict
    imp_c = ref[:-1]  # one entry short
    r = golden.diff_traces(ref, imp_c)
    assert r["ok"] is False
    v = r["spec_verdict"]
    assert isinstance(v, str) and len(v) > 0 and "SPEC" in v, v

    # (d) x0 violated on one side -> DETECTED (x0 is NOT excluded)
    imp_d = copy.deepcopy(ref)
    imp_d[2]["regs"][0] = 7  # x0 must stay 0 — that IS a spec rule
    r = golden.diff_traces(ref, imp_d)
    assert r["ok"] is False
    assert r["first_mismatch"]["reg"] == 0

    # (e) ignore_regs mechanism works when explicitly passed
    r = golden.diff_traces(ref, imp_d, ignore_regs=frozenset({0}))
    assert r["ok"] is True
    assert r["compared"] == len(ref)
    assert r["spec_verdict"] is None


def test_ps011_golden_gate():
    """PS011 step 4 (behavioral gate, REPLACES the stub-raise guards
    test_build_gate_program_stub_raises and
    test_gate_golden_trace_stub_raises — removal noted here per the
    brief's keep-guards-live constraint).

    Gate clause (brief_ps011_golden_trace.md step 4):
    - build_gate_program returns (imem, dmem) with ALL 8 words
      decode-verified via decode_ref (fmt/opcode/funct3/imm each
      asserted — asserted inside build_gate_program itself; here we
      additionally pin the word count, dmem shape, and the BNE imm
      == -16 explicitly so the branch pin is machine-checked in the
      test too);
    - gate_golden_trace returns a receipt dict:
      {'ok': True, 'transitions': 1252 (exact), 'final': {'x1': 31375,
      'x2': 0}, 'trace_len': 1253 (exact), 'spec_verdicts': [],
      'pixel_diff': RECORDED-or-'skipped' (never asserted)};
    - NON-VACUITY REQUIRED: a mutant golden_trace (x1 += counter-1,
      one-off arithmetic slip) run through the gate receipt path must
      produce ok=False with a named verdict — the probe lives here and
      is exercised in this leg.
    """
    imem, dmem = golden.build_gate_program()

    # Program shape + the branch pin, machine-checked test-side too.
    assert len(imem) == 8, len(imem)
    assert len(dmem) >= 1 and all(w == 0 for w in dmem)
    d_bne = golden.decode_ref(imem[6])
    assert d_bne["fmt"] == "B" and d_bne["funct3"] == 1
    assert d_bne["imm"] == -16, d_bne["imm"]  # insn 6 -> insn 2

    receipt = golden.gate_golden_trace()

    assert receipt["ok"] is True, receipt["spec_verdicts"]
    assert receipt["transitions"] == 1252, receipt["transitions"]
    assert receipt["final"]["x1"] == 31375, receipt["final"]
    assert receipt["final"]["x2"] == 0, receipt["final"]
    assert receipt["trace_len"] == 1253, receipt["trace_len"]
    assert receipt["spec_verdicts"] == [], receipt["spec_verdicts"]
    # pixel_diff is RECORDED-or-'skipped', NEVER asserted (determinism
    # clause): either form is acceptable, and its content must gate
    # nothing.
    assert (receipt["pixel_diff"] == "skipped"
            or isinstance(receipt["pixel_diff"], dict)), \
        receipt["pixel_diff"]

    # Receipt shape is closed: exactly the keys the brief pins.
    assert set(receipt) == {"ok", "transitions", "final", "trace_len",
                            "spec_verdicts", "pixel_diff"}, set(receipt)

    # ── non-vacuity: the gate must be able to FAIL ────────────────────
    # Mutate golden_trace with the brief's one-off arithmetic slip
    # (x1 += counter-1 instead of counter) and run it through the SAME
    # receipt path. The gate must return ok=False with a named
    # spec-rule verdict. This proves the pins discriminate: a green
    # here is not a decoration that passes for any engine.
    import copy

    real_golden_trace = golden.golden_trace

    def mutant_golden_trace(imem, dmem, state, max_steps):
        trace = real_golden_trace(imem, dmem, state, max_steps)
        mutant = copy.deepcopy(trace)
        for entry in mutant:
            entry["regs"][1] += entry["regs"][2] - 1  # the slip
        return mutant

    golden.golden_trace = mutant_golden_trace
    try:
        mutant_receipt = golden.gate_golden_trace()
    finally:
        golden.golden_trace = real_golden_trace  # restore the engine

    assert mutant_receipt["ok"] is False, mutant_receipt
    assert len(mutant_receipt["spec_verdicts"]) > 0, mutant_receipt
    v = mutant_receipt["spec_verdicts"][0]
    assert "SPEC" in v, v
    # Adjudication cites the SPEC, never an engine name (PS004 lesson).
    for engine in ("golden", "pixel", "ref", "imp", "mutant"):
        assert engine not in v.lower(), v
    # The mutant must diverge exactly where the slip lands: final x1.
    assert mutant_receipt["final"]["x1"] != 31375, mutant_receipt["final"]


# ── legs 8-10: harness invariants that survive population ───────────────

def test_ps011_ignored_regs_default_empty():
    # x0 must NOT be in the ignore set: x0==0 IS a spec rule.
    assert golden.IGNORED_REGS == frozenset()
    assert 0 not in golden.IGNORED_REGS


def test_ps011_dependency_surface_present():
    # Reuse-don't-reimplement: the PS008 driver and the PS005 decoder
    # must exist at the signatures the skeleton pins.
    from tools.pyshader_ctl import run_ctl_trace, ControlHalt
    from tools.pyshader_fde import decode_ref, execute_one, fetch, new_state
    from tools.rv32i_asm import assemble
    assert callable(run_ctl_trace) and callable(assemble)
    assert callable(decode_ref) and callable(execute_one)


def test_ps011_pixel_cpu_module_present():
    # The pixel CPU (step-2 smoke lane) import surface — import only,
    # no device acquisition in the structural harness (no GPU in unit
    # tests; wgpu device acquisition is the smoke lane's job).
    import tools.spatial_rv32i_cpu as srv
    assert hasattr(srv, "SpatialRV32ICore")
