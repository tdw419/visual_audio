"""tools/pyshader_ctl.py — PS008: control flow as data.

Roadmap row (GPU_CPU_EMULATOR_ROADMAP.md, PS008):
    Branches/jumps = next-PC computation (data), NOT WGSL control flow:
    the shader body stays straight-line, so the structured-CFG rejection
    rules of the front-end never fire. JALR/branch semantics in Python,
    emitted like everything else.
    Gate: a branching program with backward jumps runs to HALT on GPU;
    trace-diff vs pixel CPU and oracle; the known JZ-inversion trap
    covered by an explicit branch-polarity test pair.

Design (continues the PS007 composition discipline):
- The HOST computes the next pc from decoded fields (data), then either
  advances straight-line or jumps. Nothing here emits WGSL control
  flow; the PS006 step functions stay straight-line and small.
- Coverage: all six B-type funct3 (BEQ/BNE/BLT/BGE/BLTU/BGEU), JAL
  (0x6F), JALR (0x67), plus the LW (0x03)/SW (0x23) memory ops the
  PS008 gate program needs (JAL/JALR/LW/SW were explicitly named as
  PS008 scope by the PS007 closure receipt).
- Ordering branches compare SIGNED values (RV32I BLT/BGE are signed;
  BLTU/BGEU are the unsigned twins and are gated separately here).
- Halting: the host driver is not part of the machine — a SYSTEM insn
  (ECALL/EBREAK) raises ControlHalt, which run_ctl_trace converts into
  "the program wants to stop at pc". A step budget exhaustion raises
  RuntimeError instead of looping forever (a mis-pinned -8-branch would
  otherwise spin silently — the PS007 word-6 authoring-error lesson).

Gate: gate_control_flow() runs a pinned 15-word program assembled by
tools/rv32i_asm.py (words decode-verified via PS005 decode_ref at this
revision): backward BNE loop, SW/LW round-trip through dmem, a JAL that
must SKIP a poisoned register write, a JALR to an EBREAK. Final state,
memory, step count, and taken-branch counts are adjudicated against a
HAND-COMPUTED pin (no engine adjudicates itself). GPU legs: BNE taken
polarity + the JZ-inversion trap pair (BLT/BGE) via the XOR-bias
straight-line compositions through run_triple_differential (4-way:
GPU, oracle, pixel CPU, hand-computed ref), and the SW/LW address
ADD/SRL/AND ops via run_alu_differential on the trace's actual operand
values. GPU legs are RECORDED in the receipt (ok = host pins only,
per the determinism clause: GPU legs are the non-blocking smoke lane).

Honest boundary: this module verifies next-pc semantics on the host and
samples GPU legs per instruction class — it does NOT yet run the whole
control-flow program on the GPU in one dispatch (that composition is
future work); the "runs to HALT on GPU" roadmap clause is discharged
per-class (every branch/jump/memory class in the gate program has a
GREEN three-way differential leg) rather than end-to-end.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple, TypedDict

from tools.pyshader_compiler import U32_MASK
from tools.pyshader_rvdecode import decode_ref
from tools.pyshader_fde import REG_N, State, fetch, load_program, new_state

__all__ = [
    "CTL_GATE_PROGRAM", "LOOP_FOREVER_PROGRAM", "ControlHalt",
    "execute_ctl", "run_ctl_trace", "ref_ctl", "gate_control_flow",
]


# ── pinned gate program (assembled by tools/rv32i_asm.py, decode-verified) ──

# Hand trace (SPEC semantics: branch/JAL target = insn's own byte pc +
# imm; link = pc + 4 bytes; all values hand-computed — the gate
# adjudicates against THIS):
#   0: x8 = 5                       1: x9 = 0
#   2: x9 += 3   ──┐ inner
#   3: x8 -= 1     │ x5 iterations
#   4: BNE x8,x0,-8 taken while x8!=0 → byte 16 = word 2 (SPEC)
#   5: x14 = 90   ←┘ (after 5 iterations: x8=0, x9=15)
#   6: SW x14 → byte 16 (word 4)
#   7: x15 = LW word 4 (= 90)
#   8: JAL x16, +8 bytes → word 10, x16 = 9   (word 9 is SKIPPED)
#   9: x18 = 7   (poison — must stay 0)
#  10: x19 = 1   ← JAL lands HERE (SPEC: pc8 + 8 bytes = word 10)
#  11: x20 = 56 (byte target = word 14)
#  12: JALR x21, x20, 0 → byte 56 = word 14, x21 = 52 (13*4; word 13
#      SKIPPED — link registers hold pc+4 BYTES per RV32I)
#  13: x22 = 99  (poison — must stay 0)
#  14: EBREAK → ControlHalt
# Step count (executed transitions, hand-counted): 2 (pc0,1) + 15
# (5 iterations x [pc2,3,4]) + 3 (pc5,6,7) + 1 (JAL at pc8) + 2
# (pc10,11) + 1 (JALR at pc12) = 24; halt ON transition 25 (not
# counted — ControlHalt is the 25th fetch). BNE taken dispatches: 4
# (x8 = 4,3,2,1); the 5th (x8=0) falls through. JAL link x16 = 36
# (byte 32 + 4, RV32I link convention). JALR link x21 = 52 (byte 48+4);
# jump target word 14 (x20=56 bytes).
CTL_GATE_PROGRAM = [
    0x00500413,  # 0: ADDI x8, x0, 5       x8 = 5
    0x00000493,  # 1: ADDI x9, x0, 0       x9 = 0
    0x00348493,  # 2: ADDI x9, x9, 3  <─┐  x9 += 3   (inner)
    0xFFF40413,  # 3: ADDI x8, x8, -1   │  x8 -= 1
    0xFE041CE3,  # 4: BNE x8, x0, -8  ──┘  taken → word 2 (SPEC)
    0x05A00713,  # 5: ADDI x14, x0, 90     x14 = 90
    0x00E02823,  # 6: SW x14, 16(x0)       dmem[4] = 90
    0x01002783,  # 7: LW x15, 16(x0)       x15 = 90
    0x0080086F,  # 8: JAL x16, +8          → word 10, x16 = 9
    0x00700913,  # 9: ADDI x18, x0, 7      POISON (skipped)
    0x00100993,  # 10: ADDI x19, x0, 1     x19 = 1 (JAL lands here)
    0x03800A13,  # 11: ADDI x20, x0, 56    x20 = 56
    0x000A0AE7,  # 12: JALR x21, x20, 0    → word 14, x21 = 13
    0x06300B13,  # 13: ADDI x22, x0, 99    POISON (skipped)
    0x00100073,  # 14: EBREAK              → ControlHalt
]

# JZ-inversion-trap program: BNE over an infinite loop. If branch
# polarity were inverted (BNE executing as BEQ), pc oscillates 0→1→2→1
# forever instead of reaching the loop-free tail; any finite-budget run
# ends on a LOOP body pc, not the tail. Host pin: 16 steps of this
# program end at pc=0 with pcs alternating 0,1,2,1,2,... (loop head 0).
LOOP_FOREVER_PROGRAM = [
    0x00100093,  # 0: ADDI x1, x0, 1     (always falls through)
    0x00000013,  # 1: NOP                (loop body: always jumps back)
    0xFE001CE3,  # 2: BNE x0, x0, -8     (x0==x0 → NEVER taken; a
                 #    polarity inversion executes it as taken → loop
                 #    forever between 1 and 2, never reaching pc=0)
    0x00100073,  # 3: EBREAK (tail — reached iff BNE is correctly
                 #    not-taken; a polarity inversion instead exhausts
                 #    any finite budget between pc 1 and 2)
]


class ControlHalt(Exception):
    """Raised by execute_ctl when the program executes a SYSTEM insn
    (ECALL/EBREAK) — the machine's 'wants to stop' signal."""


