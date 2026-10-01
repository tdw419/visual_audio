"""tools/pyshader_golden.py — PS011: golden-trace cross-validation.

Roadmap row (GPU_CPU_EMULATOR_ROADMAP.md, PS011):
    Run the existing trace-diff pipeline between the generated emulator
    and the hand-written one on shared fixtures; divergences are
    adjudicated against the RISC-V spec, not against either
    implementation.
    Gate: >=1 non-trivial program (>=1k instructions, branches+memory)
    with 100% trace match; any divergence produces a named spec-rule
    verdict in the receipt.

SKELETON ROUND (structure-first; interfaces LOCKED, bodies are stubs):

- Step 1: `golden_trace` — run the PS008 host driver (run_ctl_trace)
  over a program and emit a JSONL-shaped golden trace: one entry per
  EXECUTED transition snapshot, {'pc', 'instr', 'regs'} with pc as the
  insn-index pc the PS-chain uses and regs as {x0..x31: int}. The
  PS-chain state is never mutated.
- Step 2: `pixel_trace` — the SAME program words through the pixel CPU
  (tools/spatial_rv32i_cpu.py SpatialRV32ICore, load_program +
  step loop + _trace_state-format entries). GPU/wgpu presence makes
  this the NON-BLOCKING SMOKE LANE per the determinism clause: recorded
  in receipts, never gating. Uses _cached-style device acquisition
  discipline (device-exhaustion lesson, PS005).
- Step 3: `diff_traces` — compare two traces entry-by-entry: pc, then
  every register present in BOTH sides (intersection, never union —
  the diff_qemu_gpu_traces.py:65 lesson). Returns a receipt dict:
  {'ok', 'compared', 'first_mismatch', 'spec_verdict'} where
  spec_verdict is None when ok, else a NAMED RISC-V spec rule string
  (e.g. 'SPEC: BGE signed comparison, Table 2.1 branch semantics') —
  a divergence is adjudicated against the SPEC, never against either
  implementation. We do NOT import or modify
  tools/diff_qemu_gpu_traces.py (protected by its own history); this
  module re-implements the 60-line comparison honestly for the
  PS-chain trace shape (insn-index pc, list regs) rather than
  normalizing two different dict shapes through someone else's
  kernel-boot assumptions.
- Step 4: `build_gate_program` + `gate_golden_trace` — build the pinned
  >=1k-transition program below, run both engines, diff, adjudicate.

THE PINNED GATE PROGRAM (locked here; hand-compute pins from THIS, do
not re-size it — the PS007 word-6 authoring-error lesson is why the
program is pinned in the skeleton, before any pin arithmetic exists)::

    ADDI x1, x0, 0        # 0: acc = 0
    ADDI x2, x0, 250      # 1: counter = 250
loop:                     #    (insn index 2)
    SW   x1, 0(x0)        # 2: dmem[0] = acc        (dmem word-index
    LW   x3, 0(x0)        # 3: x3 = dmem[0]          convention per
    ADD  x1, x1, x2       # 4: acc += counter        execute_ctl —
    ADDI x2, x2, -1       # 5: counter--             parse-verify, do
    BNE  x2, x0, loop     # 6: backward branch       not re-derive)
    EBREAK                # 7: halt (ControlHalt)

    Hand-derived structure pins (formula level — the step-4 receipt
    states the numbers and shows the arithmetic):
    - executed transitions = 2 init + 5 per iteration x 250 = 1252
      (>= GOLDEN_MIN_TRANSITIONS: the 1k requirement is met by FORMULA,
      verified against the measured trace length, not by hope).
    - final x1 = sum(1..250) = 31375; final x2 = 0; x3 = the acc value
      at the last SW; trace length = 1253 (initial snapshot + 1252).
    - the branch is insn 6 -> insn 2 = -4 insns = -16 bytes, SPEC
      semantics (pc + imm//4, RULING_ps008_branch_convention) — the
      same convention the PS007 FIB gate landed on.
    Assemble with tools/rv32i_asm.py assemble() (do NOT hand-encode);
    decode-verify every word via PS005 decode_ref at the landing
    revision (PS007 step-6 discipline).

Halting: EBREAK raises ControlHalt inside run_ctl_trace, which returns
without appending a post-EBREAK snapshot — so the golden trace ends at
the last real transition. Budget exhaustion raises RuntimeError (loud,
never a silent spin — PS008 lesson).

Determinism clause: the pixel-CPU leg (step 2) and any GPU-dependent
leg are the non-blocking smoke lane — their outcome is RECORDED in the
receipt and never gates. The gate adjudicates golden_trace (host,
deterministic) against the hand-derived pins and diff_traces(ref,
ref-mutant) mechanics; the ref-vs-pixel diff is recorded, reported, and
non-blocking.

Files this round owns: tools/pyshader_golden.py,
tests/test_pyshader_golden.py,
.builder_queue/brief_ps011_golden_trace.md. Everything else is
must-not-touch this round (including tools/diff_qemu_gpu_traces.py,
tools/pyshader_ctl.py, tools/pyshader_fde.py, tools/spatial_rv32i_cpu.py).
"""

