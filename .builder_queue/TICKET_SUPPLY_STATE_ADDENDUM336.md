# TICKET SUPPLY STATE — ADDENDUM 336 (2026-09-20, builder cron af3e62239ce2)

Status: **HOLD on PS009 itself — but new J-DECISION input landed this
tick.** Wake cause: monitor saw HEAD f67d3ab3 → 123c8976, which is
addendum-335 landing itself (self-referential, 4th consecutive). GENUINE
new supply found on scan: untracked `.builder_queue/PS009_BASELINE_RECEIPT.md`
+ `.builder_queue/probe_ps009_baseline_rv32i.py` (orchestrator-lane
baseline for the [J-DECISION] fork, never referenced by 334/335).
Landed both this tick, with an independent re-measure addendum.

## Re-measured this tick (not quoted from 335)

- Standing gate on current tree, my own run: fde+ctl+compiler →
  **96 passed / 2.48s**, rc=0.
- Probe reproduction (2 full runs, pin exact 12/12 each): Mode A
  3,301 / 3,199 steps/s; Mode B 90,658 / 78,847 steps/s; batching gain
  27.5x / ~24.6x. **Absolute rates differ ~10-12x from the receipt's
  original table on the SAME host** (load-sensitive backend); the
  batching-gain RATIO is stable (24.6x-35x across all 4 measurements).
  Consequence recorded in the receipt addendum: the fork's ≥5x test
  must be a same-run ratio (PS009 generated vs Mode B, one process,
  back to back), NOT the receipt's stored absolute threshold
  ("PS009 < 1,471 steps/s") — that number is stale by an order of
  magnitude.
- PS write set still clean; tracked-dirty set = Qoder BM lane + guest
  churn, untouched per lane split.

## State (restated for the record)

- PS007 ✅, PS008 ✅ (SPEC convention, RULING_ps008 effectuated e649cddf).
- **Next row PS009 — INELIGIBLE to this loop**: [J-DECISION]
  GPU_CPU_EMULATOR_ROADMAP.md:67 reserves the continue/harvest call to
  Jericho. The baseline receipt now on disk gives him everything the
  fork needs: Mode B baseline, the regime-mismatch warning
  (PS009's per-taken-branch re-dispatch vs shader-internal batching),
  and the corrected same-run-ratio fork gate.
- SE021: ~98th hold, BLOCKED-ON-JERICHO (maildrop md5 ab846c18
  unchanged this tick, re-checked).

## Unblock (unchanged + sharpened)

1. PS009 go/no-go from Jericho on the J-DECISION row. Decision inputs
   now fully staged: `.builder_queue/PS009_BASELINE_RECEIPT.md` (incl.
   re-measure addendum + corrected fork gate). If Jericho wants the
   MEASUREMENT legs run before ruling, a one-line "measure PS009" is
   all that's needed — the measurement itself is mechanical; only the
   continue/harvest FORK stays reserved.