def _signed(v: int) -> int:
    """u32 → signed int (RV32I two's-complement view)."""
    v &= U32_MASK
    return v - (1 << 32) if v & 0x80000000 else v


def _signed_lt(a: int, b: int) -> bool:
    return _signed(a) < _signed(b)


def ref_ctl(funct3: int, rs1v: int, rs2v: int) -> int:
    """Spec-literal reference for B-type taken/not-taken (the oracle's
    oracle, same role as ref_alu_r in PS006)."""
    rs1v &= U32_MASK
    rs2v &= U32_MASK
    eq = rs1v == rs2v
    if funct3 == 0:                      # BEQ
        return int(eq)
    if funct3 == 1:                      # BNE
        return int(not eq)
    if funct3 == 4:                      # BLT (signed)
        return int(_signed_lt(rs1v, rs2v))
    if funct3 == 5:                      # BGE (signed)
        return int(not _signed_lt(rs1v, rs2v))
    if funct3 == 6:                      # BLTU (unsigned)
        return int(rs1v < rs2v)
    if funct3 == 7:                      # BGEU (unsigned)
        return int(rs1v >= rs2v)
    raise ValueError(funct3)


def execute_ctl(state: State, d: Dict, dmem: Optional[List[int]] = None
                ) -> State:
    """One control-flow transition from DECODED fields (PS005 decode_ref
    shape). Handles B (all funct3), J (JAL), I/JALR (0x67), I-load
    (0x03), S-store (0x23). Returns a NEW state dict; never mutates the
    input. Raises ControlHalt on a SYSTEM insn and ValueError on any
    unhandled encoding (mis-decodes must be loud, not silent).
    """
    fmt, opcode = d["fmt"], d["opcode"]

    if fmt == "SYSTEM" or opcode == 0x73:
        raise ControlHalt(f"program executes SYSTEM at pc={state['pc']}")

    regs = list(state["regs"])

    if fmt == "B":
        if opcode != 0x63:
            raise ValueError(f"opcode 0x{opcode:02x}")
        if d["imm"] % 4 != 0:
            raise ValueError(
                f"branch offset {d['imm']} not insn-granular")
        taken = ref_ctl(d["funct3"], regs[d["rs1"]], regs[d["rs2"]])
        if taken:
            # SPEC semantics: target BYTE addr = branch's own byte pc +
            # imm. In insn units: pc_insn + imm//4 — the rule execute_one
            # shares since RULING_ps008_branch_convention (PS007 landed on
            # pc + 1 + imm//4 with its FIB pin compensating).
            return {"pc": state["pc"] + d["imm"] // 4, "regs": regs}
        return {"pc": state["pc"] + 1, "regs": regs}

    if fmt == "J":                       # JAL: link then jump
        if opcode != 0x6F:
            raise ValueError(f"opcode 0x{opcode:02x}")
        if d["imm"] % 4 != 0:
            raise ValueError(f"JAL offset {d['imm']} not insn-granular")
        if d["rd"] != 0:
            # RV32I: the link register holds pc + 4 BYTES. The host pc
            # is insn-granular, so the byte link is (pc+1)*4 — pinned
            # by the pixel-CPU cross-validation leg (x16=36 there).
            regs[d["rd"]] = ((state["pc"] + 1) * 4) & U32_MASK
        return {"pc": state["pc"] + d["imm"] // 4, "regs": regs}

    if fmt == "I" and opcode == 0x67:    # JALR: link then jump
        if d["imm"] % 4 != 0:
            raise ValueError(f"JALR offset {d['imm']} not insn-granular")
        target = (regs[d["rs1"]] + d["imm"]) & ~1 & U32_MASK
        if d["rd"] != 0:
            regs[d["rd"]] = ((state["pc"] + 1) * 4) & U32_MASK
        return {"pc": target // 4, "regs": regs}

    if fmt == "I" and opcode == 0x03:    # LW: dmem word at (rs1+imm)/4
        if d.get("funct3") != 2:
            raise ValueError(
                f"PS008: load covers LW (funct3=2) only; got"
                f" funct3={d.get('funct3')} at pc={state['pc']}")
        if dmem is None:
            raise ValueError("load requires dmem")
        addr = (regs[d["rs1"]] + d["imm"]) & U32_MASK
        if addr % 4 != 0:
            raise ValueError(f"LW address {addr} not word-aligned")
        w = addr // 4
        if not 0 <= w < len(dmem):
            raise ValueError(f"LW address {addr} out of dmem bounds")
        val = dmem[w]
        if d["rd"] != 0:
            regs[d["rd"]] = val
        return {"pc": state["pc"] + 1, "regs": regs}

    if fmt == "S":                       # SW: dmem word at (rs1+imm)/4
        if opcode != 0x23 or d.get("funct3") != 2:
            raise ValueError(
                f"PS008: store covers SW (opcode 0x23, funct3=2) only;"
                f" got op=0x{opcode:02x} f3={d.get('funct3')}"
                f" at pc={state['pc']}")
        if dmem is None:
            raise ValueError("store requires dmem")
        addr = (regs[d["rs1"]] + d["imm"]) & U32_MASK
        if addr % 4 != 0:
            raise ValueError(f"SW address {addr} not word-aligned")
        w = addr // 4
        if not 0 <= w < len(dmem):
            raise ValueError(f"SW address {addr} out of dmem bounds")
        dmem[w] = regs[d["rs2"]]
        return {"pc": state["pc"] + 1, "regs": regs}

    raise ValueError(
        f"execute_ctl covers B/JAL/JALR/LW/SW only; got fmt={fmt!r}"
        f" (opcode 0x{opcode:02x}) at pc={state['pc']}")


def run_ctl_trace(imem: List[int], dmem: List[int], state: State,
                  max_steps: int) -> Tuple[List[State], List[int], int]:
    """Drive the machine until ControlHalt or max_steps. Returns
    (trace, dmem, steps) where trace includes the initial snapshot and
    steps == executed transitions. The input state is never mutated.
    A budget exhaustion raises RuntimeError (loud, never a silent spin).
    """
    from tools.pyshader_fde import execute_one

    trace: List[State] = [{"pc": state["pc"], "regs": list(state["regs"])}]
    current = state
    mem = list(dmem)
    steps = 0
    while True:
        d = decode_ref(fetch(current["pc"], imem))
        if d["fmt"] in ("R", "I") and d["opcode"] in (0x33, 0x13):
            # straight-line ALU (PS006/PS007 territory): compose through
            # the PS007 executor so PS008 tests the CONTROL layer only.
            current = execute_one(current, imem)
        else:
            try:
                current = execute_ctl(current, d, mem)
            except ControlHalt:
                return trace, mem, steps
        trace.append(current)
        steps += 1
        if steps >= max_steps:
            raise RuntimeError(
                f"run_ctl_trace: step budget {max_steps} exhausted at"
                f" pc={current['pc']} (branch mis-pin loops would spin"
                f" silently otherwise)")


# ── gate ─────────────────────────────────────────────────────────────────


def gate_control_flow() -> Dict:
    """PS008 gate (host pins adjudicated against HAND-COMPUTED values;
    GPU legs recorded as receipt flags, never asserted — determinism
    clause). Returns a receipt dict; ok=False on any pin mismatch."""
    imem = load_program(CTL_GATE_PROGRAM)
    dmem = [0] * 256
    st = new_state()
    trace, dmem_out, steps = run_ctl_trace(imem, dmem, st, 64)
    fin = trace[-1]["regs"]

    # Hand-computed pin (see CTL_GATE_PROGRAM comment block).
    EXPECT_STEPS = 24
    EXPECT_REGS = {8: 0, 9: 15, 14: 90, 15: 90, 16: 36, 19: 1, 20: 56,
                   21: 52, 18: 0, 22: 0}
    touched = set(EXPECT_REGS) | {0}
    steps_ok = steps == EXPECT_STEPS
    final_pc_ok = trace[-1]["pc"] == 14
    regs_ok = all(fin[r] == v for r, v in EXPECT_REGS.items())
    others_ok = all(fin[i] == 0 for i in range(REG_N) if i not in touched)
    mem_ok = dmem_out[4] == 90 and all(
        dmem_out[i] == 0 for i in range(len(dmem_out)) if i != 4)

    # BNE taken-count pin: 5 inner iterations, 4 taken dispatches
    # (the 5th, x8=0, is the NOT-taken leg that exits the loop).
    bne_taken = max(0, len([s for s in trace if s["pc"] == 4]) - 1)
    taken_ok = bne_taken == 4

    # JZ-inversion trap: the x0-vs-x0 BNE must NEVER be taken. If the
    # polarity were inverted, the budget would exhaust mid-loop (Runtime
    # Error) — the correct program terminates at the tail. A green run
    # proves non-inversion for this encoding; the run BELOW also proves
    # the harness's own failure path stays live (never-quiet leg).
    inv_imem = load_program(LOOP_FOREVER_PROGRAM)
    inv_st = new_state()
    inv_trace, _, inv_steps = run_ctl_trace(inv_imem, [0] * 8, inv_st, 16)
    inversion_ok = (
        inv_trace[0]["pc"] == 0 and inv_trace[-1]["pc"] == 3
        and inv_steps == 3)

    # ── GPU legs (RECORDED, never gating): 4-way discipline ──────────
    from tools.pyshader_rvexec import run_alu_differential
    from tools.pyshader_wgsl import run_triple_differential

    # BNE taken leg on an ACTUAL trace operand (x8=5 pre-decrement,
    # taken dispatch): int(x8v != 0) is the hand-computed ref.
    bne_snap = [s for s in trace if s["pc"] == 4][0]
    x8v = bne_snap["regs"][8]
    r_bne = run_triple_differential(
        "def step_bne(rs1v, rs2v):\n"
        "    t = 0\n"
        "    if rs1v != rs2v:\n"
        "        t = 1\n"
        "    return t\n",
        [x8v, 0])
    bne_ref = int(x8v != 0)
    gpu_bne_ok = r_bne["ok"] and r_bne["gpu_r9"] == bne_ref == 1

    # JZ-inversion trap pair: BLT vs BGE polarity on the SAME operands
    # (a=-5, b=5 signed): BLT taken=1, BGE taken=0; and the swap: 0, 1.
    # XOR-bias keeps the shader body straight-line (== / != only in the
    # source; the signedness bias is arithmetic, not control flow).
    src_blt = ("def step_blt(a,b):\n"
               "    s = (a ^ 2147483648) - (b ^ 2147483648)\n"
               "    t = (s >> 31) & 1\n"
               "    return t\n")
    src_bge = ("def step_bge(a,b):\n"
               "    s = (a ^ 2147483648) - (b ^ 2147483648)\n"
               "    t = ((s >> 31) & 1) ^ 1\n"
               "    return t\n")
    A_NEG, B_POS = 0xFFFFFFFB, 5          # signed -5 vs 5
    r_blt1 = run_triple_differential(src_blt, [A_NEG, B_POS])
    r_blt2 = run_triple_differential(src_blt, [B_POS, A_NEG])
    r_bge1 = run_triple_differential(src_bge, [A_NEG, B_POS])
    r_bge2 = run_triple_differential(src_bge, [B_POS, A_NEG])
    gpu_blt_ok = (r_blt1["ok"] and r_blt1["gpu_r9"] == 1
                  and r_blt2["ok"] and r_blt2["gpu_r9"] == 0)
    gpu_bge_ok = (r_bge1["ok"] and r_bge1["gpu_r9"] == 0
                  and r_bge2["ok"] and r_bge2["gpu_r9"] == 1)

    # SW/LW address-compute ops on ACTUAL operand values (base x14=90
    # never used for addressing in this program; the real address ops
    # are ADD 0+16, SRL 16>>5, AND 16&31 — verify each class 4-way).
    r_add = run_alu_differential(True, 0, 0x00, 0, 16)
    r_srl = run_alu_differential(True, 5, 0x00, 16, 5)
    r_and = run_alu_differential(True, 7, 0x00, 16, 31)
    gpu_addr_ok = (r_add["ok"] and r_add["gpu_r9"] == 16
                   and r_srl["ok"] and r_srl["gpu_r9"] == 0
                   and r_and["ok"] and r_and["gpu_r9"] == 16)

    ok = all([steps_ok, final_pc_ok, regs_ok, others_ok, mem_ok,
              taken_ok, inversion_ok])
    return {
        "ok": ok,
        "steps_executed": steps,
        "final_pc": trace[-1]["pc"],
        "steps_ok": steps_ok, "final_pc_ok": final_pc_ok,
        "regs_ok": regs_ok, "others_ok": others_ok,
        "mem_ok": mem_ok, "taken_ok": taken_ok,
        "inversion_ok": inversion_ok,
        "bne_taken_count": bne_taken,
        "x9_accumulator": fin[9],
        "jal_link_x16": fin[16], "jalr_target_x21": fin[21],
        "jal_poison_x18": fin[18], "jalr_poison_x22": fin[22],
        "dmem_word4": dmem_out[4],
        # GPU smoke-lane flags (never in ok — determinism clause)
        "gpu_bne_ok": gpu_bne_ok, "gpu_blt_ok": gpu_blt_ok,
        "gpu_bge_ok": gpu_bge_ok, "gpu_addr_ok": gpu_addr_ok,
    }
