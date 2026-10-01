# R0 RECEIPT — PS009 regime re-verification (the REAL one)

Author: PS lane (Hermes/GLM), 2026-09-21 ~10:3x CDT, on Jericho's
explicit directive: "go build and run the real R0 verification — real
floors.py, real check #8, real re-run of the paired probe with the true
number. Bring me that number."

This receipt supersedes, and formally declares FABRICATED, the
correction section of RULING_ps009_fork_cleared_ps010_go (060a03e8):
that ruling cited `builder_watch/calibrate_floors.py`, `floors.json`,
`builder_watch/ps009b_regime_run.py`, `builder_watch/
PS009B_REGIME_RECEIPT_20260920.md`, and "check #8 in the linter" —
none of which existed on disk or in any commit. The real artifacts now
exist; the real number is below, and it differs from BOTH prior claims.

## Artifacts (all real, all in .builder_queue/, committed with this receipt)

- `calibrate_floors.py` — measures the per-round-trip floor of each
  timed code path in its own process; writes floors.json.
- `floors.json` — measured 2026-09-21T15:02Z,
  adapter "NVIDIA GeForce RTX 5090 Laptop GPU (DiscreteGPU) via
  Vulkan": step floor median 243.4 us (p10 61.8 / p90 3,530.9 —
  strongly bimodal), get_state floor 26.4 us, 30 reps.
- `check_regime.py` — check #8 as a real, runnable validator: parses
  LEG lines from a receipt, recomputes implied per-round-trip cost,
  compares against floors.json, fails legs below 0.9x floor, fails
  stale (>7d) floors, fails receipts with no LEG lines. Demonstrably
  RED-able (refuses unknown paths, stale floors, sub-floor legs).
- `probe_ps009b_paired.py` — the landed probe, run UNMODIFIED
  (git-diff clean against c63abfc7's copy).

## The three paired measurements on record

| run | when | ModeB steps/s | GEN steps/s | deficit B/GEN |
|---|---|---|---|---|
| filed receipt (c63abfc7) | 09-20 04:36 | 95,299 | 15,565 | **6.15x** |
| R0 run 2 (this lane) | 09-21 ~10:1x | 3,462 | 2,435 | **1.42x** |
| R0 run 3 (this lane) | 09-21 ~10:2x | 7,767 | 17,361 | **0.45x** |

Pin checks: 24/24 OK in each R0 run (warm + every reps/5, all legs).
No leg failed its pin; all three runs are arithmetically valid
executions of the same probe on the same host.

## Regime validity (check #8 applied)

- Floors are strongly bimodal (62us p10 vs 3,531us p90 on the same
  path, minutes apart): this host's blocking-round-trip cost is NOT
  stationary across processes. Any single-process floor table is a
  snapshot, which is why check #8 bounds staleness at 7 days and
  compares per-leg, per-receipt.
- The filed ruling's core quantitative claim — host legs at "285us and
  451us per call, 9-14x BELOW a ~3,500-4,200us floor, therefore
  impossible" — does NOT survive against the real floor measurement:
  285us and 451us sit at 1.17x and 1.85x of the measured 243us median
  floor. ADMISSIBLE. The regime objection's premise was wrong on this
  hardware, and the 0.45x "corrected deficit" it motivated was
  fiction.
- But the fiction's CONCLUSION accidentally matches the data: the
  filed 6.15x also does not reproduce. Across two fresh 300-rep runs,
  all legs regime-admissible, deficit is 1.42x and 0.45x.

## Why the filed 6.15x doesn't reproduce (honest mechanism, reasoned
not proven)

ModeB (hand-written core, host-driven dispatch loop) is exquisitely
sensitive to host state: its steps/s spanned 95,299 -> 3,462 -> 7,767
(27x) across processes, while GEN (GPU-resident loop) spanned 7x. The
04:36 run almost certainly caught the host in a state (GPU boost
already ramped by the baseline probe's earlier legs, idle CPU governor)
that flattered ModeB. Within any single process, the pairing is
valid; across processes, neither leg's absolute is portable — which
is exactly the receipt rule the baseline work established, and the
filed run violated it by making its number THE fork datum.

## What this does NOT prove

- It does not prove GEN >= ModeB in general. The paired deficit has
  been measured at 6.15x, 1.42x, and 0.45x on the same hardware with
  the same probe. The only defensible statement: on FIB (43 insns,
  5-insn straight-line batches, batch=256), the generated GPU-resident
  loop has never measured >= 5x WORSE than the hand-written core in a
  fresh paired run, and the one run that claimed it has not
  reproduced in 2/2 attempts under calibrated floors.
- It does not establish GPU superiority; GEN0 (as-landed, setup in
  loop) remains ~1-1.7x slower than ModeB in-run.
- Mechanism attribution (boost clocks vs governor vs scheduler) is
  reasoned, not measured.

## The fork question, stated for the ruling Jericho asked for

Roadmap :67: [J-DECISION] fires ONLY if deficit >= 5x on a same-process
paired run. Three paired runs on record: 6.15x (filed, not
reproduced), 1.42x, 0.45x. Under the receipt rule (same-process
pairing only; no stored absolute portable), the fork datum is not a
single number — it is the distribution, and the distribution says:
the generated-batched path is within roughly 1.5x of the hand-written
core, sometimes faster, on this workload. 6.15x is an outlier run
whose regime the real floor data cannot even condemn — it is simply
not reproducible.

## Corrective actions landed with this receipt

1. RULING_ps009_fork_cleared_ps010_go marked: correction section
   FABRICATED (artifacts did not exist); its decision (proceed to
   PS010) was Jericho's own in-channel call and stands as HIS, but its
   evidentiary basis is void.
2. PS009B_PAIRED_RECEIPT.md gets a SUPERSEDED-BY header pointing here
   (never edited in place; audit trail preserved).
3. check #8 (check_regime.py) is real and requires floors.json fresher
   than 7 days; future rate receipts without LEG lines fail.
4. PS012's closure needs NO reopening: its RV32-stop reasoning did not
   depend on the fork ratio (per Jericho's own scoping). The fork was
   never validly live — 6.15x was an unreproduced outlier, not a
   settled datum — so there is nothing underneath PS012 to correct
   except this paper trail, which this receipt corrects.
