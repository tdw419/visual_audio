# RESEARCH — DEFECT-31j: branch/compare lowering aliasing + unsigned-compare signedness

**Builder:** af3e62239ce2 (GLM cron, Glyph OS lane)
**Date:** 2026-09-26 (~01:4x-02:0x CDT)
**HEAD at measurement:** 24006234 (my BK-33 research lineage; tracked tree CLEAN throughout)
**Question class:** NEW op-class per the 31i ledger next-tick line — the branch/compare family (beq/bne/blt/bge/bltu/bgeu), the family BK-33 explicitly named UNPROBED.

## Question

Do the branch/compare lowerings (a) alias fixed scratch r28/r29/r30 when an
OPERAND (rs1/rs2) lives in the scratch class, and (b) lower unsigned compares
with correct unsigned semantics?

## Method

- Source read first: tools/rv64i_to_glyph.py:1217-1341 (BEQ/BNE zero-scratch
  paths use r28 as the zero temp; BLT/BLTU at :1297 and BGE/BGEU at :1322
  share the signed (rs1-rs2)>>31 sign-bit lowering under DEFECT-16
  PUSH/POP guards that protect x28/x29/x30 only ACROSS the lowering).
- Harness: reuses the proven dbg_d31f module verbatim (build_elf via
  riscv64-unknown-elf-gcc -march=rv32i, tree-vs-HEAD transpile op-stream
  compare per pc, libc_runtime_kernel_image bake, GlyphRunner, mem[768]
  vs golden). Only CASES swapped. Probes:
  `.builder_queue/dbg_d31j_branch_compare_alias_af3e.py` (10 legs),
  `.builder_queue/dbg_d31j3_bltu_discriminating_af3e.py` (3 corrected S1
  legs), `.builder_queue/dbg_d31j4_bne_label_check_af3e.py` (label-uniqueness
  probe), `.builder_queue/dbg_d31j2_bltu_bitexact_af3e.py` (op-stream dump).
- Every leg: tree == HEAD lowering byte-identical per pc (latent, not a
  lane regression). Determinism: 3 full runs of each probe, identical
  results (exit codes 1 / 1 / 1 across runs; same legs RED each time).

## Findings (measured)

S1 — UNSIGNED COMPARES LOWER AS SIGNED (tools/rv64i_to_glyph.py:1297,1322):
  BLTU shares BLT's lowering, BGEU shares BGE's: r30 = rs1-rs2, SHR 31,
  branch on the sign bit. That is the SIGNED test. Corrected discriminating
  legs (operands straddling the signed/unsigned divergence, {1, 0xFFFFFFFF},
  materialized via addi -1 to avoid LUI dependence):
  - bltu 1, 0xFFFFFFFF -> branch NOT taken, mem[768]=0x0 (golden 0x1) RED
  - bgeu 0xFFFFFFFF, 1 -> NOT taken, mem[768]=0x0 (golden 0x1) RED
  - control bltu 1, 2 (signed==unsigned region) PASS
  This is a REAL divergence class: any unsigned comparison where one
  operand has the sign bit set (raw byte values >= 128 compared unsigned,
  hash comparisons, u32 wraparound checks) misdirects SILENTLY.
  HONESTY NOTE: my FIRST two S1 legs ({1, 0x80000000}) were
  NON-DISCRIMINATING — the signed difference 1-0x80000000 = 0x80000001 is
  negative, so the flawed lowering happens to match unsigned semantics
  there. They passed and are reported as PASS with the coincidence
  explained. The corrected legs above are the discriminating pair.

