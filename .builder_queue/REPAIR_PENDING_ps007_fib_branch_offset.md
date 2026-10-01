# REPAIR_PENDING_ps007_fib_branch_offset

Filed: 2026-09-19, PS007 step-6 builder run (gate_fibonacci)
Status: **RULED** → `.builder_queue/RULING_ps007_fib_branch_offset.md`
(commit ee2d14fc): OPTION 1 adopted — word 6 = `BNE x5, x0, -20`
(0xFE0296E3). Skeleton pin corrected by the ruling; step 6 un-HOLDed
and landed GREEN the same day (commit history: "PS007 step 6").
Status before ruling: **HOLD on step 6** — this is a **skeleton-sign-off change** (the
pinned program in `tools/pyshader_fde.py` is LOCKED per the brief, so the
fix below is not in the builder's write set). No ruling → step 6 stays
stubbed; the brief cannot reach its definition-of-done until ruled.

## Measured conflict

The locked Fibonacci program's branch immediate cannot reach the loop
head that the SAME brief's hand-computed pin requires. Two locked facts
contradict each other:

1. `tools/pyshader_fde.py:62` pins word 6 as `BNE x5, x0, -8` with the
   comment "goto 2 (offset -2 insns)".
2. The brief (.builder_queue/brief_ps007_fde_composition.md:34-38) pins
   the hand-computed result: 5 instructions per iteration × 8
   iterations = 42 total, x3 sequence 2,3,5,8,13,21,34,55, final
   x1=34, x2=55, x3=55, x5=0. That behavior requires the branch to
   re-execute insn 2 (the ADD) every iteration, i.e. target pc=2.

Reproduction (probe: `.builder_queue/probe_ps007_fib_encoding.py`,
this revision): the seven words decode cleanly via PS005 `decode_ref`
(word 6 → fmt=B, funct3=1, rs1=5, rs2=0, imm=-8), but `run_fde(imem,
x5=8, 42 steps)` faults at step 22 with
`IndexError: fetch: pc 7 out of bounds (imem len 7)` — with imm=-8 the
branch at pc=6 targets pc = 6+1+(-8//4) = **5**, so the "loop" is the
spin `5: x5--; 6: BNE x5,x0 → 5`, which falls through at pc=7 after 21
steps with x1=1, x2=1, x3=2 — not the pin. Note the two locked docs
already disagree with each other: the brief writes `BNE x5,x0,-2`
(insn units?) while the skeleton writes `-8` (bytes); under the
execute_one convention (pc+1+imm//4, brief step-3 clause) NEITHER
encoding reaches pc=2.

The hand-computed pin itself is verified correct Fibonacci (F9=34,
F10=55, 2+5·8=42 instructions) — the defect is confined to the word-6
immediate.

## Options (cheapest first)

1. **Fix the immediate: word 6 = `BNE x5, x0, -20`** (offset −5 insns;
   encoded word 0xFE0296E3 — VERIFIED on this revision: decode_ref
   returns fmt=B/imm=-20, and the 7-word program with this word run
   through run_fde(42) reproduces the hand-computed pin EXACTLY:
   final x1=34, x2=55, x3=55, x5=0; x3 sequence
   2,3,5,8,13,21,34,55 at pc=3; no bounds fault). One constant in `tools/pyshader_fde.py` + the line-62
   comment; brief line 33's `-2` becomes `-5` (or −20 bytes). No
   interface, state-shape, or convention change; execute_one's
   pc+1+imm//4 rule (gated GREEN at step 3) stays as-is. **Recommended.**
2. Keep imm=-8 and re-pin the brief to the spin-loop semantics (21
   steps, x3=2 once). Rejected as first choice: abandons the actual
   Fibonacci workload the roadmap gate names (GPU_CPU_EMULATOR_ROADMAP.md:140)
   and makes the x3-sequence trace clause meaningless.
3. Re-layout the program so the loop head lands at pc 5 (move ADD to
   5, reorder). Larger diff to a locked program, re-derives the pin,
   no upside over option 1.

Holding on: step 6 (gate_fibonacci). Nothing else in the brief remains
eligible. Decision requested as `RULING_ps007_fib_branch_offset.md`.