from typing import Dict, List, Optional, Tuple

import struct

import tools.pyshader_golden as _golden_module
from tools.pyshader_ctl import run_ctl_trace
from tools.pyshader_rvdecode import decode_ref


def golden_self():
    """Module-level indirection so test-time monkeypatching of
    golden_trace (the non-vacuity mutant in test_ps011_golden_gate)
    is visible to gate_golden_trace — the gate must be able to
    adjudicate a mutated engine, not a baked-in reference."""
    return _golden_module

# The 1k-transitions requirement, as a named constant so the gate cannot
# silently drift below the roadmap threshold.
GOLDEN_MIN_TRANSITIONS = 1000

# Registers excluded from cross-engine comparison. x0 is NOT excluded
# (both engines must hold it at 0 — that IS a spec rule). Empty by
# default; the diff may accept an explicit ignore set for engine-specific
# non-architectural state, but the gate passes none.
IGNORED_REGS: frozenset = frozenset()


def golden_trace(imem: List[int], dmem: List[int], state: Dict,
                 max_steps: int) -> List[Dict]:
    """Step 1: golden trace from the PS008 host driver.

    Runs run_ctl_trace (tools/pyshader_ctl.py) over the program and
    projects each snapshot into the JSONL-shaped golden-trace entry
    {'pc', 'instr', 'regs'}: pc as the insn-index pc the PS-chain uses,
    instr the RAW instruction word at that pc (decoded on demand by the
    consumer via decode_ref — keeping the raw word here keeps the trace
    byte-comparable across engines), regs as the 32-int register file.
    The input state is never mutated (run_ctl_trace copies; the entry
    regs lists are fresh copies so downstream mutants can't alias the
    trace). ControlHalt from the driver's EBREAK ends the trace at the
    last real transition; budget exhaustion propagates the driver's
    RuntimeError (loud, never a silent spin).
    """
    ctl_trace, _dmem_out, _steps = run_ctl_trace(
        imem, dmem, state, max_steps)

    golden: List[Dict] = []
    for snap in ctl_trace:
        pc = snap["pc"]
        instr = imem[pc] if 0 <= pc < len(imem) else None
        golden.append({
            "pc": pc,
            "instr": instr,
            "regs": list(snap["regs"]),
        })
    return golden


