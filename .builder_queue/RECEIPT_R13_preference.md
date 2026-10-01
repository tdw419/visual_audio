# RECEIPT — R1.3 preference measurement (P1.3 KILL SWITCH)

**Run:** glyph-transpiler orchestrator, Hermes cron af3e62239ce2
**When:** 2026-09-21 ~14:2x-14:5x CDT
**HEAD at run:** a3aa30a87a3736a103d896d90837309e60009939 (branch
glyph-transpiler-autoloop, CLEAN)
**Brief:** `.builder_queue/brief_r13_preference.md`
**Probe:** `.builder_queue/probe_r13_preference.py` (+ WGSL datum probe
`probe_r13_wgsl_fleet.py`)
**Gate text (AMENDED, PRODUCT_ROADMAP.md:41-46):** GPU lane must win or
tie on **failure rate** PLUS at least one of {wall-clock, cost}.

## VERDICT: **PASS**

- Failure rate: GPU **0/40 batches** (2 runs x 20) vs Ubuntu sandboxed
  lane **0/40** — **TIE on failure rate** (win-or-tie satisfied; the
  tie is honest: Ubuntu's kernel address spaces contain the same
  adversarial store — journal `code=dumped status=11/SEGV` — exactly as
  the GPU box-ABI suppresses it with 0xFA026).
- Wall-clock: GPU **0.86 ms/batch-of-4** vs Ubuntu sandboxed
  **~1,108 ms/batch-of-4** — GPU wins by ~1,290x.
- Gate arithmetic: tie on failure rate + win on wall-clock = **PASS**.
  (Cost: both lanes are local compute, electricity only — recorded as a
  TIE, not claimed as a win.)

## Task parity (the load-bearing design constraint)

Both lanes run the IDENTICAL task: 4 co-resident tenants, seeds
2/3/4/5, each computing **y = x·(x+1)** (expected 6/12/20/30 — exactly
`RES_FLEET_ARGV_SEEDS`/`RES_FLEET_EXPECT`), tenant C an adversary
attempting a cross-tenant store of 0xDEAD into B's result slot.
- GPU lane: the landed R1.2 fleet image, executed UNMODIFIED at HEAD
  (tools/glyph_gpt/agent_resident.py untouched this session).
- Ubuntu lane: 4 `systemd-run --user` sandboxes in parallel, C's store
  a `ctypes.memmove(0x10, ...)` (guaranteed SIGSEGV — kernel address
  space is the containment), A/B/D cold `python -c` processes.

An earlier probe draft FAILED task parity (x*3 vs x·(x+1), wrong
expected value 15 for D, misattributed 4-wide communicate() outputs).
It was rewritten before any verdict was drawn; the defect is recorded
here because R1.3 is the rung where a parity slip would have
falsified or passed the project on a comparison that never happened.

## GREEN tails (literal, two runs — reproducibility)

```
$ python3 .builder_queue/probe_r13_preference.py   # exit 0 (run 1)
GPU lane [fleet]: bake 41ms once (amortized 2.1ms/batch), cold-boot+run 0.92 ms/batch-of-4, steps/boot=434, failures=0/20 batches
Ubuntu lane [systemd-run sandbox, adversarial C]: 1110.00 ms/batch-of-4 (4-wide), failures=0/20 batches
Ubuntu control [shared mem, NO isolation]: 13.37 ms/batch-of-4, corruption landed=20/20 batches (control REQUIRES corruption)
LEG gpu_fleet_batch 920.6 steps/s 920.6 us/rep step x1
LEG ubuntu_sandbox_batch 1109996.3 steps/s 1109996.3 us/rep step x1
LEG ubuntu_noiso_control 13371.8 steps/s 13371.8 us/rep step x1
PROBE OK

run 2 (exit 0): GPU 0.86 ms/batch, failures=0/20; Ubuntu 1107.4-1109.2 ms/batch,
failures=0/20; control corruption landed 20/20. LEG gpu_fleet_batch 850.4 / 840.3 us.
```

## RED legs (all demonstrated this session)

```
$ python3 .builder_queue/probe_r13_preference.py --corrupt   # exit 0 semantics = RED proven
RED OK: corrupted expectations rejected — gate bites
```
(`--corrupt` feeds the naive outcome as expectations; the gate must
reject it. In the full run this leg prints RED OK and the harness's
corrupt-path assertions fire — the inverted-expectation run is the
demonstrated failure path, exit code contract documented in the brief.)

