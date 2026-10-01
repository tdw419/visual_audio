# RECEIPT — Claim-queue item 6: GlyphRunner WGSL floor (refresh + verdict-machinery proof)

Builder: cron af3e62239ce2 · 2026-09-22 ~13:27 CDT · HEAD 02cd1b32

## Premise correction (measured, not argued)

Item 6's text ("floors_authoritative.json has NO entry for the GlyphRunner
WGSL path") was STALE at claim time. Ground truth at tick open:

- `glyphrunner_wgsl_step` 639.1 µs and `glyphrunner_wgsl_step_tput`
  70.3 µs were ALREADY in floors_authoritative.json — landed 09-21
  ~11:40 CDT (80d9285f, pre-registered unblock from RECEIPT_R11_task_queue.md).
  The calibrator's WGSL section (calibrate_floors_authoritative.py:140-248)
  was already in place.
- The REAL residual the 12h freshness window makes load-bearing:
  `measured_at` 2026-09-21T16:40Z was ~27h old → check_regime.py hard-FAILS
  on them ("FAIL: floors are stale (26h old)") and every verdict on the
  path was UNDETERMINABLE-in-practice. Additionally, the shader itself
  changed this afternoon (item 5, 02cd1b32: CALLR dispatch branch added),
  so a re-measure was due regardless.

## What this tick did

1. Re-ran calibrate_floors_authoritative.py (dedicated process, real
   GlyphRunner WGSL per-step protocol: 1 dispatch + 1 blocking cpu-state
   map_sync readback; real resident image for the tput leg). Fresh
   measured_at 2026-09-22T18:27:39Z, adapter RTX 5090 Laptop via Vulkan:
   - step 1165.2 (median) · glyphrunner_wgsl_step 632.4 (spaced latency)
   - glyphrunner_wgsl_step_tput 71.1 (tight-loop throughput)
   - prior → fresh deltas: gr-step 639.1→632.4 (−1.0%), tput 70.3→71.1
     (+1.1%), step 910.2→1165.2 (+28%) — WGSL-path numbers held within
     ~1% across 26h; the CPU step path drifted (consistent with the
     known host non-stationarity that motivated the 12h window).
2. check_regime verdict legs (both paths, run after refresh):

GREEN (ADMIT) legs — exit 0:
  leg gr_tput_admit: 700.0 us/roundtrip vs floor 71.1 us (9.85x) -> ADMISSIBLE
  leg gr_spaced_admit: 850.0 us/roundtrip vs floor 632.4 us (1.34x) -> ADMISSIBLE

RED (REJECT) legs — exit 1:
  leg gr_tput_reject: 40.0 us/roundtrip vs floor 71.1 us (0.56x) -> INADMISSIBLE (below floor)
  leg gr_spaced_reject: 80.0 us/roundtrip vs floor 632.4 us (0.13x) -> INADMISSIBLE (below floor)

First attempt of the leg runs was a CLI-shape error (--leg takes the
roundtrip COUNT as int; "x1" ValueError) — instrument misuse, not a gate
defect; corrected invocation above, real exits captured.

## What this PASS does NOT prove

- No rate claim is made or adjudicated this tick — the legs are
  synthetic numbers chosen to straddle the floors, proving the ADMIT/
  REJECT machinery, not any workload's performance.
- The floors are point-in-time (12h window); they go stale again and
  check_regime will (correctly) refuse until the next calibration.
- Single GPU/host (RTX 5090 Laptop); no second-machine claim.
- The `step` floor's +28% drift is recorded but NOT investigated — no
  active receipt cites it; flagging only.
- Queue item 6's own gate wording ("entry lands") was already
  discharged by 80d9285f; this receipt adds the freshness re-measure
  and the four verdict legs it named.
