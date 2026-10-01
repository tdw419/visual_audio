# RESEARCH — DEFECT-31f: ALU/immediate lowering scratch-lifetime aliasing (measured)

**Date:** 2026-09-26 ~00:4x CDT · **Builder:** af3e62239ce2 (Glyph OS Event Chain cron)
**HEAD at measurement:** 96c97619 (my own BK-29 research commit; tree tracked-CLEAN at tick start)
**Probe:** `.builder_queue/dbg_d31f_alu_imm_alias_af3e.py` (deterministic, no GPU/LLM/network)
**Final run transcript:** `/tmp/d31f_final.txt` (md5 of probe at run time: e3de3ddcd1aecff4a1d6d4ce24a9a099 — note: file was byte-stable across runs 3/4/5; the run-5 edit fixed L01's vacuous golden only)

## Question

BK-28 covered the SB/SH **else branches**, BK-29 the store **fix branches** (value side). Per BK-29's own next-tick line, the next unfixed op-class question is: **do the ALU/immediate lowerings (`andi/ori/xori/slti/sltiu/srli/srai/sub/neg`) have the same fixed-scratch (`r26..r30`) lifetime aliasing when the destination or source register lands in the scratch class?**

## Method

- Hand-encoded RV32I I/R-type words (verified via the transpiler's own `decode_instruction`) — no gcc allocation variance, exact register control.
- `transpile_rv32i_to_glyph` run on BOTH the tree module AND a `git show HEAD:` snapshot; op streams byte-identical per pc in all 12 legs → **latent at HEAD, not a lane regression**.
- Baked via `libc_runtime_kernel_image`, run on `GlyphRunner` (ram_words=16384, max 20000 instructions), result word at mem[768] vs golden.
- All RED legs: `halted=True, faulted=False` — **silent misexecution**.
- Op-stream listings cross-checked instruction-by-instruction (`/tmp/probe_alu_lower2.py` output) — every RED is explained at the lowering level, not just end-to-end.

## Findings (12 legs: 10 RED, 2 PASS)

**Shape 1 — rd==rs1==x29 (the scratch class is x26..x29 under the identity map; r29 is the transpiler's favorite imm temp):**

| Leg | RV32I | Lowering (observed) | mem[768] | Golden | Verdict |
|---|---|---|---|---|---|
| L01 | `andi x29,x29,0xff` (from 0x1234) | `LDI r29 0xff; AND r29 r29` | 0xff | 0x34 | **RED** (stores the imm) |
| L02 | `ori x29,x29,0x34` (from 0x1200) | `LDI r29 0x34; OR r29 r29` | 0x34 | 0x1234 | **RED** |
| L03 | `xori x29,x29,0xff` (from 0x1234) | `LDI r29 0xff; XOR r29 r29` | 0x0 | 0x12cb | **RED** |
| L04 | `sub x29,x28,x29` | `LDI r29 0; ADD r29 r28; SUB r29 r29; …` | 0x0 | 0xc0 | **RED** (rd==rs2 arm self-subtracts) |
| L05 | `neg x29,x29` | `LDI r29 0; SUB r29 r29; …` | 0x0 | 0xffffedcc | **RED** |
| L06 | `srli x29,x29,4` (from 0x1230) | `LDI r29 4; SHR r29 r29` | 0x0 | 0x123 | **RED** (4>>4) |
| L07 | `srai x29,x29,4` (from 0x80001230) | `LDI r29 0x80000000; XOR r29 r29; …` | 0xf8000000 | 0xf8000123 | **RED** (sign-only, mantissa destroyed) |
| L08 | `slti x29,x29,0x10` | `LDI r29 0; ADD r29 r29; SUB r29 r29; …` | 0x0 | 0x1 | **RED** |
| L09 | `sltiu x29,x29,0x10` | mask `LDI r29 0x80000000` precedes `ADD r28 r29` | 0x0 | 0x1 | **RED** — even the "defensive ordering" path is defeated when rs1==x29 |

**Shape 2 — unconditional scratch bleed, NO aliasing required:**

| Leg | RV32I | Mechanism | Verdict |
|---|---|---|---|
| L12 | `sltiu x8,x9,0x10` with live store base x30 | lowering writes r28/r29/r30 unconditionally (`LDI r30 imm` clobbers RV x30 = the base) | **RED, faulted=True** (store faults) |

**Controls (PASS):** `andi x28,x28,0xff` → 0x34 PASS; `sub x28,x9,x28` → 0xc0 PASS (that arm orders `SUB r29 r28` before the r28 write — proof the codebase knows the correct ordering pattern and applies it selectively).

## Mechanism

`tools/rv64i_to_glyph.py` — the `rd == rs1` fast paths of ANDI (:646-647), ORI (:658-659), XORI (:670-671) all emit `LDI r29 <imm>` then operate `r{rd}` (== r29) against itself. SLT/SLTI else-arm (:830-837) consumes rs1 into rd before the SUB/SHR. SUB rd==rs2 arm (:630-634) and the neg path (:620-623) self-subtract r29. SLTIU/SLTU (:852-863) write r28/r29/r30 unconditionally — safe only if the caller keeps live values out of x26..x30 across the instruction, which nothing enforces. The shift paths (:734-766, SRLI/SRAI) put the shamt in r29/r27+28 before the shift reads rd.

DEFECT-31b already fixed the ADDI rd==rs1==x29 case with a PUSH/POP guard — this research shows the same pattern in **eight more lowerings**, plus a shape-2 class (unconditional bleed) that needs no register aliasing at all, just a live x26..x30 value held across the instruction.

## Measured blast-radius context (rule-6 honesty)

- Latent-only at HEAD: the xv6-nano scenario does not currently allocate x26..x29 as these operands into these ops, and all landed gates are GREEN — same latent-vs-regression status as BK-28/29.
- gcc DOES allocate x28/x29 (t3/t4) freely in larger programs (that is exactly how DEFECT-30/31/31b were each found live), so this is a matter of when, not if, a larger C program hits one of these 10 shapes.
- NOT verified: no WGSL twin leg (transpiler-side, nothing spatial); no live xv6-nano repro; fix not implemented (research never lands engine code).

## Candidate (backlog format, filed as BK-30)

**BK-30 — ALU/imm lowering: complete the scratch-class aliasing guards (8 self-alias shapes + unconditional-bleed class).**
Fix shape = the proven DEFECT-31b pattern (guard `rd==rs1==x29` with PUSH/POP around a non-scratch temp) applied to ANDI/ORI/XORI/SUB-rd==rs2/neg/SLTI-else/SRLI/SRAI, plus a bleed-safe SLTIU/SLTU that reads rs1/rs2 into temps BEFORE any scratch LDI (or pushes x26..x30 for the instruction duration).
Gate: `tests/test_defect31f_alu_imm_aliasing.py` — the 10 RED probe programs as fixtures + the 2 controls, RED-first at current HEAD, GREEN after fix; worktree isolation (engine-core transpiler) per AGENTS.md.
Source: `tools/rv64i_to_glyph.py` regions cited above; probe `.builder_queue/dbg_d31f_alu_imm_alias_af3e.py`.

## Rule floors

No rate/latency/cost claims — all numbers are structural asserts (memory words, halted/faulted booleans, opcode listings) from GlyphRunner receipts of real runs this tick. Rule-1 floors treatment does not attach.
