"""tools/pyshader_fde.py — PS007: fetch-decode-execute composition.

SKELETON (skeleton-driven-development, Phase 1+2): interfaces LOCKED,
bodies stubbed. This file is the spec; the roadmap PS007 section and
.builder_queue/brief_ps007_fde_composition.md are the consumer
contract. The builder populates ONE stub per run; each stub's gate
clause lives in the brief's step table.

Architecture (all host-side; the GPU runs ONE compiled step function
per dispatch — composition happens on the host):

    program (.word/.insn list)
        │  fetch()      -> instruction word at pc
        │  decode()     -> PS005 toolchain (tools/pyshader_rvdecode)
        │  dispatch()   -> PS006 step function (tools/pyshader_rvexec)
        │               -> GPU triple-differential + ref (4-way check)
        ▼
    state dict {pc, regs[32]} advanced ONE instruction per run_fde tick
        │  run_fde()    -> full trace (list of state snapshots)
        ▼
    gate_fibonacci()    -> 10-step Fibonacci trace-diff vs the PS004
                           cross-validation fixture

Interfaces below are LOCKED (skeleton protocol): the builder populates
bodies, never signatures. If a signature looks wrong, file
REPAIR_PENDING per the skeleton handoff contract — do not edit.

What the stubs return is deliberate: state dicts are returned
UNMODIFIED (so a structural test can assert "stub = no-op"), and every
stub raises NotImplementedError where silence would be dangerous.
"""
from __future__ import annotations

from typing import Dict, List, Optional, TypedDict

from tools.pyshader_compiler import U32_MASK
from tools.pyshader_rvdecode import decode_ref
from tools.pyshader_rvexec import ref_alu_i, ref_alu_r

__all__ = [
    "REG_N", "PC0", "FIB_PROGRAM", "FIB_EXPECTED_TRACE_HEAD",
    "State", "new_state", "fetch", "load_program", "execute_one",
    "run_fde", "gate_fibonacci",
]

# ── locked constants ────────────────────────────────────────────────────

REG_N = 32          # RV32I register file width
PC0 = 0             # programs start at instruction index 0

# Fibonacci in the PS006 ALU subset + branches (BEQ/BNE/ADDI):
#   x1 = a, x2 = b, x3 = temp; loop: x3 = x1 + x2; x1 = x2; x2 = x3
# Encoded words are FIXED here so the skeleton pins the program before
# any implementation exists (pin external facts, do not restate them).
# Layout (word index -> insn):
#   0: ADDI x1, x0, 1      # a = 1
#   1: ADDI x2, x0, 1      # b = 1
#   2: ADD  x3, x1, x2     # loop: t = a + b
#   3: ADDI x1, x2, 0      # a = b
#   4: ADDI x2, x3, 0      # b = t
#   5: ADDI x5, x5, -1     # i--  (x5 preloaded with loop count)
#   6: BNE  x5, x0, -16    # if i != 0 goto 2  (offset -4 insns; word
#                          # 0xFE0298E3 — SPEC semantics per
#                          # RULING_ps008_branch_convention: target =
#                          # pc + imm//4 = 6 - 4 = 2; supersedes the
#                          # ps007 -20/pc+1+imm//4 convention)
# NOTE: BNE is NOT in the PS006 ALU core and NOT in PS005's decode
# fixture list as an executed class; step_b (branch) is PS007 scope —
# that is precisely why this program is the gate.
FIB_LOOP_COUNT_DEFAULT = 8

# First 6 reg values after 8 iterations of the loop above, starting
# x1=x2=1 (hand-computed; the trace-diff adjudicates against THIS plus
# the PS004 recorded trace, not against either engine):
#   iter: x3 = x1+x2 before swap... (documented in the brief)
FIB_EXPECTED_TRACE_HEAD = "FIB-TRACE-PINNED-IN-BRIEF"

# Fibonacci program image (PS007 step 6). Every word decode-verified
# field-exact via PS005 decode_ref (fmt/opcode/rd/rs1/rs2/imm) at the
# landing revision; word 6 per RULING_ps008_branch_convention (BNE
# imm -16 bytes = -4 insns; SPEC semantics: target = pc + imm//4 =
# 6 - 4 = 2).
FIB_PROGRAM = [
    0x00100093,  # 0: ADDI x1, x0, 1      a = 1
    0x00100113,  # 1: ADDI x2, x0, 1      b = 1
    0x002081B3,  # 2: ADD  x3, x1, x2     loop: t = a + b
    0x00010093,  # 3: ADDI x1, x2, 0      a = b
    0x00018113,  # 4: ADDI x2, x3, 0      b = t
    0xFFF28293,  # 5: ADDI x5, x5, -1     i--
    0xFE0298E3,  # 6: BNE  x5, x0, -16    if i != 0 goto 2
]

