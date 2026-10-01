> **SUPERSEDED 2026-09-21 by R0_REGIME_RERECEIPT.md**: the 6.15x deficit
> below did not reproduce in two fresh 300-rep paired runs under real
> calibrated floors (1.42x, 0.45x — see R0_REGIME_RERECEIPT.md for the
> three-run table). Verdict lines below are preserved as filed; treat
> "the >=5x fork gate FIRES" as VOID. This file is NOT edited beyond
> this header — audit trail intact.

# PS009b — paired measurement receipt (RULING_ps009 leg 2, MEASURE ONLY)

Revision: glyph-transpiler-autoloop @ 2c2cffbf (PS009a) + this commit
Probe: `.builder_queue/probe_ps009b_paired.py` (this commit)
Environment: this cron lane, RTX 5090 host, load ~uncontrolled (see
baseline receipt's same-process rule — absolutes are context; the
PAIRING is the fork datum).

## The paired numbers (ONE process, back to back, both legs in-run)

| leg | definition | rate | per-rep |
|---|---|---|---|
| A (floor) | hand-written SPATIAL_RV32I, step(1) x43 | 3,513 steps/s | 12,241 us |
| B (denominator) | same core, step(43) x1 | 95,299 steps/s | 451 us |
| GEN (numerator) | GPU-resident generated-body FDE loop (ps009a shader, batch=256), device/pipeline/buffers amortized; per-rep = state upload + dispatches + blocking readbacks | 15,565 steps/s | 2,698 us |
| GEN0 (context) | full `run_fde_gpu` per rep, ALL setup in-loop | 8,765 steps/s | 4,792 us |

**PAIRED DEFICIT ModeB/GEN = 6.15x — the >=5x fork gate FIRES.**
Context: ModeB/ModeA = 28.0x; ModeB/GEN0 = 10.9x.

The [J-DECISION] (GPU_CPU_EMULATOR_ROADMAP.md:67, continue/harvest vs
stop) is **Jericho's** — this receipt produces the fork data only and
does not self-promote past the gate (RULING_ps009: "the builder does
not self-promote past it").

## Rep discipline (apples-to-apples)

- Workload: `pyshader_fde.FIB_PROGRAM`, x5=8. Host legs: 43 steps
  (42 pin steps + the illegal fetch that latches halted, counted).
  GEN legs: 42 executed (the ps009a loop stops AT the imem-OOB fetch,
  pc=7 stop=IMEM_OOB — one-step count-convention difference, stated;
  each leg rated on its own executed count; a 43-vs-42 numerator
  error is +2.4%, an order below the 6.15x signal).
- Verification in-loop: final regs {x1=34, x2=55, x3=55, x5=0}
  checked warm + every reps/5 — pin OK on every check, all legs.
- GEN steady-state excludes one-time device/shader/pipeline creation
  (that amortization IS the architecture's claim); GEN0 kept as the
  as-landed context bound.

## RED-first / probe-shown-able-to-fail

First GEN run went RED by the probe's own in-loop pin check: my probe
bug (initial prefix did not preload x5=8 -> x5 underflow spin, final
regs garbage: `pin MISMATCH {1: (2673165122, 34), ...}`). The probe's
verification demonstrably refuses a wrong-numbers leg. Two further
boundary asserts tightened during bring-up (GEN trace_n 42 vs host 43;
GEN0 steps_executed 42), now pinned and machine-checked.

## What this PASS does NOT prove

- GEN leg is single-invocation (1x1x1 workgroup), sequential inside
  one shader; no parallel lanes.
- Batch=256 on a 7-word program means one dispatch per rep until the
  taken-BNE exit + one IMEM_OOB dispatch; per-rep cost is dominated
  by upload + two dispatch round-trips + one blocking map. Larger
  straight-line workloads amortize differently — this is the FIB
  workload's deficit only.
- No stored absolute from any prior session entered this arithmetic
  (md5-6865bb54 rule upheld): A/B here (3.5k/95k) sit near the
  reporting lane's reproducible band (206-216/~7,400 — B ~13x above
  it in THIS run), another demonstration that absolutes are
  session-bound and only the same-process pairing is the datum.
- GEN0 (as-landed) rebuilds pipeline + shader every rep; its 8.8k
  number is a floor on the as-landed API, not the architecture's rate.
- No performance tuning was attempted on the GEN leg (no padding,
  no subtracking, no persistence hints); 009b measures the seam AS
  LANDED by 009a.

## Fork package for Jericho

Deficit 6.15x >= 5x on the ruling's own pairing -> gate fires.
Per GPU_CPU_EMULATOR_ROADMAP.md:67 and RULING_ps009: continue/harvest
is YOUR call. The probe and this receipt are reproducible:
`python3 .builder_queue/probe_ps009b_paired.py`.
