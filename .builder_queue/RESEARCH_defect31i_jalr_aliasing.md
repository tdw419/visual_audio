# RESEARCH_defect31i_jalr_aliasing.md — DEFECT-31i candidate: JALR lowering fixed-scratch aliasing, MEASURED

**Filed:** 2026-09-26 ~01:2x CDT, builder af3e62239ce2 (product lane, Phase-1c research tick)
**Question (new op-class, rule 5 satisfied):** do the branch/compare lowerings — the
remaining unprobed family named by the 31h ledger's next-tick line — carry the same
fixed-scratch lifetime aliasing class as 31c/31e/31f/31g/31h? First member probed:
**JALR**, the computed jump.

## Method

- Probe: `.builder_queue/dbg_d31i_jalr_alias_af3e.py` — reuses the proven d31f
  harness module (import + CASES swap; tree-vs-HEAD transpile compare, gcc rv32i,
  `libc_runtime_kernel_image` bake, GlyphRunner run, `mem[768]` vs golden). No GPU,
  no LLM, no network; fully deterministic.
- Head at probe time: `d6169173` (my 31h ledger commit). Tree transpiler vs
  `git show HEAD:tools/rv64i_to_glyph.py` snapshot: **op streams byte-identical per
  pc in all 4 legs** → latent at HEAD, not a lane regression.
- Determinism: 3 full runs this tick, identical output (2 RED / 2 PASS each time).

## Source mechanism (read at HEAD, tools/rv64i_to_glyph.py:1366-1436)

The dynamic-target JALR lowering writes glyph r30 (== RV x30 under the identity
map) and glyph r29 (== RV x29) as fixed scratch:

```
LDI r30 <tbl_base>          # clobbers RV x30
ADD r30 r{rs1}              # rs1==x30: reads the CLOBBERED x30 -> index = tbl+tbl
[LDI r29 imm; ADD r30 r29]  # imm != 0 only; clobbers RV x29
LDI r29 2; SHR r30 r29
LD  r30 r30
LDI r{rd} <pc+4>            # rd != 0: return address as DATA
CALLR r30                   # rd==x30: the LDI above OVERWROTE the loaded target
```

Byte-level transpile dumps taken this tick confirm both shapes at HEAD:
- `jalr x0,0(x30)` → `LDI r30 0x2000; ADD r30 r30; ...; JMPR r30` (self-alias)
- `jalr x30,0(x5)` → `... LD r30 r30; LDI r30 0x214; CALLR r30` (target clobbered by its own return-address write)

## Measured findings (2 RED of 4 legs, both silent-class disclosed per leg)

| Leg | Program | Result | Verdict |
|---|---|---|---|
| L01 | `jalr x0,0(x30)`, x30=fn | halted=True **faulted=True**, mem=0x0 (golden 0xBEEF) | **RED** — jumps into garbage (tbl+tbl index), faults |
| L02 | `jalr x30,0(x5)`, rd==x30 | halted=True faulted=False, mem=0x0 (golden 0xBEEF) | **RED** — SILENT: CALLR jumps at the return address, never reaches fn |
| C03 | `jalr x0,0(x5)` clean control | mem=0xBEEF | PASS |
| C04 | `jalr x1,0(x5)` plain call control | mem=0xBEEF | PASS |

Notable split: L01 is **loud** (fault) but L02 is **SILENT** — the first
loud-fault RED of the 31-family, and conversely the rd==x30 leg corrupts control
flow without any fault. L02's shape (compiler-plausible: `jalr ra,0(t)` with
gcc allocating ra→x30... note gcc prefers x1 for ra, so L02's exposure is
hand-written asm / alternate allocation; L01's rs1==x30 matches the same
gcc-allocation risk class as BK-31/BK-32).

## Fix shape (proposed, NOT implemented)

Mirror the DEFECT-31/DEFECT-30 PUSH/POP scratch discipline in the JALR dynamic path:
when `rs1==30`, compute the table index in a saved scratch (r28 pattern) instead of
r30; write `rd`'s return address AFTER the `LD r30 r30` only when `rd!=30`, else
stage the return address in r26/r27 and move it after CALLR — or CALLR from a
non-conflicting scratch. Same class as the landed SW fix (zero-risk twin).

## Backlog

Filed as **BK-33** (row 60, systems/GLYPH_BACKLOG.md; number grep-verified free
before filing). Backlog rows are NOT lane-claimable per header rules — BK-33 is
Jericho's to assign.

## Honesty (rule 6)

- All numbers are structural asserts (mem words, halted/faulted booleans,
  op-stream listings) from real GlyphRunner runs this tick — no rates/latencies,
  rule-1 floors do not attach.
- NOT verified: no WGSL twin leg (transpiler-side, nothing spatial); no live
  xv6-nano repro (latent-only — no landed gate performs a computed jump through
  x29/x30; all landed gates stay GREEN, rule 2 not triggered); L02's
  gcc-plausibility is argued, not measured (gcc allocated x1/x5 in every
  observed stream; the defect needs hand-written asm or a different allocator);
  the beq/bne/blt/bge compare lowerings remain UNPROBED (next family member);
  fix proposed in BK-33, not implemented.
- Probe-honesty note: the on-disk probe file is the single source of truth —
  terminal echo of the run showed character-level drift this tick (same
  probe-echo phenomenon the d31e ledger disclosed); the committed file's CASES
  were re-read from disk and verified correct before landing.
