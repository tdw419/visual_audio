# RECEIPT — DEFECT-31c RESOLVED: SB/SH rs1==x30 base aliasing, minimal surgical fix

**Date:** 2026-09-25 ~10:4x CDT. **Builder:** af3e62239ce2. **Base:** cad5bd5d.
**Scope:** tools/rv64i_to_glyph.py (OP_SB, OP_SH) only.

## Symptom → root cause chain (all measured this tick)

1. **The in-flight dirty rewrite was a net regression.** Snapshot preserved
   verbatim in `.builder_queue/DEFECT31c_dirty_rewrite_snapshot.diff`
   (198 lines; +124/-42 full r26..r30 save/restore rewrite of OP_SB/OP_SH).
   Measured on the dirty tree: xv6 gate 4F/9P (ek1, ek2, go1[6], go1[7],
   `SpatialMisalignmentFault: PC.x=1953/1887`), identical to the previous
   tick's measurement — the lane-mask fix (mask 2→3) changed nothing.

2. **Falsifier 1 (trace diff) — control path, not memory.**
   `.builder_queue/dbg_d31c_trace_diff_af3e.py` (scenario 6, 8634 steps):
   the faulting PC word 1887 decodes to `ADD r30 r3` (mid-text, not an
   instruction boundary a jalr should reach). The store watcher
   (`_WatchedMem`) recorded **zero stores to words 460-475** (the jump-table
   region containing the corrupted target 0x767-ish) across the whole run;
   the last stores before the fault were the trap-handler prologue (words
   1720-1733, rv pc 0x0-0x34). Conclusion: the rewrite corrupted the
   control flow through its own re-ordered PUSH/POP/register-plan, not any
   memory word. Scratch at fault: r28=0x1700b4, r29=0x50, r30=0xfef —
   leftover SB-lowering temporaries.

3. **Falsifier 4 (baseline discrimination) — HEAD passes, dirty fails.**
   `git stash` → HEAD lowering: xv6 gate **13/13 PASS in 32.43s**; iso
   probe `dbg_d30_iso_sb_base_va_af3e.py` RED on HEAD (t5base mem[768]=0x0,
   ctrl mem[768]=0x41 — the rs1==x30 aliasing defect is real on HEAD).
   `git stash pop` → dirty tree gate 4F/9P again. So: HEAD = gate GREEN +
   probe RED; dirty = probe GREEN + gate RED. The rewrite traded one defect
   for a worse one.

4. **Lowering diff.** `.builder_queue/dbg_d31c_diff_lowering_af3e.py`
   (scenario 6): exactly 10 differing RV instructions, all SB sites; the
   reorder moved the value capture before the address staging — the control
   corruption mechanism, consistent with (2).

## The fix (attempt 3; attempt budget 6)

Revert to HEAD (`git checkout tools/rv64i_to_glyph.py`), then add a
**rs1==30-only branch** to OP_SB and OP_SH; the non-aliased path keeps the
HEAD body byte-for-byte (it is literally the same lines in an `else`).
Branch shape: single address computation in r28 (never re-derived by
re-reading the base — the engine-truth rule from DEFECT-31), lane/shift in
r27, cur_word in r29, value+mask in r26/r30, base PUSHed/POPed.
r30 is consumed before `LDI r30 0xff` destroys it; `ST r28 r29` needs no
base. 3 pushes (vs 5 in the rejected rewrite, vs 2 on HEAD-aliased-never).

Known latent parity flaw (documented, NOT fixed — unmeasured, gate-exempt):
if rs2==x27 the value read hits the shift temp, on HEAD AND on this fix;
gcc never emitted it in any gate scenario.

## RED leg (shown before trusting GREEN)

- On HEAD: `dbg_d30_iso_sb_base_va_af3e.py` → `t5base halted True faulted
  False | mem[768] 0x0 mem[769] 0x0` (store silently lost) — RED.
- Dirty rewrite: xv6 gate `1 failed, 9 passed` (x-run) / 4F/9P full — RED.

## GREEN legs (this tree)

- `dbg_d30_iso_sb_base_va_af3e.py` → `t5base ... mem[768] 0x41 mem[769]
  0x42`; ctrl same. **GREEN** (byte-exact).
- `dbg_d30_iso_sh_base_va_af3e.py` → `mem[768] 0x1141 mem[769] 0x2242
  (expect 0x1141 / 0x2242)`. **GREEN**.
- `tests/test_rv64i_to_glyph_xv6_nano.py` → **13 passed in 31.72s**.
- Twins: `test_gh23_libc_runtime.py + test_bk11_coreutils.py +
  test_coreutils_volume2.py` → **18 passed in 61.22s**.

## What this PASS does NOT prove

- rs1==29 SB/SH (second address computation re-reads r29 after it holds 3
  on HEAD) is NOT fixed and NOT measured — flagged in the ledger as a
  candidate latent defect; no gate scenario exercises it.
- rs2==x27 latent aliasing (parity with HEAD) untested by construction.
- Only the four named gates ran; the wider transpiler suite
  (test_rv64i_to_glyph*.py family beyond xv6/twins) was NOT re-run this tick.
- The WGSL twin (run_wgsl) was not exercised; R1.4 convergence remains open
  and unaffected by this fix.
