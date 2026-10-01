# DEFECT-30: OP_LBU/LHU lowering — scratch-register aliasing + stack leak when rd ∈ {r28, r29}

Filed: 2026-09-25 ~07:4x CDT, builder cron af3e62239ce2
Status: OPEN — root cause measured, fix requires worktree-isolated transpiler session
Discovered by: CLAIM QUEUE item 19 (coreutils volume port #2), gate `tests/test_coreutils_volume2.py` RED (4/5 tools fail)

## One-line defect

In `tools/rv64i_to_glyph.py` OP_LBU lowering (line ~921) and OP_LHU
lowering (line ~1021, same shape), the DEFECT-16c PUSH/POP scratch
guard pushes r28/r29/r30 but pops only `[r for r in (28,29,30) if r !=
rd]` — and when `rd` aliases the lane scratch (r28) or mask scratch
(r29), the lowered sequence is BOTH value-corrupted AND leaks one word
of the engine's r31 stack per executed LBU.

## Mechanism (measured)

Lowered shape (transpiler, `rv64i_to_glyph.py:937-956`):

```
_push = (28, 29, 30)              # ALL THREE pushed, unconditionally
_pop  = [r for r in (28,29,30) if r != rd]   # rd excluded from pops
PUSH r28; PUSH r29; PUSH r30
LDI r30 <imm>; ADD r30 r{rs1}     ; addr
LDI r28 3; AND r28 r30            ; lane
LDI r29 3; SHL r28 r29            ; shift = lane*8
LDI r29 2; SHR r30 r29            ; word addr
LD  r{rd} r30                     ; rd = word      ← rd live from here
SHR r{rd} r28
LDI r29 0xff                      ; MASK scratch ← aliases rd when rd==r29
AND r{rd} r29
POP r30; POP r{28 or nothing}; ...            ; 2 pops for 3 pushes
```

Two failure modes, both measured:

1. **Stack leak (rd ∈ {28,29}):** 3 PUSH, 2 POP → engine sp (r31) −1
   word per LBU execution, forever.
2. **Value corruption (rd == r29):** `LDI r29 0xff` (intended as the
   mask in scratch) overwrites rd's freshly extracted byte; the
   following `AND r29 r29` yields 0xff unconditionally — every byte
   "extracted" through this shape reads as 0xff.
   (rd == r28 similarly trashes the lane/shift scratch mid-sequence.
   rd == r30 is the ONLY in-scratch dest that works: the address reg's
   live range ends before the LD, pops balance, value correct.)

## Isolated repro

`.builder_queue/dbg_vol2_lbu_iso.py` — a 2-instruction RV32I program
(`lbu t4, 0(a0); lbu t4, 1(a0)`), transpiled with the repo transpiler:

```
PUSH: 6  POP: 4  -> leak per lbu(t4): 2   (one per LBU, 2 LBUs)
... LD r29 r30 ... LDI r29 0xff ... AND r29 r29 ...   ; value = 0xff always
```

## Live consequences (item 19 gate, `tests/test_coreutils_volume2.py`)

Measured with `.builder_queue/dbg_vol2_*.py` probes on the current
tree (HEAD 6c405773):

- **cut field2**: infinite loop — the field-scan loop's `lbu`
  destination is a scratch-aliased reg; every extracted byte reads
  0xff, never equals `:` (0x3a) or `\n` (0xa), loop never exits.
  Engine sp observed 0x51f→0x51a over 5 iterations (−1/iter, the
  leak); 9354 loop arrivals in 300k steps; receipt `halted: False`.
- **tr / sort**: same defect, different stack layouts — sp leak walks
  into unrelated words → fault 0xed8 (tr) / 0x2c00 with wild cursor
  write 0x7008600 (sort).
- **grep**: byte-compare loop misreads bytes (match predicate always
  true-ish) → flushed stream contains non-matching lines shifted by a
  byte (`'pple pie\nbanana bread\napple tart'` where the POSIX
  reference is `'apple pie\napple tart\n'`).
- **tee**: PASSES (3/3 fixtures) — gcc allocated its byte loads to
  non-scratch registers; no aliasing, no leak. The two green legs
  (tee + L0 table) confirm the harness itself is sound.

## Fix shape (NOT landed — engine-core file, worktree isolation per AGENTS.md)

1. Stack: push only what will be popped (`_push = [r for r in
   (28,29,30) if r != rd]`), keeping the sequence's internal use of
   the pushed set intact.
2. Values: the mask (and lane) scratch must never alias rd after `LD
   rd` — pick the mask register dynamically (e.g. fall back to
   pushed/popped r26) or reorder so the mask lives in a register
   outside rd's live range. Same treatment for OP_LHU (line ~1021,
   identical `_pop` pattern).
3. Gates that must stay green after the fix: `tests/test_gh23_libc_runtime.py`
   (5), `tests/test_bk11_coreutils.py` (6), `tests/test_coreutils_volume2.py`
   (7, this defect's own gate), plus the bk25/l1/bk22 family (79/79 at
   last landing). RED-first evidence for the fix: the isolated repro
   above goes from `PUSH:6 POP:4` + always-0xff to `PUSH:4 POP:4` +
   correct bytes.

## What this ticket does NOT claim

- Not verified on the WGSL twin (no spatial leg in the failing path).
- Not a claim that gcc -ffixed-x31 is involved — the dirty-tree flag
  is orthogonal (engine stack is r31; the flag prevents RV allocation
  of x31; the defect fires regardless).
- The exact register-allocator trigger shapes (which C patterns put
  byte dests in t3/t4) are characterized only by the vol2 fixtures and
  the isolated repro, not exhaustively.