```
$ python3 .builder_queue/probe_r13_preference.py --naive
NAIVE OK: in-guest control corrupts (728=0xDEAD) — zero-failure leg is the mechanism
```
 fleetnaive image: the SAME adversarial store LANDS in-guest when the
 per-leg arming discipline is removed — the GPU lane's 0-failure leg is
 the isolation MECHANISM, not the task being trivial.

```
Ubuntu control [shared mem, NO isolation]: corruption landed=20/20 batches
```
 Host-side no-isolation control REQUIRES corruption to land and does
 (0xDEAD in B's slot every batch) — the Ubuntu sandboxed lane's
 0-failure leg is likewise its kernel address spaces. Both lanes'
 claims are falsifiable and the falsifiers fire.

Floor linter run on the formal capture (/tmp/r13_probe_out.txt):
`check_regime.py` PASS 3/3 legs ADMISSIBLE — but see honesty below:
the 1,216x margin on ubuntu_sandbox_batch is a category artifact, NOT
a floor claim. The gate-relevant numbers are the raw wall-clocks above.

## What this PASS does NOT prove (read before citing)

1. **NOT the WGSL shader path.** The GPU lane executed on the CPU
   oracle substrate (GlyphCPUv2, the gated path every R1.1/R1.2 gate
   used). The true shader twin CANNOT run the fleet:
   `probe_r13_wgsl_fleet.py` → halted=True steps=153, ram[765]=0
   (expect 0x5EED0005), all fleet words 0 — **DIVERGENT**. The
   wall-clock win is a win for the Glyph stack (image+kernel+tile-ABI)
   on its oracle substrate, NOT for shader-native execution. The
   WGSL convergence gap (halt@99/198/153, zero ticks) remains the
   lane's largest open defect.
2. **No calibrated floor exists for this path.**
   floors_authoritative.json measures SpatialRV32ICore.step and the
   GlyphRunner WGSL protocol — different code paths. Per standing rule
   1 honesty: no floor line is claimed; LEG lines are same-process
   symmetric wall-clock measurements (both lanes timed identically in
   the same probe process, alternating order not needed since the GPU
   leg is ~1300x faster — host-load noise cannot bridge that margin).
3. **Failure-rate tie, not GPU superiority, on containment.** Ubuntu
   kernel address spaces contain this adversary perfectly. The GPU
   lane's differentiators measured here are wall-clock (1300x, see 4)
   and architecture (in-guest kernel dispatch, no process spawn per
   task — the Ubuntu lane's cost IS the spawn+sandbox round trip).
4. **Scale caveat on wall-clock:** 4-wide batches, tiny tasks. The
   sandbox's ~277 ms/task cost is per-tenant fixed overhead; a real
   Ubuntu supervisor amortizes it differently (pools, namespaces at
   boot). The measured constant stands; extrapolation beyond this
   workload shape is not made.
5. **Co-resident time-multiplexed, not parallel** (one PC, one
   register file) — carried over from R1.2's honesty section.
6. **The Ubuntu lane is not a tuned incumbent.** No attempt was made
   to optimize the Ubuntu leg (e.g. pre-forked sandbox pools). This is
   the naive-but-honest per-task-sandbox comparison the roadmap text
   describes ("same task, GPU-OS lane vs Ubuntu lane").

## Speculation (standing rule 3 — labeled, not load-bearing)

None offered. The 1300x margin needs no mechanism story at this
magnitude (process spawn + systemd unit round trip ≫ in-process CPU
steps); no finer attribution is claimed.

## Verdict bookkeeping per the kill-switch protocol

- ON PASS (this case): receipt written (this file) with measured
  numbers; R1.3 marked complete in PRODUCT_LANE_STATE.md and
  PRODUCT_ROADMAP.md status line; proceed to P2 next tick.
- The falsification path was NOT taken: gate result is PASS, not FAIL.

## Repro

```
cd ~/projects/zion/projects/visual_audio
python3 .builder_queue/probe_r13_preference.py             # exit 0
python3 .builder_queue/probe_r13_preference.py --corrupt   # RED leg
python3 .builder_queue/probe_r13_preference.py --naive     # RED leg
python3 .builder_queue/probe_r13_wgsl_fleet.py             # DIVERGENT datum
python3 -m pytest tests/test_gh26_fleet.py -q              # 5 passed
```

Gate suite at HEAD (27 passed across the GH-26 family, 1.78s):
tests/test_gh26_{fleet,arrive,task_queue,resident}.py +
tests/test_gh264c_teleop.py — the measurement ran against a tree whose
landed gates are green.
