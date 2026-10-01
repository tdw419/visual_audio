# RECEIPT_floors_glyphrunner_extension.md

**Rung context:** R1.1 residual floor gap (pre-registered in
RECEIPT_R11_task_queue.md: "no calibrated floor exists for the GlyphRunner
WGSL code path"). Lane: PRODUCT_ROADMAP (1827f6cb), builder cron af3e62239ce2.
**Base revision:** 18dc85f2 (dirty: unrelated lane files, none touched here).
**Freshness:** floors_authoritative.json re-measured 2026-09-21T16:40:27Z —
inside the 12h window. Adapter: RTX 5090 Laptop (Vulkan), same process as
all four floor quantities (policy rule 1: separate process from the probe).

## What landed

1. **calibrate_floors_authoritative.py extended** (additive, same dedicated
   process): two NEW floor quantities for the GlyphRunner WGSL code path —
   - `glyphrunner_wgsl_step` = **639.1 µs** — spaced (5ms sleep) per-step
     round-trip **latency**: 1 dispatch + 1 blocking cpu-state readback on
     the real `wgsl_glyph_isa_v2` shader.
   - `glyphrunner_wgsl_step_tput` = **70.3 µs** — **pipelined throughput**,
     tight loop (no sleep), same protocol, run on the REAL resident image
     (53×32×3 bake rebuilt in-process), median of 30 reps × per-rep medians.
   All prior quantities (`step`, `get_state`, `gen_dispatch_plus_map`)
   unchanged in definition; values re-measured (non-stationary host —
   step moved 4870→1567→910 µs across the day; that is exactly why the
   12h window exists).

2. **probe_r11_task_queue.py** LEG line now cites
   `glyphrunner_wgsl_step_tput x1` (was `step x1`).

3. Falsifier probes (kept as receipts-in-code):
   `.builder_queue/orch_grfloor_falsifier_af3e_20260921.py`,
   `.builder_queue/orch_grbacklog_af3e_20260921b.py`.

## The mechanism (measured, not reasoned — rule 3 compliant because measured)

The original INADMISSIBLE verdict (0.02x) was CORRECT arithmetic on a
CATEGORY ERROR: the receipt's leg is a tight-loop **throughput** number;
the only floor that existed was a spaced **latency** number. Falsifier
results (one process, interleaved):
- spaced small-image step: 686.7 µs · spaced resident-scale: 603.9 µs
- tight loop, per-step map: 72–102 µs (matches probe's 89–111 µs)
- empty-dispatch (halted CPU) lower bound: ~34 µs
So ~5–9x of the "0.02x violation" was latency-vs-throughput mismatch; the
remainder was the proxy-vs-real-shader units mismatch already receipted.

## Gates

GREEN (literal):
```
$ python3 .builder_queue/probe_r11_task_queue.py
CPU queue drain: jobs [7, 11, 13] -> results [21, 33, 39] expected [21, 33, 39] depth=0 receipt=0x5eed0003 steps=382 ticks=9
WGSL result@754 = 0x0 expected 0x15 (DIVERGENT — recorded, not gated) steps=198 halted=True
LEG wgsl_queue 9,124 steps/s 109.6 us/rep glyphrunner_wgsl_step_tput x1
VERDICT=PASS (cpu queue drain host-verified; floor line emitted)

$ python3 .builder_queue/check_regime.py --leg wgsl_queue 9124 109.6 glyphrunner_wgsl_step_tput 1
leg wgsl_queue: 109.6 us/roundtrip vs floor 70.3 us (1.56x) -> ADMISSIBLE

$ python3 -m pytest tests/test_gh26_task_queue.py tests/test_gh26_resident.py tests/test_gh264c_teleop.py tests/test_bk3_signals.py tests/test_glyph_linter.py -q
.................................                                        [100%]
33 passed in 1.35s
```

RED (literal):
```
$ python3 .builder_queue/probe_r11_task_queue.py --corrupt ; echo exit=$?
LEG wgsl_queue 12,527 steps/s 79.8 us/rep glyphrunner_wgsl_step_tput x1
CORRUPT-LEG: expectation did not match (correct RED)
VERDICT=FAIL failures=['cpu:slot0', 'cpu:slot1', 'cpu:slot2']
exit=1

$ python3 .builder_queue/check_regime.py --leg wgsl_queue 11125 89.9 glyphrunner_wgsl_step 1 ; echo exit=$?
leg wgsl_queue: 89.9 us/roundtrip vs floor 639.1 us (0.14x) -> INADMISSIBLE (below floor)
exit=1
```
The second RED is the discriminating leg for the category fix: the SAME
number against the WRONG floor still rejects — the floor pair distinguishes
latency from throughput rather than accepting everything.

## What this PASS does NOT prove

- **WGSL twin divergence unchanged**: WGSL still halts at 198 steps with
  result@754 = 0x0 (CPU: 382 steps, result 0x15). Still not root-caused;
  still never gated. The throughput floor times the protocol, it does not
  make the WGSL execution correct.
- **R1.1 gate status unchanged**: the rung gate (CPU in-guest task,
  host-verified) was already PASSed at 982c24c3. This receipt closes the
  floor-honesty gap only. Post-boot job arrival (mailbox receive-while-busy)
  remains the R1.1 residual gap; R1.2 (≥4 agents, fault-injection RED leg)
  untouched.
- **Cross-quantity ratios still barred**: `wgsl_tput / rv32i_step` mixes
  code paths; only same-path comparisons are admissible.
- Floors remain non-stationary; any rate claim after 2026-09-21T16:40Z+12h
  must re-run the calibrator.
