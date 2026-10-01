# RECEIPT — BK-59 DESKTOP GATE SCORECARD (measured at HEAD ba4b955d, 2026-10-01)

**Builder:** af3e62239ce2 (this cron tick). **Trigger:** DIRECTIVE_BK56
landing sequence §5.3 + ledger "Next tick" instruction. **Session pick
verified:** HEAD ba4b955d == monitor fingerprint, state CLEAN, queue=0,
mailbox rule clean (newest binding file older than HEAD; BK-56's own
directive sequenced this filing).

## What this receipt IS

The DoD evaluation of the BK-59 desktop gate, every line measured or
re-verified THIS SESSION at HEAD ba4b955d. Directive:
`.builder_queue/DIRECTIVE_BK59_DESKTOP_GATE.md`.

## DoD scorecard (with live evidence)

1. **BK-38..45 sequenced commit + falsifiers — GREEN.** Family run 50/50
   (BK-45 RESOLUTION tail, GLYPH_BACKLOG.md); BK-38 + BK-52 re-run this
   session: 11/11 passed in 0.31s (`tests/test_bk52_kfault0_trap.py
   tests/test_bk38_ld_fence.py`).
2. **BK-52 vector guard — GREEN** (same 11/11 run).
3. **BK-50 door posture + BK-51 twin tile consults — GREEN (landed).**
   BK-50 RESOLUTION 6/6 x2; BK-51 RESOLUTION 5/5 with stash-RED; BK-77
   box-only widening 7/7 x2.
4. **BK-56 read posture — GREEN (landed)** bd76198c, gate 13/13 x2 +
   mainline re-verify (ledger 2026-10-01 ~08:1x).
5. **BK-53 hijack chain (oracle) — DEAD, re-verified LIVE this session.**
   `.builder_queue/probe_ek1_vector_hijack_af3e.py` re-run: stdout md5
   `8a8bcb6f2fd9cc730a1fd5e72c68ec41` == the landed citation in the BK-77
   row; verdicts D1 no escape / D3 no landing / D5 no vector escape, C1
   E-K1 baseline live.
6. **BK-55 hijack chain (twin) — DEAD (landed).** BK-77 RESOLUTION: post-fix
   probe results md5 `6dd9a46fbe606aa5004d059d1a4c7f83` (D1 no hijack fault
   32772, D2 no landing, D3 no door).
7. **BK-57 twin LD tile consult — DIVERGENCE GONE, verified LIVE this
   session; the backlog row is STALE.**
   `.builder_queue/probe_bk51_twin_tile_ld_af3e.py` re-run at HEAD: L1 twin
   out-of-tile LD faults 656, r3=0, mode→SUPER (results md5
   `7033af4b3fd878be78adfd883dba673a` — differs from the research receipt's
   `8334c4d4f5e56082fa39e530c48a1b89`, which is the POINT: the leak closed
   when BK-48 landed `ld_tile_fault`); L4 oracle parity unchanged (fault
   656); L3 in-tile control clean (r3 canary, mode USER).
8. **BK-54 ring cursor — LANDED (commit 4a6c44dc).**
   Gate `tests/test_bk54_ring_saturation.py` 8/8 GREEN, family 33/33 GREEN
   (BK-24 5/5, BK-11 6/6, BK-46 8/8, BK-47 6/6). Branchless clamp in
   `tools/glyph_gpt/libc_runtime.py` clamps cursor at 832, records dropped
   frame count in word 725, diverts saturated frames to scratch sink 726..729.
   Canaries past 832 (840, 860) remain untouched. Every defect in BK-59's DoD
   is now CLOSED.

## Decisions made (all class (a) per DECISION_RULES §3; full text in the directive)

- BK-53, BK-57: RESOLUTION CLOSED (subsumed and verified dead).
- BK-54: LANDED (commit 4a6c44dc).
- Stage 3 open/close: class (b), RESERVED to Jericho. All DoD prerequisites
  are 100% green at HEAD. One-line ask presented to Jericho. NO compositor
  work starts before Jericho answers (a)/(b).

## What this receipt does NOT prove

- BK-54's fix is not written — only re-measured and postured.
- The BK-57 rot-guard leg check (does BK-48's L1a pin the out-of-tile LD
  fault?) is asserted from the resolution tail text, not re-run in isolation
  this session beyond the probe itself.
- No WGSL device leg ran this session (all twin citations are landed gate
  receipts; the probes re-run are oracle/device-harness probes whose landed
  md5s were compared, plus the BK-57 probe which ran on-device shape).
- Stage 3 readiness is a FUTURE state: it exists only after the three
  closures land and Jericho answers the ask.