def pixel_trace(imem: List[int], n_steps: int) -> List[Dict]:
    """Step 2: the same program through the pixel CPU.

    SMOKE LANE — record, never gate (determinism clause). Drives
    SpatialRV32ICore (tools/spatial_rv32i_cpu.py) one step at a time and
    projects each state into the SAME {'pc', 'instr', 'regs'} entry
    shape as golden_trace. The pixel core's pc is BYTE-addressed
    (SPATIAL_RV32I.wgsl: next_pc = state.pc + 4u; taken branch =
    pc + imm) while the PS-chain trace pc is the insn-index — the
    projection divides by 4 (ram_base=0, word-aligned program; a
    non-multiple-of-4 pc means the core left the program image and the
    entry is dropped, loop ends on halted).

    instr is projected from the RAW imem word at the projected pc —
    same convention as golden_trace, keeping traces byte-comparable.
    Halting: EBREAK at M-mode with mtvec=0 sets halted with pc
    unchanged (raise_trap, SPATIAL_RV32I.wgsl:276-308), so the trace
    ends after the last real transition. Device acquisition is wrapped
    in the _cached-style discipline (device-exhaustion lesson, PS005):
    any wgpu failure raises RuntimeError('wgpu device acquisition
    failed: ...') — the smoke-lane test SKIPS on exactly that string.
    Budget exhaustion raises RuntimeError (loud, never a silent spin).
    """
    try:
        from tools.spatial_rv32i_cpu import SpatialRV32ICore
    except Exception as e:  # import failure = no usable backend
        raise RuntimeError("wgpu device acquisition failed: "
                           f"spatial_rv32i_cpu import error: {e}") from e

    try:
        core = SpatialRV32ICore()
    except Exception as e:
        raise RuntimeError(f"wgpu device acquisition failed: {e}") from e

    blob = b"".join(w.to_bytes(4, "little") for w in imem)
    core.load_program(blob, entry_point=0, ram_base=0)

    trace: List[Dict] = []
    try:
        st = core.get_state()
        # get_state() returns numpy scalars (np.uint32) for pc/halted —
        # coerce once so projected entries carry plain ints.
        st["pc"] = int(st["pc"])
        st["halted"] = int(st["halted"])
        if st["halted"]:
            return trace  # halted at entry: nothing executed, empty trace
        trace.append({
            "pc": st["pc"] // 4,
            "instr": imem[st["pc"] // 4]
            if st["pc"] % 4 == 0 and st["pc"] // 4 < len(imem) else None,
            "regs": [int(v) for v in st["regs"]],
        })

        steps = 0
        halted = False
        while steps < n_steps:
            core.step(1)
            steps += 1
            st = core.get_state()
            st["pc"] = int(st["pc"])
            st["halted"] = int(st["halted"])
            if st["halted"]:
                halted = True
                break
            if st["pc"] % 4 != 0:
                halted = True  # left the word-aligned image: terminal
                break
            trace.append({
                "pc": st["pc"] // 4,
                "instr": imem[st["pc"] // 4]
                if st["pc"] // 4 < len(imem) else None,
                "regs": [int(v) for v in st["regs"]],
            })
    finally:
        del core  # __del__ closes the trace fd; release the device early

    if not halted:
        raise RuntimeError(
            f"pixel_trace: budget exhausted after {n_steps} steps "
            "(loud, never a silent spin)")
    return trace


def diff_traces(ref: List[Dict], imp: List[Dict],
                ignore_regs: frozenset = IGNORED_REGS) -> Dict:
    """Step 3: entry-by-entry diff with named spec-rule verdicts.

    Compares two {'pc','instr','regs'} traces: pc first, then EVERY
    register present in BOTH sides (intersection, never union — the
    diff_qemu_gpu_traces.py:65 lesson). Returns a receipt dict:
    {'ok', 'compared', 'first_mismatch', 'spec_verdict'} where
    first_mismatch is None or {'index', 'reg', 'ref_val', 'imp_val'}
    (reg is None for a pc mismatch), and spec_verdict is None when ok,
    else a NAMED RISC-V spec rule string — a divergence is adjudicated
    against the SPEC, never against either implementation (no engine
    name appears in the verdict; PS004 lesson). ignore_regs may carry
    an explicit exclusion set for engine-specific non-architectural
    state; x0 is NOT excluded by default because x0==0 IS a spec rule.
    Length mismatch refuses loudly with its own verdict rather than
    silently zipping to the shorter side.
    """
    ignore = frozenset(ignore_regs) if ignore_regs else frozenset()

    def verdict(pc: int, kind: str, reg: Optional[int],
                ref_val: object, imp_val: object) -> Dict:
        # Map the observed divergence class to the RISC-V unprivileged
        # spec rule it violates. The verdict names the SPEC RULE, never
        # an engine (PS004 lesson: no engine adjudicates itself).
        rules = {
            "x0": "SPEC: x0 is hard-wired to zero — writes to x0 are "
                  "discarded, RV32I Unprivileged Spec §2.6 (including "
                  "any state where a side holds x0 != 0)",
            "pc": "SPEC: sequential/branch control flow — pc advances "
                  "+1 (insn-index) or to the taken-branch target, "
                  "RV32I Unprivileged Spec §2.5 branch semantics",
            "reg": "SPEC: instruction semantic result — the "
                   "destination-register value must match the ISA's "
                   "defined operation for the instruction at this pc, "
                   "RV32I Unprivileged Spec §2.4/§2.5",
            "length": "SPEC: both engines must execute the SAME "
                      "instruction stream — divergent halt point means "
                      "control flow (branch/halt semantics) diverged, "
                      "RV32I Unprivileged Spec §2.5",
        }
        fm = None
        if kind != "length":
            fm = {"index": pc, "reg": reg,
                  "ref_val": ref_val, "imp_val": imp_val}
        return {
            "ok": False,
            "compared": pc if kind != "length" else pc,
            "first_mismatch": fm,
            "spec_verdict": rules[kind],
        }

    n = min(len(ref), len(imp))
    for i in range(n):
        r, m = ref[i], imp[i]
        if r["pc"] != m["pc"]:
            return verdict(i, "pc", None, r["pc"], m["pc"])
        regs_r = r["regs"]
        regs_m = m["regs"]
        common = [j for j in range(min(len(regs_r), len(regs_m)))
                  if j not in ignore]
        for j in common:
            if regs_r[j] != regs_m[j]:
                kind = "x0" if j == 0 else "reg"
                return verdict(i, kind, j, regs_r[j], regs_m[j])

    if len(ref) != len(imp):
        return verdict(n, "length", None, len(ref), len(imp))

    return {"ok": True, "compared": len(ref),
            "first_mismatch": None, "spec_verdict": None}


def build_gate_program() -> Tuple[List[int], List[int]]:
    """Step 4: assemble + decode-verify the pinned gate program.

    Assembles the docstring-pinned 8-word loop program via
    tools/rv32i_asm.assemble (never hand-encoded — PS007 discipline),
    then decode-verifies EVERY word via PS005 decode_ref against
    field-exact expectations (fmt/opcode/funct3/imm each asserted,
    PS007 step-6 discipline). Returns (imem, dmem): imem is the 8-word
    program; dmem is 16 words of scratch data memory (word 0 is the
    SW/LW cell). The branch pin (BNE imm == -16 bytes, insn 6 -> insn
    2) is asserted here — SPEC branch semantics per
    RULING_ps008_branch_convention, the same convention the PS007 FIB
    gate landed on. A decode disagreement raises loudly: the program is
    LOCKED, so any drift is a defect, not something to re-encode.
    """
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
    assert len(blob) % 4 == 0
    imem = list(struct.unpack("<%dI" % (len(blob) // 4), blob))
    assert len(imem) == 8, len(imem)  # the pinned program shape

    # Field-exact decode verification of ALL 8 words (PS007 step-6
    # discipline): (fmt, opcode, funct3, imm). funct3=None where the
    # format carries none in decode_ref's dict.
    PINS = [
        ("I", 0x13, 0, 0),      # 0: ADDI x1, x0, 0
        ("I", 0x13, 0, 250),    # 1: ADDI x2, x0, 250
        ("S", 0x23, 2, 0),      # 2: SW x1, 0(x0)
        ("I", 0x03, 2, 0),      # 3: LW x3, 0(x0)
        ("R", 0x33, 0, 0),      # 4: ADD x1, x1, x2
        ("I", 0x13, 0, -1),     # 5: ADDI x2, x2, -1
        ("B", 0x63, 1, -16),    # 6: BNE x2, x0, loop  (insn 6 -> insn 2)
        ("SYSTEM", 0x73, 0, 1), # 7: EBREAK
    ]
    for i, (w, (fmt, opc, f3, imm)) in enumerate(zip(imem, PINS)):
        d = decode_ref(w)
        assert d["fmt"] == fmt, (i, hex(w), d["fmt"], fmt)
        assert d["opcode"] == opc, (i, hex(w), d["opcode"], opc)
        assert d["funct3"] == f3, (i, hex(w), d["funct3"], f3)
        assert d["imm"] == imm, (i, hex(w), d["imm"], imm)

    dmem = [0] * 16
    return imem, dmem


def gate_golden_trace() -> Dict:
    """Step 4: THE PS011 roadmap gate.

    Runs the pinned gate program through golden_trace (the PS008 host
    driver — deterministic, the GATING engine) and adjudicates the
    receipt against HAND-DERIVED pins, never engine-vs-engine
    self-agreement (PS004 lesson):
      - transitions == 1252 exactly (2 init + 5 x 250, >=
        GOLDEN_MIN_TRANSITIONS by formula);
      - final x1 == 31375 (sum 1..250), x2 == 0, all other regs 0
        except x3 == 31375 (the acc value at the last SW);
      - trace_len == 1253 (initial snapshot + 1252 transitions);
      - spec_verdicts == [] (golden-vs-pins agreement);
      - pixel_diff: RECORDED, never gated (determinism clause) — the
        ref-vs-pixel diff lands in the receipt as a diff_traces receipt
        dict, or the string 'skipped' when the wgpu device is absent.

    Non-vacuity (gate proven able to fail) is machine-checked in
    tests/test_pyshader_golden.py via a one-off arithmetic-slip mutant
    through the same receipt path.
    """
    imem, dmem = build_gate_program()

    from tools.pyshader_fde import new_state

    trace = golden_self().golden_trace(
        imem, dmem, new_state(), max_steps=10000)

    spec_verdicts: List[str] = []
    ok = True

    def pin_fail(msg: str) -> None:
        nonlocal ok
        ok = False
        spec_verdicts.append(msg)

    # Structure pins (formula: 2 init + 5/iter x 250 iterations).
    transitions = len(trace) - 1
    if transitions != 2 + 5 * 250:
        pin_fail(
            "SPEC: executed-transition count %d != hand-derived 1252 "
            "(2 init + 5/iter x 250) — control-flow semantics diverged, "
            "RV32I Unprivileged Spec §2.5" % transitions)
    if transitions < GOLDEN_MIN_TRANSITIONS:
        pin_fail(
            "SPEC: %d transitions < the roadmap's 1k threshold — the "
            "program does not exercise a non-trivial stream" % transitions)

    # Final-state pins (hand-derived: x1 = sum(1..250) = 31375).
    fin = trace[-1]["regs"]
    expected_x1 = 250 * 251 // 2
    if fin[1] != expected_x1:
        pin_fail(
            "SPEC: final x1 %d != hand-derived %d (sum 1..250) — "
            "register-result semantics, RV32I Unprivileged Spec §2.4"
            % (fin[1], expected_x1))
    if fin[2] != 0:
        pin_fail(
            "SPEC: final x2 %d != 0 (counter exhausted) — "
            "RV32I Unprivileged Spec §2.4" % fin[2])
    if fin[3] != 31374:
        pin_fail(
            "SPEC: final x3 %d != hand-derived 31374 (acc at the last "
            "LW = sum 1..249 — the loop's LW at insn 3 precedes the ADD "
            "at insn 4, so the final architectural x3 is one add short "
            "of x1) — load-result semantics, RV32I Unprivileged Spec "
            "§2.4/§2.6" % fin[3])
    for j in range(32):
        if j in (1, 3):
            continue
        if j == 2:
            continue  # pinned to 0 above
        if fin[j] != 0:
            pin_fail(
                "SPEC: x%d is not architecturally written by this "
                "program but holds %d — RV32I Unprivileged Spec §2.4"
                % (j, fin[j]))
            break

    if ok:
        # x3 sequence sampled at each iteration's LW COMMIT: trace
        # entries are snapshots BEFORE execution, so the entry at insn
        # 4 (the ADD right after the LW) carries iteration k's loaded
        # x3. idx = 2 init + 5*(k-1) + 2 (insn 4 of iteration k,
        # 1-based k). Iteration k's LW loads the acc its own SW just
        # stored = acc after k-1 DESCENDING adds (250+249+...): x3(k) =
        # 0 for k=1, else (k-1)*(502-k)//2 — k=2 -> 250, k=3 -> 499,
        # k=250 -> 31374 (== the docstring's "acc at the last SW").
        # Measured against the real trace (probe_ps011_x3_pin.py):
        # insn-3 snapshots (idx,x3_prev,x1) = (3,0,0), (8,0,250),
        # (13,250,499) — confirming the one-snapshot lag.
        def want(k):
            return 0 if k == 1 else (k - 1) * (502 - k) // 2
        for k in (1, 2, 3, 250):
            idx = 2 + 5 * (k - 1) + 2
            v = trace[idx]["regs"][3]
            if v != want(k):
                pin_fail(
                    "SPEC: x3 after iteration %d's LW = %d, hand-derived"
                    " %d (acc stored by that iteration's SW) — memory "
                    "round-trip (SW/LW) semantics, RV32I Unprivileged "
                    "Spec §2.6" % (k, v, want(k)))
                break

    receipt: Dict = {
        "ok": ok,
        "transitions": transitions,
        "final": {"x1": fin[1], "x2": fin[2], "x3": fin[3]},
        "trace_len": len(trace),
        "spec_verdicts": spec_verdicts,
        "pixel_diff": "skipped",
    }

    if ok:
        # SMOKE LANE (determinism clause): the ref-vs-pixel diff is
        # RECORDED, never gating. Absent device -> literal 'skipped'.
        try:
            ptrace = pixel_trace(imem, 10000)
            receipt["pixel_diff"] = diff_traces(trace, ptrace)
        except RuntimeError as e:
            if "wgpu device acquisition failed" not in str(e):
                raise
            receipt["pixel_diff"] = "skipped"

    return receipt