# Hand-computed pin (brief:35-38; the trace-diff adjudicates against
# THIS plus the PS004 recorded trace, not against either engine).
FIB_X3_SEQUENCE = [2, 3, 5, 8, 13, 21, 34, 55]
FIB_EXPECTED_FINAL = {1: 34, 2: 55, 3: 55, 5: 0}
FIB_EXPECTED_STEPS = 42  # 2 setup + 8 iterations x 5 insns


class State(TypedDict):
    """Locked state shape: program counter + 32-word register file."""
    pc: int
    regs: List[int]


def new_state(regs: Optional[List[int]] = None) -> State:
    """Fresh hart state. Pure utility — IMPLEMENTED in skeleton phase.

    regs: optional initial register file (x0..x31); missing/short
    entries zero-filled. x0 is NOT forced to zero here (PS006 honest
    boundary carries into PS007 until x0-write suppression is gated)."""
    r = [0] * REG_N
    if regs:
        for i, v in enumerate(regs[:REG_N]):
            r[i] = v & U32_MASK
    return {"pc": PC0, "regs": r}


def load_program(words: List[int]) -> List[int]:
    """Pin a program image (list of u32 instruction words). Pure
    utility — IMPLEMENTED: masks each word to 32 bits, returns a fresh
    list. No imem bounds logic here; fetch enforces bounds."""
    return [w & U32_MASK for w in words]


def fetch(pc: int, imem: List[int]) -> int:
    """IMPLEMENTED (PS007 step 1). Return imem[pc]; out-of-bounds pc
    raises IndexError (bounds fault, not silent zero — silent fetch-0
    halts invisibly). Negative pc raises explicitly: Python's negative
    indexing would otherwise wrap to the program tail silently."""
    if not 0 <= pc < len(imem):
        raise IndexError(f"fetch: pc {pc} out of bounds (imem len {len(imem)})")
    return imem[pc]


