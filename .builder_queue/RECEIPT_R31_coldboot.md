# RECEIPT — R3.1 Cold Boot to Agent-Fleet-Ready, Measured (GATE)

**Rung:** R3.1 — PRODUCT_ROADMAP.md:64-65: "Cold boot to agent-fleet-ready
<60s on this hardware, measured, receipts with floors attached (policy
rule 1)."
**Session:** builder cron af3e62239ce2, 2026-09-21 ~16:4x CDT
**Base:** cee0d963 (R1.4 landed; P2 fully landed: R2.1 docs/BOX_ABI_v2.md,
R2.2 tools/glyph_run.py, R2.3 tools/glyph_cc.py) — P3 R3.1 is the next
eligible rung; no newer RULING in the queue contested this pick.
**Brief:** brief_r31_coldboot.md (tools/check_brief.py PASS, exit 0).

## VERDICT: PASS (measured)

**Cold boot to fleet-ready: 814.0 ms** (rep 1, includes wgpu shader
pipeline creation — that IS the cold boot). Roadmap budget 60,000 ms.
Margin: 73.7x under budget. Warm reps (pipeline reused) ~86 ms —
reported, NOT gated.

## The cold chain (all host-side, over LANDED artifacts unmodified)

1. `build_default_atlas()` — ~30 ms
2. `resident_image(atlas, mode="fleet", timer_quantum=6)` (bake) —
   ~6-12 ms
3. `GlyphRunner(img, ram_words=16384)` init — ~0.1 ms
4. `run_wgsl(max_steps=5000)` to halt — ~777 ms cold (pipeline
   creation) / ~46-50 ms warm; 458 steps, halted=True

"Fleet-ready" is verified against the frozen R1.2/R1.3 words, host-side
from `receipt["ram"]` — the same readiness the R1.2 fleet gate uses:
receipt 0x5EED0005 @765, done bits 0b1011 @717, fault receipt 0xFA026
@731, results {714:6, 728:12, 748:20, 763:30} = RES_FLEET_EXPECT
(y=x·(x+1), seeds 2/3/4/5).

## RED legs (rule 4 — gate shown able to FAIL, at landing time)

Budget leg (`--budget-ms 500`, threshold genuinely missed):

```
COLD_BOOT_TOTAL=785.2 ms (budget 500 ms)
R3.1 COLD BOOT: FAIL (cold 785.2 ms >= budget 500 ms)
BUDGET_EXIT=1
```

Corrupt-verify leg (verifier expectations corrupted; a GOOD boot must
be REJECTED — proves the readiness check is load-bearing, not
decorative):

```
rep0: COLD=826.1 ms steps=458 halted=True ready=False
  ram[765]=0x5eed0005 (expect 0x5eed5a5f) ram[717]=0b1011 results={714: 6, ...}
R3.1 corrupt-verify RED leg: verifier REJECTED the boot (correct discrimination)
CORRUPT_EXIT=1
```

Process note: the first corrupt-verify run was piped through `tail`,
which masked its exit code (tail's 0). Re-run with file redirection;
true exit 1 captured. Both RED tails above are from the re-run/capture.

## GREEN leg

```
rep0: atlas=30.1 bake=6.4 init=0.1 run=777.3 COLD=814.0 ms steps=458 halted=True ready=True
  ram[765]=0x5eed0005 (expect 0x5eed0005) ram[717]=0b1011 ram[731]=0xfa026
  results={714: 6, 728: 12, 748: 20, 763: 30}
LEG cold_boot 563 steps/s 1,777.2 us/rep glyphrunner_wgsl_step x1
warm reps (pipeline reused, NOT the gate): 86.8 ms, 86.6 ms
COLD_BOOT_TOTAL=814.0 ms (budget 60000 ms)
R3.1 COLD BOOT: PASS (cold 814.0 ms < 60000 ms, fleet-ready host-verified)
GREEN_EXIT=0
```

## Floors (policy rule 1) — FLOORS AUTHORITY

- Citable file: `.builder_queue/floors_authoritative.json`,
  measured_at 2026-09-21T16:40:27Z (~0.1h old at gate time; 12h window
  — FRESH). Adapter: NVIDIA GeForce RTX 5090 Laptop GPU via Vulkan.
- Floors used: `glyphrunner_wgsl_step` 639.1 us (spaced) /
  `glyphrunner_wgsl_step_tput` 70.3 us (tight-loop) — the
  GlyphRunner.run_wgsl per-step protocol extension
  (RECEIPT_floors_glyphrunner_extension.md).
- LEG line is boot-shaped per the R1.3 hygiene lesson
  (RECEIPT_R13_preference.md:20-24,87-90): steps/s computed from THIS
  leg's own measured wall-clock (814.0 ms) and step count (458), not a
  raw wall-clock posed as a rate.
- check_regime (separate process, this receipt's leg):

```
leg cold_boot: 1,777.2 us/roundtrip vs floor 639.1 us (2.78x) -> ADMISSIBLE
regime check via --leg: exit 0
```

The implied per-step cost (1,777 us) sits 2.78x ABOVE the bare-step
floor — honest: the cold leg necessarily includes atlas+bake+init
(~40 ms) and one-time pipeline creation, which a bare step does not.
No citation of the banned 6.15x/1.42x/0.45x history numbers.

## What this PASS does NOT prove

- The substrate is the GlyphRunner WGSL engine (shader path) with a
  host-side bake. "Cold boot" here = cold engine start to a verified
  fleet workload — NOT booting a kernel image, NOT the virtio-pixel
  guest, NOT an OS process tree. R3.1's wording ("agent-fleet-ready")
  is satisfied at the level the roadmap's anchor workload lives at;
  a fuller boot story (P3 R3.2 persistence, R3.3 host integration)
  remains open.
- Single image family (the R1.2 fleet image, timer_quantum=6). Other
  images will have different step counts; the budget dominates by 73x,
  so the verdict is robust to that, but per-image numbers are not
  claimed.
- Warm-start behavior is reported (pipeline reuse makes reruns ~86 ms)
  but NOT gated — the gate is the COLD leg only.
- Timing is single-host, single-GPU (RTX 5090, Vulkan), this session.
  No distribution or cross-machine claim.
- No rate claim beyond the LEG line above; nothing else is floor-
  derived.

## Scope

Changed (all additive, .builder_queue/): brief_r31_coldboot.md,
probe_r31_coldboot.py, RECEIPT_R31_coldboot.md (this file),
PRODUCT_LANE_STATE.md (ledger). NOT touched: any engine/shader/baker
file (measurement ran the LANDED artifacts unmodified),
floors_authoritative.json (read-only), protected assets, other
RULING/RECEIPT files.
