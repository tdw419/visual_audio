# RESEARCH_defect31m_shift_reg_aliasing.md — DEFECT-31m candidate: REGISTER-register shift lowerings (SLL/SRA) aliasing, MEASURED

**Filed:** 2026-10-01 ~11:4x CDT, builder af3e62239ce2 (product lane, Phase-1c research tick)
**Head at probe time:** `fb06b690` (== monitor fingerprint CLEAN; picked after mailbox-rule check — newest RULING mtime 09-29 09:08 < HEAD 11:23, ledger STATUS ACTIVE, CLAIM QUEUE empty)
**Question (new op-family members, rule 5 satisfied):** the 31-family probed SB/SH (31c), the store fix branches (31e), ALU/immediates incl. SRLI/SRAI (31f), LW (31g), SW value-side (31h), JALR (31i), branch/compare (31j), ECALL rewrite (31k). The REGISTER-register shift lowerings — SLL and SRA — were never probed. SRL stages its count through PUSH/POP'd r26 (the DEFECT-30 fix) and is expected safe; SLL uses NO scratch and SRA's DEFECT-30 guard covers r26 only.

## Method

- Probe: `.builder_queue/dbg_d31m_shift_reg_alias_af3e.py` — reuses the proven d31f
  harness module (import + CASES swap; gcc rv32i `-march=rv32i -mabi=ilp32`,
  tree-vs-HEAD transpile compare, `libc_runtime_kernel_image` bake, GlyphRunner
  run, `mem[768]` vs golden). No GPU, no LLM, no network; fully deterministic.
- Tree transpiler vs `git show HEAD:tools/rv64i_to_glyph.py` snapshot:
  **op streams byte-identical per pc in all 6 legs** → latent at HEAD, not a
  lane regression.
- Determinism: 3 full runs this tick, stdout md5 identical all three
  (`c8331ba8b69635e112129b5330a0a884`).
- One-command re-derivation: `python3 .builder_queue/dbg_d31m_shift_reg_alias_af3e.py` (exit 1 = RED present).

## Source mechanism (read at HEAD, tools/rv64i_to_glyph.py)

SLL (:769-776):

```
if rd == rs1: SHL r{rd} r{rs2}      # safe: no scratch
else:
  LDI r{rd} 0                       # zeroes rd BEFORE the count is read
  ADD r{rd} r{rs1}
  SHL r{rd} r{rs2}                  # rs2==rd: reads the DESTROYED count
```

SRA (:779-813; DEFECT-30 PUSH/POP covers r26 = the count scratch only):

```
PUSH r26; LDI r26 31; AND r26 r{rs2}    # count staged — safe
[LDI r{rd} 0; ADD r{rd} r{rs1}]
LDI r29 0x80000000; XOR r{rd} r29       # rd==x29: XOR r29 r29 -> 0
SHR r{rd} r26
LDI r27 0x80000000; SHR r27 r26         # r27 = sign fill
SUB r{rd} r27                           # rd==x27: SUB r27 r27 -> 0
POP r26
```

## Measured findings (3 RED of 6 legs, all SILENT: halted=True faulted=False)

| Leg | Program | Result | Verdict |
|---|---|---|---|
| L01 | `sll x9,x19,x9` (count in rd) | mem[768]=0x1579a000 (golden 0xabcd000) | **RED** — `LDI r9 0` destroyed the count 12; SHL read rd=0xABCD, glyph SHL masks &31 → shifted by 13 |
| L02 | `sra x29,x29,x8` (rd==x29 sign scratch) | 0xff800000 (golden 0xff876540) | **RED** — XOR self-zeroed rd; result = 0 − (0x80000000>>8) |
| L03 | `sra x27,x27,x8` (rd==x27 fill scratch) | 0x0 (golden 0xfff87654) | **RED** — SUB r27 r27 = 0 |
| L04 | ctrl `sll x9,x19,x8` clean | 0xabcd00 == golden | PASS |
| L05 | ctrl `sra x9,x19,x8` rd clean | 0xff876540 == golden | PASS |
| L06 | ctrl `srl x9,x19,x8` staged-r26 DEFECT-30 path | 0xabc == golden | PASS |

Notable: L01's corruption is WORSE than shift-by-0 — the destroyed count register
feeds glyph SHL's &31 mask, so the shift lands on an adjacent count (12→13 here,
value-dependent). L02/L03 are pure zeroing. All three shapes are silent
(halted=True faulted=False): no fault, no visible trace, wrong data only.

## Fix shape (proposed, NOT implemented)

Same discipline the sibling lowerings already apply:
- **SLL**: stage the count in a PUSH/POP'd scratch (the DEFECT-30 pattern used
  by SRL/SRA) before the rd-zeroing LDI when `rs2 == rd` — or reorder to read
  rs2 into the scratch first.
- **SRA**: take the sign-extend (r29) and fill (r27) scratch from a saved set
  that EXCLUDES rd — exactly the `scratch = [r for r in (28,29,30) if r != rd]`
  discipline the LBU (:984) and LHU (:1126) lowerings landed with.

## Backlog

Filed as **BK-79** (systems/GLYPH_BACKLOG.md, row appended after BK-78;
grep-verified free before filing). Backlog rows are NOT lane-claimable per
header rules — BK-79 is Jericho's to assign.

## Honesty (rule 6)

- All numbers are structural asserts (mem words, halted/faulted booleans,
  op-stream identity) from real GlyphRunner runs this tick — no rates/latencies,
  rule-1 floors do not attach.
- NOT verified: no WGSL twin leg (transpiler-side, nothing spatial); no live
  xv6-nano repro (latent-only — no landed gate allocates a register-shift count
  or dest in these collision classes; all landed gates stay GREEN, rule 2 not
  triggered); gcc-allocation plausibility for the collision shapes is argued
  from the family precedent (gcc freely uses x9/x27/x29 as call-clobbered/
  callee-saved temps), not measured — the defects are reachable from hand-written
  asm regardless; fix proposed in BK-79, not implemented.
- Rule-5 check performed this tick: no existing RESEARCH_*.md or backlog row
  covers register-register SLL/SRA (BK-30 covers the SRLI/SRAI IMMEDIATE arms
  only — different lowerings at :734-766 vs :769-813).
- Probe-honesty note: results quoted from the probe file's own stdout captured
  via md5-pinned re-runs (3× identical), per the d31e/d31i probe-echo lesson.
