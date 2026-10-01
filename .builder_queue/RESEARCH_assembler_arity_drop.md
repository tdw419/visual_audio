# RESEARCH — assembler operand arity: extra operands silently dropped (BK-37 candidate)

**Date:** 2026-09-27 ~00:5x CDT · **Builder:** af3e62239ce2 (Glyph GPU OS product lane)
**Tick type:** PHASE 1c research (queue empty: QUEUE_STATE.json all 22 items landed,
mailbox clean — no RULING_* newer than HEAD 10233635, monitor queue=0, stall_tier=0)
**Question:** the BK-36 research tick folded in a candidate ("assembler silently
drops extra operands on 3-operand ADD/MUL, glyph_isa_v2.py:436-438") with no
measurements. Is that real, what is its blast radius, and is the error contract
loud everywhere else?

## Method

New probe `.builder_queue/probe_arity_af3e.py` (untracked, landed modules only:
imports `GlyphAssemblerV2`/`OpcodeMapV2` from `tools/glyph_isa_v2.py`, assembles
one-line programs, dumps the rs1/rs2/rd + immediate word pixels). Deterministic:
two consecutive runs byte-identical (`diff` clean).

## Findings (measured at HEAD 10233635, probe exit 0)

| source line | result |
|---|---|
| `ADD r1 r2 r3` | **assembles OK**, rd=1, rs2=2 — `r3` silently dropped |
| `ADD r1 r2 bogus` | **assembles OK**, same encoding — even a non-register token is dropped |
| `LDI r1 5 r3` | **assembles OK** — extra operand dropped |
| `SUB r4 r5` | control, assembles OK |
| `MOV r1 r2` | raises `KeyError: 'MOV'` (loud, but the message leaks the raw dict error — already ticketed as BK-17 L3) |

Root cause (read, tools/glyph_isa_v2.py): the per-opcode branches read operands
positionally and never check `len(args)` — `ADD`-class at :437-439 reads
`args[0]`, `args[1]` and ignores the rest; `LDI` at :430-435 reads `args[0]`,
`args[1]`; the only arity-sensitive opcode in the whole dispatch is SYSCALL
(`len(args) > 1`, :458). The pre-loop label/bounds validation (:386-409) checks
labels and jump-target bounds but not operand counts.

Why this is a correctness hazard, not a lint: the Glyph ISA is 2-operand
(`ADD rd rs` = `rd += rs`). A programmer coming from RISC-V/MIPS writes
`ADD r1 r2 r3` meaning `r1 = r2 + r3`; the assembler encodes `r1 += r2`
**and discards r3 with no diagnostic**. The program then runs to clean HALT
with wrong data — the same silent-wrong-answer class as the DEFECT-31 family
(lowering-side), but at the hand-written-assembly surface, and invisible to
every runtime gate because assembly succeeds.

Blast radius: every hand-written `.glyph` source (the R2.2 stranger path,
`tools/glyph_run.py`, docs/START_HERE.md flow) and every LLM-authored assembly
in the agent fleet — exactly the population that writes 3-operand arithmetic
by reflex. WGSL twin unaffected at this layer (shader is generated from
`OpcodeMapV2`, `tools/glyph_gpt/runner.py:150` — the defect is upstream in the
shared assembler), so a parity gate would NOT catch it; it needs its own
assemble-time leg.

## Candidate backlog item (BK-37) — backlog format

- **Title:** Assembler arity guard: extra/missing operands on every opcode →
  loud assemble-time error (`ValueError: ADD expects 2 register operands, got 3
  ('r3')`), never silent drop. Plus, folded (same dispatch loop, same fix
  shape): register-token validation (`ADD r1 r2 bogus` currently encodes with
  the same image as well-formed source).
- **Gate:** `tests/test_bk37_assembler_arity.py` —
  L1: `ADD r1 r2 r3` → assemble raises ValueError naming opcode AND the extra
  token (RED today: assembles clean);
  L2: `ADD r1 r2 bogus` → ValueError (RED today);
  L3: `LDI r1 5 r3` → ValueError (RED today);
  L4: missing-operand `ADD r1` → ValueError (RED today: IndexError leak);
  L5: non-vacuity — arity check neutered → L1 fires;
  L6: family — full assemble/glyph_run/transpiler gates stay green (no
  landed fixture may rely on the silent drop; verify by suite, disclose any).
- **Prereqs:** none — assembler-level, no engine/CPU/WGSL surface change.
- **Source:** this receipt + probe; folded from RESEARCH_move_damage_blackout.md.

## Rule-1 statement

No rate/latency/cost numbers anywhere in this receipt — all quantities are
structural (opcode branch shape, exit codes, encoding tuples from one probe
process, deterministic across 2 runs). Floors/check_regime N/A (rule 1 not
triggered).

## What this does NOT prove

- That no landed fixture assembles a >2-operand line on purpose (L6 checks at
  landing time; not probed in this research tick).
- WGSL-side behavior of malformed sources (out of scope — defect is upstream
  of twin generation).
- That KeyError-leak error-quality for unknown mnemonics (BK-17 L3) and arity
  are the same fix — related loop, separate legs, filed folded but separable.
