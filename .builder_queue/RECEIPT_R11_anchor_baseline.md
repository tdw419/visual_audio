# RECEIPT — R1.1 anchor baseline (PRODUCT_ROADMAP.md:24-27)

**Run:** glyph-transpiler orchestrator, Hermes cron af3e62239ce2
**When:** 2026-09-21 ~10:45 CDT
**HEAD at run:** 9f82d19f25278c175c20b4192499208cdb26137b (branch
glyph-transpiler-autoloop)
**Brief:** `.builder_queue/brief_r11_anchor_baseline.md` (check_brief PASS,
0 invalid / 0 warnings)
**Probe:** `.builder_queue/probe_r11_anchor_baseline.py`

## What this step is (and is not)

R1.1's gate text: "one full agent task completes in-guest, output verified
host-side." This step delivers the **measured baseline** for that gate: one
deterministic agent task (the GH-26.4 resident daemon's `triple()` verb)
completing in-guest under preemptive ticks, host-verified. It does NOT
complete R1.1 — see "What this PASS does not prove."

## Method

- Input pinned: argv payload 0x2A, GH-22 mailbox word 0x3B00112A @750
  (same as `tests/test_gh26_resident.py`); expectation 3×0x2A = 0x7E = 126,
  computed host-side, compared with `==`.
- Drive: `GlyphRunner.drive` (CPU oracle substrate, gated path).
- Timed leg: WGSL/GPU path, protocol-identical to
  `.builder_queue/calibrate_floors.py`'s `step` floor (one dispatch + one
  blocking map_sync readback per round trip, x1).
- Floors re-measured this run in a SEPARATE process (standing rule 1):
  `calibrate_floors.py` → step floor **98.6us** (p10 84.4 / p90 456.2,
  bimodal), get_state 56.8us, adapter "NVIDIA GeForce RTX 5090 Laptop GPU
  (DiscreteGPU) via Vulkan", measured_at 2026-09-21T15:40:07Z.

## GREEN tail (literal, this run)

```
$ python3 .builder_queue/probe_r11_anchor_baseline.py
CPU result@754 = 0x7e expected 0x7e (MATCH) steps=247 ticks=4 wall=1,261us
WGSL result@754 = 0x0 expected 0x7e (DIVERGENT) ticks=0 steps=99 halted=True
LEG wgsl_anchor 11,125 steps/s 89.9 us/rep step x1
VERDICT=PASS (cpu functional OK; wgsl timed leg 99 steps; wgsl functional divergence recorded as baseline datum)
$ python3 .builder_queue/check_regime.py /tmp/r11_probe_out.txt
leg wgsl_anchor: 89.9 us/roundtrip vs floor 98.6 us (0.91x) -> ADMISSIBLE
regime check: PASS (1 legs, floors from 2026-09-21T15:40:07.021271+00:00, NVIDIA GeForce RTX 5090 Laptop GPU (DiscreteGPU) via Vulkan)
```

- CPU (gated substrate): result 0x7E @754 == expectation, argv word intact
  @750 (0x3B00112A), both done flags lit @717 (0b11), 4 ticks serviced
  @732, kernel status word RES_KERNEL_OK. **The agent task completed
  in-guest and was verified host-side.**
- GPU functional: **DIVERGENT** — halts at step 99, result word 0x0, zero
  ticks. Deterministic across 3 runs (also reproduced via `run_wgsl` twice:
  99 steps / mem754=0 / tick732=0 each time).
- Gate suite at HEAD: `tests/test_gh26_resident.py +
  tests/test_gh264c_teleop.py` → **13 passed in 1.11s**.

## RED tail (literal, this run — probe is DISCRIMINATING)

```
$ python3 .builder_queue/probe_r11_anchor_baseline.py --corrupt   # exit 1
CPU result@754 = 0x7e expected 0x7f (MISMATCH) ...
VERDICT=FAIL failures=['cpu:result@754', 'corrupt:expected-failure']
```

Floor linter proven able to fail (this run):

```
$ python3 .builder_queue/check_regime.py --leg demo_sub 100000 100.0 step 1   # exit 1
leg demo_sub: 100.0 us/roundtrip vs floor 243.4 us (0.41x) -> INADMISSIBLE (below floor)
$ python3 .builder_queue/check_regime.py --leg demo_ok 30000 500.0 step 1     # exit 0
leg demo_ok: 500.0 us/roundtrip vs floor 243.4 us (2.05x) -> ADMISSIBLE
```

An intermediate probe version also went INADMISSIBLE for real (84.5us =
0.86x against the freshly-measured 98.6us floor) before the readback
protocol was made protocol-identical to the floor's — the linter rejected
a leg of mine in the same session it accepted the fixed one.

## What this PASS does NOT prove

- **R1.1 is not complete.** This is one deterministic task, host-driven
  through the runner API — not the roadmap's anchor workload (autonomous
  agent fleet, mailbox-supervised, real tasks for hours). R1.2 (≥4 agents),
  R1.3 (preference measurement), and everything P2+ are untouched.
- **Not LLM-driven, not resident-prompted.** The box's daemon is the
  deterministic GH-26.4 hands; Tier C residency (mailbox words, GH-25
  paging, oracle-gated tiles) remains unbuilt. This run is B-state teleop,
  not residency.
- **The WGSL twin cannot run the resident kernel yet.** Measured divergence
  (halts at 99 steps, no ticks, no result; CPU: 247 steps, 4 ticks, result
  delivered) is recorded as the first R1.1 gap datum, NOT root-caused. Per
  standing rule 3, no mechanism story is offered. Until root-caused, any
  in-guest workload on this stack runs on the CPU substrate only.
- **The floor margin is thin (0.91x vs the 0.9x line) and the floor is
  bimodal** (p90 456.2us vs median 98.6us — the run-to-run host-load swing
  is larger than the margin). The LEG datum is admissible as measured; a
  re-run under load could legitimately fail the lint. Per-run probe
  refactor (F1/F2 pattern) is the standing fix if this flaps.
- Test-suite GREEN covers the CPU substrate; no test gates WGSL functional
  correctness for this image (which is just as well — it would be red).

## Speculation (standing rule 3 — labeled, not load-bearing)

The WGSL twin's 99-step halt with zero ticks is *consistent with* the
shader's tick/timer path not firing, but no intervention experiment has
been run (e.g. baking with timer_quantum perturbed, or tracing which PC
the shader halts at). Treat as speculation, not attribution.

## Repro

```
cd ~/projects/zion/projects/visual_audio
python3 .builder_queue/probe_r11_anchor_baseline.py            # exit 0
python3 .builder_queue/probe_r11_anchor_baseline.py --corrupt  # exit 1 (RED)
python3 .builder_queue/check_regime.py /tmp/r11_probe_out.txt  # exit 0
python3 -m pytest tests/test_gh26_resident.py tests/test_gh264c_teleop.py -q
```