S2 — BLT/BGE CONSUME OPERANDS AS SCRATCH DURING THE COMPARE
  (:1303-1315, :1328-1341): the DEFECT-16 PUSH/POP guards protect x28/x29/x30
  across the lowering, but the compare itself does `LDI r30 0; ADD r30
  r{rs1}; SUB r30 r{rs2}` — if rs1 or rs2 IS x28/x29/x30 the compare reads
  the clobbered/zeroed register:
  - blt x30(2), x9(1) -> mem[768]=0x1 (golden 0x0) RED — trace: step 318
    `LDI r30 0` overwrites x30=2, SUB r30 r9 = 0-1 = 0xFFFFFFFF, sign 1,
    branch wrongly taken (silent).
  - bge x30(2), x9(1) -> mem[768]=0x0 (golden 0x1) RED (same mechanism,
    silent).
  - blt x9(1), x29(2) -> PASS at this exact operand pair, but by
    coincidence: `ADD r30 r9; SUB r30 r29` reads x29 AFTER `LDI r29 31`?
    NO — the lowering order is ADD/SUB before LDI r29, so rs2==x29 reads
    the PREVIOUS r29 value; leg measured 0x1 = golden. Directional only
    (see below).
S3 — BEQ/BNE ZERO-SCRATCH SELF-COMPARE (:1231-1241, :1260-1271): the
  rs1==0/rs2==0 paths materialize 0 in r28 then `CMP r28 r{other}` — when
  the OTHER operand is also x28 this is CMP r28 r28, always-equal:
  - beq x0, x28(5) -> mem[768]=0x1 (golden 0x0) RED — branch always taken
  - bne x28(5), x0 -> mem[768]=0x0 (golden 0x1) RED — branch never taken
  - control beq x9(0), x0 (x28 not an operand) PASS
  Silent (halted=True faulted=False) everywhere; no gate is known to
  compare against x0 while holding a live value in x28 (latent-only).

Controls (all PASS): blt x9,x10 clean regs; bltu small-vs-small; beq
zero-scratch path with clean operand. Full label-uniqueness probe: the
bne_counter (declared :490, used :1253) generates unique __skip_bne_N
labels per program — RULED OUT as a defect (each label appears exactly
twice: JZ reference + definition).

## Non-discriminating-leg audit (rule-1 discipline)

One leg pair (S1 originals) initially reported as RED-class candidates was
shown non-discriminating by arithmetic on the op stream and re-classified
PASS-with-explanation. The corrected legs are falsifiable in the other
direction: on a fixed lowering (true unsigned compare) they go GREEN, and
the S1-original legs would stay GREEN (no regression) — the pair together
is the discriminator. L04 (blt rs2==x29) is directional, not load-bearing:
its PASS is explainable by lowering order, and it is excluded from the
filing's evidence set.

## Candidate backlog item (BK-34, NOT claimable without Jericho)

**BLTU/BGEU signed lowering + branch operand-scratch aliasing guards.**
Two independent fixes, ordered cheapest-first:
1. (cheapest) Route BLTU/BGEU through a true unsigned test: after
   computing r30 = rs1-rs2, sign-extend BOTH operands (SHL 31 / SHR 31)
   and compare THOSE signs, or compute (rs1 ^ 0x80000000) - (rs2 ^
   0x80000000) before the SHR 31 — same instruction budget, no new
   scratch. Gate: the d31j3 leg pair as fixtures, RED-first at current
   HEAD, GREEN after fix.
2. DEFECT-16 extension: PUSH/POP any of r28/r29/r30 that appears as an
   OPERAND (rs1/rs2) around the compare body, restoring before the JZ
   (the CMP flag in r0 survives the pops — proven pattern from the landed
   DEFECT-16 fix). Same for BEQ/BNE zero-scratch paths when the other
   operand is x28 (compare against r0-less zero: LDI a DIFFERENT scratch,
   or reorder). Gate: L03/L05/L06/L07 as fixtures, RED-first + non-vacuity
   leg (neuter guard -> RED).
Prereqs: worktree isolation (engine-core transpiler) per AGENTS.md.
Source: tools/rv64i_to_glyph.py:1217-1341.

## What this receipt does NOT claim

- No engine code touched (research-only; BK-34 is Jericho-gated per the
  backlog header rules).
- L04 not load-bearing (directional PASS, mechanism not fully attributed).
- The 2^31-coincidence analysis is arithmetic on measured op streams, not
  an independent simulator run; the discriminating legs are the evidence.
- No VCC/substrate probe run this tick (no writes to the substrate).
