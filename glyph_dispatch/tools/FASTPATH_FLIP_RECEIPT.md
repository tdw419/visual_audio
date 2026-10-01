# Fast Path Flip Attempt — Receipt

**Date**: 2026-09-02
**Task**: Flip `DECODED_FASTPATH_DISABLED = false` and boot bbird to shell
**Outcome**: FLIP REVERTED — fresh fast-path boots wedge deterministically. Three real fast/slow parity bugs were found and fixed along the way.

## Evidence chain

1. Flip landed; fresh bbird boot (batch=100k) wedged: PC frozen at
   `0xffffffff808a4aa6` (`queued_spin_lock_slowpath`) from hb 18.4M onward.
   Historic pc `...4aa2` same function. Deterministic across every attempt.

2. Root-cause discovery that invalidated ALL prior checkpoint-resume fastpath
   results: `load_checkpoint()` restores memory via raw `write_buffer` and never
   marks dirty ranges → `_sync_decoded_ops()` no-ops → decoded_ops buffer stays
   ZEROED (`dop.len==0` fails the gate) → resumed "fast" cores silently ran the
   slow path. The 600M-step "clean" lockstep, both 100M runs, and the Alpine-init
   resume run never exercised the fast path.

   Fix: `tools/fastpath_core.py::_post_load_sync()` — rebuild linear shadow from
   GPU buffer, `_mark_range_dirty(0, n)`, `_sync_decoded_ops()`.
   Verified: after 50k steps `bb_threaded_insts=464144, bb_fallback_insts=1`.

3. With a genuinely-fast core, lockstep from `bbird_fresh_500K` diverged at
   step 10,700,000 — deterministically, same step and same regs on repeat runs —
   but phase-2 replay of the same window as ONE step() call found no divergence.

4. Root cause of THAT: the mtime jitter LCG (`var<private> mtime_jitter_lcg`,
   seeded 0x2545F491) resets on EVERY dispatch → mtime after N steps depended on
   host dispatch chunking, not N → interrupt timing differed between chunk
   patterns. **Fix landed**: jitter removed, `mtime_delta = 1u` constant
   (chunk-independent). This also explains the historic "dispatch-alignment
   sensitivity".

5. Wedge persists after jitter fix. Two more parity gaps fixed (kept):
   - Threaded loop now ends the block after STORE ops (ops 22-25): GPU stores
     never update the host `_linear_shadow`, so kernel self-modifying code
     (alternatives patching) could leave stale decoded_ops that the threaded
     loop — which does no `.raw` validation — would execute pre-patch.
   - Threaded path now calls `maybe_take_interrupt()` BEFORE executing each
     instruction, matching the fetch path (was: after — one-instruction-late
     delivery).

6. Wedge STILL persists (also ~0x808a4aa6, entering ~12-17M). The wedged image
   is genuinely dead: resuming `.ckpt/percpu_spin_fastrun.rv64ckpt` on the SLOW
   core spins identically; poll word at VA `0xffffffff80fbc8ec` stays 0 after
   2M steps. On a single hart this is self-deadlock-shaped: an interrupt lands
   inside the lock holder's critical section and the handler spins on the same
   lock. Slow path's timing never hits it; every fast-path timing parity fix
   shifts the entry point but doesn't remove it.

7. Flag reverted to `DECODED_FASTPATH_DISABLED = true` (slow default). Fast path
   remains opt-in via `fastpath_core.CoreFast` / `fresh_boot_ckpt --fast-path`
   for resume-based work, where it is correct and ~3x faster.

## What's real now

- Resume+fastpath (post_load_sync) is clean for 10.65M+ steps of real threaded
  execution (bb counters prove the path is live).
- The three parity fixes are genuine correctness improvements independent of
  the wedge.
- Open lead for next session: first-behavioral-difference hunt between
  fast-fresh and slow-fresh boots via UART bisection (not lockstep), and the
  interrupt-delivery gate in `maybe_take_interrupt` vs spec under the threaded
  path's skipped I-TLB translate (fixmap aliasing candidate).

## Files

- `tools/SPATIAL_RV64I.wgsl` — flag true (reverted); jitter removed; store-stop;
  IRQ-before-execute in threaded loop
- `tools/fastpath_core.py` — CoreFast/CoreSlow + `_post_load_sync`
- `tools/fresh_boot_ckpt.py` — `--fast-path`
- `glyph_dispatch/tools/fastpath_lockstep_harness.py` — `LOCKSTEP_FROM` env,
  slow-loader, chunk env vars
- Checkpoints: `.ckpt/bbird_fresh_500K*.rv64ckpt`, `.ckpt/bbird_fresh_5M.rv64ckpt`,
  `.ckpt/percpu_spin_fastrun.rv64ckpt` (wedged state)


## RESOLVED (2026-09-03, follow-up session)

Root cause chain found and fixed. The wedge and the residual lockstep divergences
were two bugs stacked:

1. **Double IRQ sampling** (fixed earlier in this file's timeline): threaded path
   called maybe_take_interrupt() post-execute in addition to the fetch path's
   pre-execute call. Fixed by delivery-at-pre-execute only + mip refresh after.

2. **Stale decoded ops on self-modifying code** (fixed): threaded loop executed
   pre-decoded ops without comparing .raw against live memory. First caught live
   at pc 0xffffffff800769ec: slot held `jal +128` (raw 0x0800006f) while memory
   held `nop` (0x00000013). Fixed with per-iteration raw validation.

3. **mtime double-advance on threading fallback** (fixed, the last divergence):
   mtime advanced at loop top, but the threaded fallback `continue`s (stale op,
   trap-pending) exit without i++ — one retired instruction, two mtime ticks.
   Measured: fast core +184,735 ticks per 100k steps (~1.85x) vs slow +100,000.
   The skew fed rdtime -> guest jitterentropy RNG -> entropy-pool memory
   divergence -> random-dependent register divergence (first seen as x13/x15 at
   5.6M-10.8M). Fixed by advancing mtime at the three retirement sites.

Validation after fix 3:
- Lockstep (regs+CSRs+full memory hash): 100M steps, ZERO divergence
  (/home/jericho/f6b_lockstep.log). Previously diverged by 5.6M.
- Fresh boot, DECODED_FASTPATH_DISABLED=false baked into the shader: bbird shell
  at 497,600,000 steps / 2005s — identical step count to the slow-path baseline
  (497.6M), confirming timing parity (/home/jericho/f6_boot_fastflag.log).

The flip STICKS: fast path is now the default and arch-identical to slow.
