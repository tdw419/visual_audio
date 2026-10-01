# RESEARCH — DEFECT-31c latent aliasing measured: 5 new RED classes in the
# landed SB/SH lowerings (builder af3e62239ce2, 2026-09-26 ~0:0x CDT)

## Question

The DEFECT-31c receipt (RECEIPT_DEFECT31c_sb_sh_r30_alias.md) flagged two
latent aliasing classes as "unfixed, unmeasured — no gate scenario hits
them": rs1==x29 second-address re-read, and rs2==x27 value-read. Do they
actually fault, and is the class bigger than the receipt guessed?

## Method

- Transpile minimal RV32I programs (riscv64-unknown-elf-gcc -march=rv32i,
  -Ttext=0x200) through BOTH the tree transpiler AND HEAD's
  (git show HEAD:tools/rv64i_to_glyph.py loaded as a standalone module);
  diff the glyph op stream per pc (they are IDENTICAL for every case —
  the defect is in the landed lowering, not a regression).
- Bake each program via libc_runtime_kernel_image, run on GlyphRunner,
  compare stored mem[768] against the golden byte/half.
- Probe: .builder_queue/dbg_d31c_latent_alias_af3e.py (re-runnable,
  deterministic, no LLM/GPU). Op-stream dump:
  .builder_queue/dbg_d31c_dump_sb_x29_af3e.py.

## Findings (measured, all real runs this tick)

1. **rs1==x29 base — RED, both SB and SH.** `sb t1,0(t4)`/`sh t1,0(t4)`
   with base t4=x29 stores NOTHING (mem[768]=0x0). Root cause is in the
   op stream (dump, pc_0000020c): the else-branch recomputes the address
   a second time AFTER `LDI r29 3` has already overwritten r29:
   `ADD r30 r29` (2nd) reads the shift constant 3, not the base. The
   store lands at word 0 — invisible, silent, wrong.
2. **rs2==x27 value — RED, worse than the receipt guessed.**
   `sb x27,0(s1)` stores 0xff (lane OR'd with a stale all-ones word, the
   value read happens after r27 became the 0xff mask via
   `LDI r27 0xff; SHL r27 r28`), and `sh x27,0(s1)` stores 0xffff.
   The value's lane bits are already set in the current word, so the
   clear-then-insert dance inserts the MASK, not the value.
3. **rs2==x26 value — RED.** Stores 0x0: the `LDI r26 0` init clobbers
   the value register before `ADD r26 r6`... reads it (actually the ADD
   reads r26=0 — the init IS the clobber).
4. **Control (base s1, value t1) — PASS**, and tree==HEAD lowering
   identical in all 6 cases: this is a LATENT class, present at HEAD,
   not introduced by any lane tick.
5. **Why no landed gate ever hit it:** gcc never allocates x26/x27 for C
   temps (unnamed in RV32I ABI usage in these fixtures), and no xv6-nano
   scenario uses t4 as an SB/SH base. The class is real but only
   reachable from hand-written asm or different register allocation.

## Summary

| case | lowering tree==HEAD | mem[768] | golden | verdict |
|---|---|---|---|---|
| sb base x29 | yes | 0x0 | 0x41 | RED |
| sh base x29 | yes | 0x0 | 0x4243 | RED |
| sb value x27 | yes | 0xff | 0x42 | RED |
| sh value x27 | yes | 0xffff | 0x4243 | RED |
| sb value x26 | yes | 0x0 | 0x44 | RED |
| control | yes | 0x41 | 0x41 | PASS |

## Candidate item (backlog format — BK-28)

**BK-28 — SB/SH lowering: complete the aliasing guard (rs1==29, rs2==26/27
classes).** The DEFECT-31c minimal fix guarded only rs1==30. The else
branch still: (a) re-derives the address after clobbering the base's
register with the shift constant, (b) reads the value register after the
mask/init LDIs have clobbered it (x27→mask bits, x26→0). Fix shape is the
same as the rs1==30 branch: compute address ONCE in a saved scratch, read
the value BEFORE any scratch LDI, restore callee-saved around the
sequence. Gate: tests/test_defect31d_aliasing.py with 6 legs (the exact
probe programs above as fixtures, plus non-aliased control), RED first at
current HEAD. Prereq: engine-core file → worktree isolation per AGENTS.md.
Source: this receipt + dbg_d31c_latent_alias_af3e.py.

## Honesty

- All numbers are structural asserts on real runs (halted/faulted/mem
  reads from GlyphRunner receipts this tick), not floors/cost claims —
  rule-1 floors treatment does not attach (no rate cited).
- NOT verified: no WGSL twin (transpiler-side, nothing spatial); no
  xv6-nano scenario exercises these classes, so the landed 13/13 gate
  stays green and this is NOT a regression — latent-only; the FIX is
  proposed, not implemented (research never lands engine code).
- Priority signal: file:line — tools/rv64i_to_glyph.py:1084-1111 (SB
  else), :1188-1215 (SH else). Not a "most-patched" claim; it is the
  direct continuation of the receipted DEFECT-31c "latent, unmeasured"
  disclosure.
