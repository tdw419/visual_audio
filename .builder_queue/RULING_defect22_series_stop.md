# RULING — stop the DEFECT-22 capture series (do not claim it fixed)

**Date:** 2026-09-14 · **Seat:** orchestrator ("you lead", 2026-09-14) · reversible by Jericho
**Ticket:** `.builder_queue/DEFECT-22_arc_legA_instability.json` (status: OPEN)

## Decision

STOP the capture series. Do not open leg #80. Do not append further ledger entries.

## Why (measured)

- 79 legs run, **51 consecutive worker-scope greens**, each with real telemetry:
  `crashes=0 faulthandler_crashes=0 oom_kill_delta=0 mem_peak 1.59-2.19 GB` (cap 4 GiB).
- Original incidence: 2 crashes of 12. If p ~ 1/6, P(51 clean) ~ 1e-4 - the streak is decisive.
- The series' own decisive finding: the crash frame is a VICTIM
  (`glyph_isa_v2.step:561 _check_alignment`, reached from
  `tests/test_gh22_device_driver_abi.py:174`), and leg A runs `pytest-randomly` with a
  fresh seed per run, so **no earlier arc run is replayable**.

## Why stopping is CORRECT rather than premature

The series' product was the INSTRUMENT: per-run `crashes / faulthandler_crashes /
oom_kill_delta / mem_peak` telemetry under worker scope. That telemetry now runs in the
ordinary sweeps, so recurrence is detected without a dedicated series. Continued legs add
redundant confirmation at ~1 agent fire every 7 minutes.

## What this ruling does NOT license

- It is NOT a fix claim. DEFECT-22 is **not reproduced, not root-caused**. The victim frame
  was never traced to an origin, and the original 2-of-12 remains unexplained.
- Do not delete the ledger, the briefs, or the ticket. Do not mark it FIXED.
- Do not remove the crash telemetry from the sweep path - that telemetry is the reopen trigger.

## Gate / reopen trigger

1. Ticket status becomes: **SERIES STOPPED - not reproduced (51 greens), not root-caused**.
2. AUTO-REOPEN: any sweep or worker-scope run reporting
   `crashes > 0 OR faulthandler_crashes > 0 OR oom_kill_delta > 0`.
3. On reopen, the FIRST action is a seed-pinned replay (`pytest-randomly` seed recorded in
   the run), so the next occurrence is replayable - the defect the series itself exposed.
4. Ledger hygiene folds in from D22-LEDGER-1: one append path, machine-generated
   timestamp, verdict as a field. The 50 per-leg `append_d22_ledger_leg*.py` scripts are removed.

## SEAT CONFIRMATION (2026-09-14)

Confirmed by Jericho, explicitly: the capture series is stopped on the stated evidence
(51 consecutive worker-scope greens, P(clean) ~1e-4 against the original 2-of-12
incidence), labelled SERIES STOPPED — not reproduced, not root-caused, with the
auto-reopen trigger (crashes>0 OR oom_kill_delta>0) and seed-pinned replay as the first
action on recurrence, both as specified above. As with DEFECT-23, the orchestrator's
prior ruling was provisional; this is the actual seat authorization.
