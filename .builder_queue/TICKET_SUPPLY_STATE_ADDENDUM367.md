# Supply state addendum 367 — 2026-09-20 ~20:2x CDT (orchestrator cron af3e)

## Monitor delta attribution: DIRTY_ACTIVE -> REPAIR_PENDING (head 12789220f -> 95d7f02c)

The transition is a MONITOR-SEMANTICS event, not a new lane defect:

1. Tree went tracked_dirty=0 when the sibling Qoder bare-metal lane landed
   its churn as 12789220 + 95d7f02c (both docs/fix commits under
   tools/bare_metal_poc/ — OUT OF SCOPE for this lane per the 2026-09-19
   redirect). Nothing in this lane's write set was touched.
2. On a clean tree the monitor level-triggers REPAIR_PENDING when open
   .json tickets exist (tools/glyph_build_chain_monitor.py:230). The two
   open tickets it counts:
   - DEFECT-22E_gh18_19gb_not_reproducible.json — measured-negative probe
     series; its own "next" field parks the decision on Jericho (renew
     supply / accept DEFECT-22 stability bound / re-point cron). NOT
     lane-implementable.
   - TICKET_SUPPLY_STATE_20260919_0845.json — a supply-state snapshot
     whose status is literally "HOLD — Jericho's seat". NOT work.
   Both are parked on Jericho's seat. There is no adoptable repair work
   behind the REPAIR_PENDING state; it will stay level until one of the
   two tickets is resolved at the seat or the PS012 ruling lands.

## Re-checks this tick (all negative, nothing to adopt)

- No RULING_ps012* exists; no .builder_queue file newer than the HOLD
  receipt section in brief_ps011_golden_trace.md (20:05) except the
  Qoder bare-metal commits themselves. No new Jericho direction.
- PS-lane gate re-run by this run on 95d7f02c:
  tests/test_pyshader_golden.py + test_pyshader_measure.py +
  test_pyshader_multihart.py + test_pyshader_divergence.py ->
  **32 passed in 33.80s** (exit 0, GPU legs included). Inherited green
  re-verified as this run's own measurement.
- PS-chain state: PS005-PS011 done (PS010d + PS011 completed after the
  PS009 fork ruling RULING_ps009_fork_cleared_ps010_go.md lifted the
  earlier HOLD). Next row PS012 (GPU_CPU_EMULATOR_ROADMAP.md:338) is
  [J-DECISION] — three exits on PS009+PS011 data. PS013 gated on PS012.

## What this run did NOT do

- No code changes; no adoption of either open ticket (both seat-parked).
- No re-execution of the PS010d/PS011 measurement legs beyond the 32-test
  re-run; the divergence curve (peak 2.498 @ N=64, ~1.72 @ 65536) is
  cited from the PS011 HOLD receipt, not re-measured.
- No verification of the bare-metal commits' contents (out of lane).

next: HOLD pending RULING_ps012 (or in-channel Jericho word). The
REPAIR_PENDING monitor state is expected to persist during the HOLD;
this addendum is the attribution record so future wakes skip the
re-derivation.
