# RECEIPT — R5.3 day-1 defect: rustc auipc+jalr / sp-relative mangling FIXED

Ticket: .builder_queue/TICKET_R53_day1_transpiler_auipc_jalr.json
(landed 62ec0c1c, corrected 5a9c608d by the seat lane; last link handed
to this lane). Builder: cron af3e62239ce2, 2026-09-22 ~09:0x CDT.
Branch: glyph-transpiler-autoloop. No rate claims → floors/check_regime N/A.

## Verdict

**RESOLVED — gate GREEN.** Rust recursive fib(15) via tools/glyph_cc.py:
HALT, a0=610, artifact round-trip MATCH (93760 steps). C lane unchanged
and still green (fn-ptr 36, recursion 610, add8 36). 65 transpiler-family
tests pass, including the 57 pre-existing ones plus 2 new gate legs.

## What the fix actually was (measured, and DIFFERENT from the ticket's
## best attribution)

The ticket's probing_result_20260922 split the fault into
"necessary: unseeded pointer table" + "insufficient: second fault, label
lands mid-BLT / POP on unbalanced stack". The second half was a
MISATTRIBUTION. There was no label-placement defect; assemble_glyph_to_pixels
label coordinates are correct (verified by direct trace).

The real second defect: **the glyph JALR lowering dropped the instruction's
immediate** (tools/rv64i_to_glyph.py, OP_JALR branch, ~:1238).

- rustc's call idiom is `auipc ra,0x0` + `jalr -N(ra)`: target = ra + imm.
- Old lowering: `LDI r30 TBL; ADD r30 r1; SHR r30 r29; LD r30 r30` —
  indexes the pointer table at **ra alone**.
- Measured consequence (probe_trace2.py, fib(15) repro): the call site
  `:pc_0x4` holds ra=0x4 after auipc, so the executor reads
  table[wi(0x4)] = packed 0x3 = the entry for `:pc_4` — the auipc's OWN
  address — instead of the call target `:pc_0x6c`. Jump back to auipc →
  call again → infinite spin at the same site (8 instrs/iteration, ~56K
  steps per fib call); the call-stack pointer r31 then walks into the
  auto stack band and the return path CALLRs with garbage — exactly the
  "POP faults on unbalanced stack / r30 huge" the seat lane saw and
  read as a label-placement bug. The seat lane's probe read
  memory[0x81b] (the CORRECT entry for 0x6c) directly and concluded
  coordinates were consistent — but the executing code reads
  memory[0x801] (indexed by ra=4), so the observation never tested the
  defect path.
- Why the C lane was immune: gcc rv32i emits `jal ra,sym` (direct, →
  glyph CALL) and `jalr ra,0(a5)` (imm=0) for fn pointers. With imm==0
  the broken lowering accidentally computes the right table index.
  The whole C/Rust asymmetry is the immediate.

## Three-part fix (one commit)

1. **tools/rv64i_to_glyph.py (JALR lowering)**: fold the immediate into
   the table index — `r30 = TBL + rs1 (+ imm); SHR; LD`. imm==0 emits
   byte-identical glyph text as before (all existing fixtures untouched;
   65 tests green prove it). Honesty note in code: RISC-V clears target
   bit 0; no glyph AND-imm exists and no rv32 toolchain emits odd text
   targets, so the ~1 mask is not applied.
2. **tools/glyph_cc.py (runner path)**: seed the pointer table via
   build_pointer_table(text, vaddr, meta) before executing — the
   ticket's "necessary" half, confirmed necessary (go5_shell.py:25
   pattern). Also seed the table in the ROUND-TRIP artifact-replay leg:
   without it, any program that reaches the table re-runs with word 0
   (packed 0 → glyph PC (0,0)) and the round-trip lies (measured:
   MISMATCH a0=0 pre-fix of the leg). The replay leg re-derives the
   label→coord map from the glyph text, not a second transpile.
3. **tools/glyph_cc.py (_RUST_WRAP)**: adopted the seat lane's uncommitted
   `#[naked]` _start (quiet on the tree since 08:02; disclosed per the
   R1.2/R1.4 in-flight precedent). Measured alone it was INSUFFICIENT
   (NO HALT — table never seeded), which is consistent: it fixes the
   sp=0 prologue-store fault (rustc emits `addi sp,sp,-16` before any
   inline asm; plain `asm!("li sp")` lands after the prologue; `#[naked]`
   + naked_asm!("lui sp,0x4"; call main; ecall) sets sp before any
   store), but the JALR defect needed part 1.

## Evidence (tails pasted; full runs on this machine)

RED (pre-fix, HEAD 5a9c608d + seat's naked diff):
```
result   : FAULT            # HEAD, no sp fix
result   : NO HALT (budget exhausted)   # naked diff alone (sp fixed, JALR still broken)
roundtrip: MISMATCH (a0=0)  # after JALR fix, before round-trip table seeding
```
RED (rule-4 gate discrimination — rv64i_to_glyph.py fix stashed):
```
FAILED tests/test_glyph_cc.py::test_rust_recursive_stack_program
1 failed in 0.35s
```
GREEN (full fix):
```
chain    : rust -> rustc riscv32im-unknown-none-elf -> rv32im link -> transpiler
result   : HALT
a0       : 610
steps    : 93760
roundtrip: MATCH (a0=610)
```
C-lane regression (ticket gate): fn-ptr indirect a0=36 HALT; C recursion
fib(15) a0=610 HALT (roundtrip MATCH); add8 direct a0=36 HALT.
Transpiler family: 65 passed (rv64i_to_glyph* suites incl. bytemem,
switch, xv6_nano, printf, sltiu_auipc + gh15_ir + assembler labels +
glyph_cc). glyph_cc gate: 9 passed (7 existing + 2 new).

## New gate legs (tests/test_glyph_cc.py)

- test_rust_recursive_stack_program — THE ticket gate: rust recursive
  fib(15) → halted, a0=610, roundtrip MATCH. Shown RED above.
- test_c_fn_pointer_indirect_call — pins the C fn-pointer path so the
  C/Rust asymmetry can never silently return.

## What this PASS does NOT prove

- CPU oracle only (GlyphCPUv2): no WGSL/shader-path parity claim.
- The ~1 target-bit mask is not applied (no glyph AND-imm op; no rv32
  toolchain in use emits odd text targets — stated assumption, not gated).
- rustc is version-pinned only by this machine (naked_asm needs ≥1.82);
  no cross-toolchain-version claim.
- Steps count (93760) is the glyph-machine execution length for fib(15);
  no performance comparison is made (floors N/A).
- Artifact-only replay now needs the glyph SOURCE text alongside the
  artifact to rebuild the pointer table (documented in-code); a pure
  "artifact with zero side files" claim is NOT made for indirect-call
  programs.