def execute_one(state: State, imem: List[int]) -> State:
    """STUB (builder steps 2-4). Compose ONE fetch-decode-execute
    transition: fetch at state['pc'], decode via the PS005 toolchain,
    execute via the PS006 step functions (R/I) or step_b (B-type,
    PS007-new), return a NEW state dict (never mutate the input —
    traces need the old snapshot). pc advances by 1 except a TAKEN
    branch, which sets pc = pc + branch_offset(insns) (SPEC semantics:
    pc + imm//4 per RULING_ps008_branch_convention — no +1).

    Sub-steps in the brief:
      step 2: straight-line R/I (pc always +1) — IMPLEMENTED below
      step 3: B-type decode + step_b taken/not-taken (STILL STUBBED —
        a decoded B word raises NotImplementedError until step 3)
      step 4: x0-write suppression (writes to x0 discarded)
    """
    d = decode_ref(fetch(state["pc"], imem))
    fmt = d["fmt"]

    # ── B-type (PS007 step 3): BNE only; taken → pc + imm/4 (SPEC) ──────
    if fmt == "B":
        if d["opcode"] != 0x63 or d["funct3"] != 1:
            raise NotImplementedError(
                f"PS007 step 3: B-type covers BNE (funct3=1) only; got"
                f" funct3={d['funct3']} at pc={state['pc']}"
            )
        regs = list(state["regs"])
        if d["imm"] % 4 != 0:
            raise NotImplementedError(
                f"PS007 step 3: branch offset {d['imm']} not a whole"
                f" number of instructions (insn-granular pc only)"
            )
        taken = regs[d["rs1"]] != regs[d["rs2"]]
        if taken:
            # SPEC branch semantics (RULING_ps008_branch_convention):
            # next pc = pc + imm//4 — no +1. The old +1 convention
            # (RULING_ps007_fib_branch_offset) is superseded; PS010+
            # trace-diffs against the pixel-CPU/QEMU oracle, so the
            # executor must agree with the oracle, not with itself.
            return {"pc": state["pc"] + d["imm"] // 4, "regs": regs}
        return {"pc": state["pc"] + 1, "regs": regs}

    if fmt not in ("R", "I") or (fmt == "I" and d["opcode"] != 0x13):
        raise NotImplementedError(
            f"PS007: execute_one covers R (0x33), ALU-I (0x13) and BNE"
            f" (0x63/funct3=1) only; got fmt={fmt!r}"
            f" (opcode 0x{d['opcode']:02x}) at pc={state['pc']}"
        )
    regs = list(state["regs"])
    if fmt == "R":
        result = ref_alu_r(d["funct3"], d["funct7"],
                           regs[d["rs1"]], regs[d["rs2"]]) & U32_MASK
    else:
        # ALU-immediate subset (opcode 0x13): imm in the rs2 operand slot;
        # funct7hi (shift-op code) is imm bits [11:5] per RV32I encoding
        # — decode_ref's I dict has no funct7 field (it aliases imm).
        funct7hi = (d["imm"] >> 5) & 0x7F
        result = ref_alu_i(d["funct3"], funct7hi,
                           regs[d["rs1"]], d["imm"]) & U32_MASK
    # x0-write suppression (PS007 step 4, closes the PS006 honest
    # boundary): RV32I hardwires x0 to zero — rd=0 writes are discarded.
    if d["rd"] != 0:
        regs[d["rd"]] = result
    return {"pc": state["pc"] + 1, "regs": regs}


def run_fde(imem: List[int], state: State, n_steps: int) -> List[State]:
    """IMPLEMENTED (PS007 step 5). Drive execute_one n_steps times,
    snapshot every state. trace length == n_steps + 1 (includes the
    initial state as trace[0]); the input state dict is never mutated —
    execute_one already returns fresh dicts, so the trace is a chain of
    independent snapshots."""
    trace: List[State] = [{"pc": state["pc"], "regs": list(state["regs"])}]
    current = state
    for _ in range(n_steps):
        current = execute_one(current, imem)
        trace.append(current)
    return trace


def gate_fibonacci() -> Dict:
    """IMPLEMENTED (PS007 step 6 — the roadmap gate). Build FIB_PROGRAM
    with x5 = FIB_LOOP_COUNT_DEFAULT, run_fde FIB_EXPECTED_STEPS, and
    adjudicate the final register state + x3-per-iteration sequence
    against the HAND-COMPUTED pin above (4-way discipline: the host
    FDE result is compared to the pin, and the GPU legs of the ADD and
    BNE dispatches are separately verified on actual trace operand
    values via the PS006 triple-differential + a hand-computed ref, so
    no engine adjudicates itself).

    Returns a receipt dict; ok=False on any pin mismatch (it does NOT
    raise on mismatch — the receipt IS the gate artifact)."""
    imem = load_program(FIB_PROGRAM)

    st = new_state()
    st["regs"][5] = FIB_LOOP_COUNT_DEFAULT
    trace = run_fde(imem, st, FIB_EXPECTED_STEPS)

    # pin 1: trace shape
    shape_ok = len(trace) == FIB_EXPECTED_STEPS + 1 and trace[0]["pc"] == PC0

    # pin 2: final registers match the hand-computed values EXACTLY
    fin = trace[-1]["regs"]
    final_regs = {r: fin[r] for r in FIB_EXPECTED_FINAL}
    others_zero = all(fin[i] == 0 for i in range(REG_N)
                      if i not in FIB_EXPECTED_FINAL)
    final_ok = (final_regs == FIB_EXPECTED_FINAL) and others_zero

    # pin 3: x3-per-iteration sequence, sampled at each ADD commit
    x3_sequence = [snap["regs"][3] for snap in trace[1:]
                   if snap["pc"] == 3]
    sequence_ok = x3_sequence == FIB_X3_SEQUENCE

    # pin 4: GPU legs on ACTUAL trace operand values (4-way: GPU,
    # oracle, pixel CPU, hand-computed ref — PS004 lesson).
    from tools.pyshader_rvexec import run_alu_differential
    from tools.pyshader_wgsl import run_triple_differential

    # ADD x3,x1,x2 at pc=2 — last iteration's operands from the trace.
    add_snap = [s for s in trace if s["pc"] == 2][-1]
    a, b = add_snap["regs"][1], add_snap["regs"][2]
    r_add = run_alu_differential(True, 0, 0x00, a, b)
    add_ref = (a + b) & U32_MASK  # hand-computed
    gpu_add_ok = (r_add["ok"] and r_add["gpu_r9"] == add_ref)

    # BNE x5,x0,-20 at pc=6 — a TAKEN instance's operand from the
    # trace; the comparison itself goes through the GPU (branch-free
    # single-statement style, same as the PS006 step sources).
    bne_snaps = [s for s in trace if s["pc"] == 6]
    x5v = bne_snaps[-2]["regs"][5] if len(bne_snaps) >= 2 else 0
    bne_ref = 1 if x5v != 0 else 0  # hand-computed
    r_bne = run_triple_differential(
        "def step_bne(rs1v, rs2v):\n"
        "    t = 0\n"
        "    if rs1v != rs2v:\n"
        "        t = 1\n"
        "    return t\n",
        [x5v, 0])
    gpu_bne_ok = (r_bne["ok"] and r_bne["gpu_r9"] == bne_ref)

    ok = shape_ok and final_ok and sequence_ok and gpu_add_ok and gpu_bne_ok
    return {
        "ok": ok,
        "steps_executed": FIB_EXPECTED_STEPS,
        "final_regs": final_regs,
        "x3_sequence": x3_sequence,
        "trace_len": len(trace),
        "shape_ok": shape_ok,
        "final_ok": final_ok,
        "sequence_ok": sequence_ok,
        "gpu_add_ok": gpu_add_ok,
        "gpu_bne_ok": gpu_bne_ok,
        "gpu_add": {"gpu_r9": r_add["gpu_r9"], "ref": add_ref,
                    "oracle_r9": r_add["oracle_r9"],
                    "cpu_r9": r_add["cpu_r9"]},
        "gpu_bne": {"gpu_r9": r_bne["gpu_r9"], "ref": bne_ref,
                    "oracle_r9": r_bne["oracle_r9"],
                    "cpu_r9": r_bne["cpu_r9"]},
    }
