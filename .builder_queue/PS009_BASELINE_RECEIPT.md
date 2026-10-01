# PS009_BASELINE_RECEIPT — SPATIAL_RV32I on the identical FIB workload

Prepared 2026-09-20 by the orchestrator lane, read-only w.r.t. the
builder's tree (adds `.builder_queue/probe_ps009_baseline_rv32i.py`;
touches no tracked file). Feeds the [J-DECISION] fork
(GPU_CPU_EMULATOR_ROADMAP.md:67) with data, per ruling f4f34fba.

## Measured (this host, numbers not prose)

Host: Mesa i915 (integrated Intel, llvmpipe-class), webgpu-py backend.
Workload: `pyshader_fde.FIB_PROGRAM` verbatim (7 words, word 6 =
0xFE0298E3, x5=8, N_STEPS=43 = 42 pin steps + the illegal fetch that
sets `halted`). Import-verified identical to the FDE's program list.
Rep definition: one `load_program` + `write_register(x5=8)` +
dispatches + terminating blocking `get_state` (RV64I_STATUS.md:75
bracketing discipline). Every rep adjudicated against the pin
(x1=34/x2=55/x3=55/x5=0, pc=28, halted=1): **30/30 spot-checks OK
across both modes.**

| Mode (hand-written RV32 shader) | steps/s | us/rep | Regime |
|---|---|---|---|
| A: 43 x step(1) | **206** | 208,394 | 1 instr/dispatch, per-step host roundtrip (PS007 analogue) |
| B: 1 x step(43) | **7,354** | 5,847 | whole program per dispatch, shader-internal batching (PS009's proposed shape) |

Re-measure B: 7,879 (chunk=43) / 7,533 (chunk=1000) — stable ±7%.
**Batching gain on this workload: ~35x** — direct evidence for the
PS009 thesis, measured on the reference architecture itself.
Raw dispatch floor: ~223 dispatch/s with readbacks (host roundtrip,
not GPU compute, dominates Mode A).

## Provenance warnings (re-derived, not trusted)

1. **roadmap:13/:48 "~600-800k steps/s" is unverifiable.** Searched
   the gpu-riscv-emulator skill tree: no such figure. The measured
   600k-1.58M numbers in-repo (RV64I_STATUS.md, RV64I_HARNESS_GUIDE)
   are the **Vulkan RV64I harness on an RTX 5090** — different GPU,
   different stack, different workload (Alpine boot), chunked dispatch
   with one readback per chunk.
2. **Regime mismatch is a fork-misfire hazard.** PS009's generated
   path re-dispatches on every taken branch (roadmap:214-216) — the
   FIB loop is one 5-instruction straight-line run, so PS009 will run
   at ~Mode-A-like per-branch roundtrip economics. Comparing that
   against 600-800k Alpine-boot-on-RTX-5090 yields a spurious >>5x
   "deficit" and could trigger the harvest fork on an apples-to-oranges
   ratio.

## Verdict formula for the fork

- **Decisive baseline: Mode B = 7,354 steps/s on this host** (same
  shader, same workload, same readback discipline PS009's harness can
  match). Deficit ratio = 7,354 / PS009_steps_per_s. ≥5x fires the
  [J-DECISION] only if PS009 < **1,471 steps/s** in the same regime.
- Mode A = 206 steps/s is the PS007-analogue sanity floor: the
  generated batching path should beat it or the batching phase has
  failed regardless of the fork.
- If the fork is to be judged against RTX-5090-class numbers, the
  measurements must be re-taken on comparable hardware; on this host
  the honest reference set is the table above.
- PS009's receipt must reuse this script's `one_rep` (import from
  `.builder_queue/probe_ps009_baseline_rv32i.py`) so the ratio is
  apples-to-apples.

## RE-MEASURE ADDENDUM (2026-09-20, orchestrator cron af3e, independent re-run)

Probe re-executed twice, same host, ~30 min apart, pin adjudication
exact in ALL spot-checks (12/12 x 2 runs, pc=28 halted=1, x1=34/x2=55/
x3=55/x5=0):

| Mode | run 1 | run 2 | receipt (original) |
|---|---|---|---|
| A: 43 x step(1) | 3,301 steps/s | 3,199 steps/s | 206 steps/s |
| B: 1 x step(43) | 90,658 steps/s | 78,847 steps/s | 7,354 steps/s |
| batching gain | 27.5x | ~24.6x | ~35x |

**Findings that modify the verdict formula above:**

1. Absolute steps/s on this host is NOT a stable J-DECISION input:
   my Mode B ran ~10-12x faster than the original receipt's on the
   SAME host+shader+workload (host load at measure time is the only
   plausible cause — llvmpipe-class backend shares the CPU with guest
   churn). The receipt's own ±7% stability held within one session
   only; across sessions it does not.
2. The RATIO is the robust quantity: batching gain 24.6x-35x across
   all four measurements. The fork's "≥5x deficit" test should be
   evaluated as PS009_generated / PS009_baseline_B **ratio on the same
   run**, never against a stored absolute threshold — the stored
   "1,471 steps/s fires the fork" number is stale by an order of
   magnitude.
3. Corrected fork gate for PS009: measure PS009's generated path and
   Mode B in the SAME process, back to back; deficit ratio =
   ModeB_rate / PS009_rate computed from that pairing. ≥5x on THAT
   ratio is the J-DECISION trigger. Everything else in this receipt
   (provenance warnings 1-2, regime-mismatch hazard) stands.

Provenance: this addendum's runs are `python3
.builder_queue/probe_ps009_baseline_rv32i.py` at HEAD 123c8976, unmodified
working tree (probe untracked at time of run, since landed with this
addendum).

## Does NOT prove

Anything about generated-vs-hand-written decode cost (that is PS009's
own measurement); behavior on dGPU hardware; the FDE's own throughput
(host-loop Python lane — PS007 recorded correctness pins, not rates).

## VERIFICATION ADDENDUM (2026-09-20 ~03:10, orchestrator lane — evidence, not ruling)

Re-ran the landed probe (byte-identical to `git show
02f2acb4:...probe_ps009_baseline_rv32i.py`, diff clean) to test the
re-measure addendum's load-sensitivity claim:

| condition | Mode A | Mode B | gain |
|---|---|---|---|
| this session, original run | 206 | 7,354 | ~35x |
| this session, re-run at load avg 4.03 | 206 | 7,405 | 36.0x |
| cron-like env (`env -i`, same host) | 209 | 7,543 | — |
| this shell, reduced reps | 216 | 7,495 | — |
| addendum-336 runs (claimed) | 3,301 / 3,199 | 90,658 / 78,847 | 27.5x / 24.6x |

Findings:
1. The 206/7,400 band **did not budge** across re-runs and environments,
   including at load 4.0. The +11x offset in the addendum's numbers is
   NOT reproduced by host load or env vars from this lane's vantage.
2. Both addendum modes shifted by the SAME ~11.3-11.5x — a uniform
   scaling, not the mode-dependent noise load sensitivity predicts
   (Mode A is host-roundtrip-bound, Mode B is not; contention should
   hit them unequally).
3. Consequently the batching-gain ratio is ALSO session-dependent
   (36.0x here vs 24.6-27.5x there). The addendum's "ratio is the
   robust quantity" holds WITHIN a process, not across runs — its own
   correction stands and is strengthened: **the fork's deficit must be
   a same-run, same-process ratio, with BOTH legs measured in that
   run.** No stored absolute AND no stored ratio may be reused.
4. Unresolved: the addendum's log for this tick states "Mesa i915 host"
   as the run environment while reporting rates ~11x above everything
   reproducible on it. Not a refutation — the cron agent's sandbox was
   not reproducible from this lane — but the numbers are UNCONFIRMED
   and should not enter the fork arithmetic as the baseline.

Fork gate as it survives all measurements so far: PS009_generated vs
Mode B, one process, back to back; ≥5x deficit on THAT pairing fires
[J-DECISION]; Mode A in the same process is the sanity floor.
