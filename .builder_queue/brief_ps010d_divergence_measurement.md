# BRIEF PS010d — divergence-cost measurement rung (SKELETON ROUND)

**Skeleton (read FIRST — it is the spec):** `tools/pyshader_measure.py`
@ the commit that carries this brief (NEW file — the PS010c rung-1
precedent, commit 99bd417b, landed brief + skeleton + harness
together). Interfaces are LOCKED. **Authority:** 
GPU_CPU_EMULATOR_ROADMAP.md:233-310 (PS010 non-vacuity: divergence cost
is a MEASURED OUTPUT — wall/cycle for BOTH legs in the receipt, the
ratio at multiple N so the curve is visible; three honest outcomes named
in advance at :270-279) + the PS010b step-4 CORRECTION
(brief_ps010b_divergence_sweep.md: the host round-scheduler proxy is
algebraically scale-invariant, so the verdict is NOT REACHED until a leg
whose numbers can move exists) + the PS010c step-4 receipt
(brief_ps010c_gpu_multihart.md: "the uniform-vs-adversarial wall ratio
is NOT a divergence-cost verdict; the measurement rung prices that with
same-process pairing and floors attached"). RULING_ps009_
fork_cleared_ps010_go.md sets the pattern: measurement claims come AFTER
correctness gates — PS010c proved bit-for-bit parity at all 15 cells;
THIS rung is the pricing.

## Why this rung exists (measured)

PS010b's efficiency was 4dp-identical at N=2 and N=65536 (algebraic
identity, not a measurement). PS010c recorded wall_seconds but its own
brief forbids reading any uniform-vs-adversarial verdict from them
(no pairing, no warmup discipline, informational only). The GPU leg
whose numbers CAN move now exists: `run_multihart_gpu`
(tools/pyshader_multihart.py:270) — one dispatch per ROUND, halted harts
idle in-lane, which is exactly the warp-occupancy cost the roadmap
:246-268 requires pricing. This rung adds the measurement discipline
around it: same-process pairing, warmup floors, REPS medians, and a
ratio curve across the roadmap's named N points (2, 64, 4096, 65536).

## Measurement discipline (the PS009B lesson, carried forward)

The PS009B 6.15x defect was a rate-regime violation: legs timed outside
their device's floor, ratio of two overhead artifacts. This rung's
defenses, LOCKED into the skeleton:
- **Same-process pairing**: at each N, uniform and adversarial cells
  alternate rep-by-rep in one process — drift hits both legs equally.
- **Warmup floor**: one throwaway `run_multihart_gpu` call before any
  timed cell (shader compile + buffer alloc amortized; the PS009B
  "285us per step() vs 4200us floor" artifact class).
- **REPS medians**: walls are per-rep lists; the reported number is the
  median, and it must be RECOMPUTABLE from the recorded raw walls
  (recomputability is a gate pin — a forged median is a pin failure).
- **Determinism clause**: wall-clock varies run to run. The gate pins
  STRUCTURE (parity per cell, recomputability, positivity, presence) —
  NEVER a threshold on the ratio. The ratio curve is DATA for the
  three-named-outcomes verdict (roadmap :270-279), reported in the
  receipt, adjudicated by the curve — not by a pass/fail cut.

## Scope (exclusive write set)

`tools/pyshader_measure.py` + `tests/test_pyshader_measure.py` + this
brief (receipts appended). Everything else is must-not-touch:
`tools/pyshader_multihart.py`, `tools/pyshader_divergence.py`,
`tools/pyshader_wgsl.py`, `tools/pyshader_fde.py` (imported, never
edited); no bare-metal files (BM lane is Qoder's per
BM905_MANUAL_LANE_STATE.md); the roadmap file is read-only. If an
imported interface looks wrong for a step, that is skeleton-sign-off:
file `.builder_queue/REPAIR_PENDING_ps010d_<topic>.md` (measured
conflict + 2-4 options cheapest-first) and pick the next eligible step.

## Reuse, do NOT reimplement

- The N-hart GPU kernel: `tools.pyshader_multihart.run_multihart_gpu`
  (PS010c, parity-proven — its receipts carry bit-for-bit evidence at
  all 15 cells).
- The leg programs + x5 splits: `LOW_PROG`, `DIVERGENT_PROG` from
  `tools.pyshader_divergence` (uniform = LOW_PROG x N, x5=0;
  adversarial = DIVERGENT_PROG x N, x5 = [4]*half + [0]*rest) with the
  analytic step pins (uniform 5/hart, adversarial 2|18) from
  `tools.pyshader_multihart._analytic_steps` and the per-cell parity
  evaluator `_cell_pins` (private helpers of the PS010c gate — reuse
  is the point; do NOT fork a second pin implementation).
- Device discipline: `_cached_device()` is inside run_multihart_gpu
  already; this module never creates a second device.

## Pinned facts (parse/verify, never restate from memory)

- Roadmap-named scale points: N ∈ {2, 64, 4096, 65536} (the ratio
  curve, not one point — roadmap :271-274).
- Steps per hart (PS010c probe pins): uniform LOW = 5; adversarial
  DIVERGENT taken(x5=4) = 2, not-taken(x5=0) = 18. The N=65536
  adversarial cell runs ≈ 65536 harts x 18 rounds of full-buffer
  readback — minutes-scale is NOT expected (PS010c saw 2.6s for this
  cell), but the gate must tolerate slow devices by SKIPPING the
  full-scale leg on device-acquisition failure (smoke-lane rule for
  the largest N; N=2/64/4096 gate).
- REPS = 3 paired reps per (leg, N); median of the 3.

## Step table (one row per builder run)

| # | Populate | New gate (test name) | Gate clause (RED first, then GREEN) |
|---|---|---|---|
| 1 | `measure_cell` | `test_ps010d_measure_cell_small_n` | measure_cell('uniform', 2) and measure_cell('adversarial', 2): dict with leg/n/wall_seconds (>0)/useful/slots/steps_ok=True/pin_failures=[]/stops=[]; useful == 5*2 resp. (2+18)*1+... == analytic via _analytic_steps; slots == n*rounds. RED evidence: NotImplementedError tail from the stub. |
| 2 | `wall_ratio` + `_pair_medians` | `test_ps010d_pairing_medians_recomputable` | Host-pure: forged cell lists -> _pair_medians returns per-leg medians EXACTLY recomputable (statistics.median), wall_ratio == adv_median/uni_median; empty or zero-wall input raises. One real paired N=2 run: ratio finite and >0. RED evidence: NotImplementedError tail. |
| 3 | full-scale recorded leg | `test_ps010d_full_scale_recorded` | gate-scale run at N ∈ {4096, 65536} RECORDED in a receipt dict (walls, ratio) — pytest.skip('wgpu device acquisition failed') ONLY on the RuntimeError whose message starts with that string (PS011 step-2 smoke-lane discipline); when present: cells recorded, ratio recomputable from raw walls, NO threshold asserted on the ratio (determinism clause). RED evidence: NotImplementedError tail. |
| 4 | `gate_divergence_cost` — THE rung gate | `test_ps010d_gate_divergence_cost` | Receipt dict (ok flag, does NOT raise on pin failure): warmup executed before first timed cell (measured: warmup call visible in receipt); per N ∈ MEASURE_NS both legs paired rep-by-rep; pins (a) parity/steps_ok at every cell, (b) wall_median recomputable from walls at every cell, (c) ratios reported per N ("numbers, not prose"), (d) all walls > 0. NON-VACUITY REQUIRED: a mutant measure_cell forging wall_median inconsistent with its walls list run through the SAME gate path must produce ok=False with the recomputability pin naming the cell. |

## Hard constraints

- Additive only. Do not edit the skeleton signatures, docstring pins,
  or the discipline constants (MEASURE_NS, REPS). 
- Keep live guards live: stub-raise tests are guards; REPLACE each with
  its behavioral gate — never delete silently, never weaken to pass.
- Stdlib + existing toolchain only; no new dependencies. wgpu touches
  ONLY via run_multihart_gpu (which owns _cached_device()).
- The gate adjudicates against STRUCTURE + the PS010c analytic pins,
  never engine-vs-engine wall comparison alone and never a hardware
  threshold; ratio values are recorded DATA.
- The verdict language in the final receipt MUST match roadmap
  :270-279's three named outcomes (tolerable / needs scheduling
  discipline / bad-at-low-N-tolerable-at-scale) — the curve decides,
  and the receipt states which outcome the curve indicates WITHOUT
  converting the measurement into a pass/fail gate.

## Receipt discipline

- RED first (save the literal output tail), then GREEN; paste both
  tails in the commit message.
- After every step, structural gate green:
  `python3 -m pytest tests/test_pyshader_measure.py -q` -> exit 0.
  PS-chain suite green:
  `python3 -m pytest tests/test_pyshader_hart.py tests/test_pyshader_ctl.py tests/test_pyshader_fde.py tests/test_pyshader_divergence.py -q`
  -> exit 0.
- Commit message ends with: `next: PS010d step N+1 (<row name>)`.

## Definition of done

Steps 1..4 each with RED->GREEN evidence; structural harness green;
PS-chain suite green; a receipt (appended as `## PS010d receipt`)
stating what is proven and what is NOT — including: the ratio is a
HOST-DRIVEN round-scheduler GPU measurement (one dispatch per ROUND,
full-buffer readback per round — the readback is part of BOTH legs'
cost and inflates the denominator uniformly), NOT a profiling-counter
warp-execution-efficiency number (roadmap :253-255's IPC/spill counters
remain unbuilt); the adversarial leg is a deterministic x5 PRELOAD
split, not intra-loop data-dependent divergence; and the three-outcome
verdict is INDICATED by the curve, with the curve attached as numbers.

## What this round does NOT claim

- No profiling-counter metrics (GPU hardware counters are a later rung).
- No warp-coherent scheduling implementation (the contingency if the
  curve comes back bad — a later rung, roadmap :258-260).
- No PS012 work: [J-DECISION] rows are RESERVED to Jericho. This rung
  produces the LAST missing data input (the divergence curve) to
  PS010's closure; PS010's final mark and any PS012 branch-point
  reading remain with Jericho.
- No change to PS010c's parity claims — this rung CONSUMES
  run_multihart_gpu as-is.

## PS010d receipt — rung-1 skeleton + step 1 (measure_cell)

Commits: 2e8818df (brief + locked skeleton + 5-leg structural harness;
check_brief.py PASS exit 0) + 7c20ad3d (step 1 populate, RED->GREEN).
Revisions: glyph-transpiler-autoloop @ 16ba4f31+2e8818df, then
2e8818df+7c20ad3d (sibling lane advanced HEAD to 6ea6407e mid-run; my
two files verified clean against it).

Scope honored: .builder_queue/brief_ps010d_divergence_measurement.md +
tools/pyshader_measure.py + tests/test_pyshader_measure.py ONLY. The
tree's other dirty files (pxc1 frames, guest context, bare_metal_poc)
are sibling-lane churn — untouched throughout.

Step-1 change: measure_cell (tools/pyshader_measure.py:100-127) — REPS
timed run_multihart_gpu calls per (leg, N); every rep adjudicated
against the PS010c pins (_cell_pins parity + rounds pin 5/18) BEFORE
its wall counts — a parity failure is a measurement failure, never a
number (PS009B lesson: the filed 6.15x was un-adjudicated overhead).
wall_median = statistics.median(walls), recomputable by construction;
receipt carries walls raw, useful/slots/rounds, steps_ok,
pin_failures, stops. reps<=0 and unknown leg refuse loudly. The
stub-raise guard test_ps010d_measure_cell_small_n was REPLACED (not
deleted) by the behavioral gate (removal noted in the test file —
audit trail kept).

RED tail (literal, skeleton stub restored at 2e8818df, behavioral test
in place): `NotImplementedError: PS010d step 1: measure_cell is a
stub` — `1 failed in 0.09s` (exit 1).

GREEN tails (literal): `5 passed in 1.39s`
(tests/test_pyshader_measure.py) and `56 passed in 11.54s` (PS-chain
suite: fde + ctl + hart + divergence + multihart).

**What this PASS does NOT prove:** no full-scale leg (steps 3-4), no
ratio/curve yet (step 2), no N beyond 2 measured, no divergence-cost
verdict of any kind — that is gate_divergence_cost's deliverable
(step 4) with the three-named-outcomes language (roadmap :270-279).
Walls at N=2 are warm-device numbers only.

Incidents (recovery protocol, no human escalation needed): (1) a
`git stash` for a RED re-run swept in sibling churn and the pop
aborted on sibling files — recovered via `git checkout stash@{0} --
<my two files>`, stash entry then dropped; LESSON for future ticks:
never `git stash` in this shared tree; use `git show HEAD:<file>` +
restore, as done for the RED leg. (2) one index.lock contention with
the Qoder sibling's commit — waited, no lock removed.

## PS010d receipt — step 2 (wall_ratio + _pair_medians)

Commits: 5ab8b240 (step 2 populate, RED->GREEN) at revision
glyph-transpiler-autoloop @ 6377536d parent. Scope held to the
exclusive write set: `tools/pyshader_measure.py` (bodies only,
signatures + docstring pins + constants untouched) +
`tests/test_pyshader_measure.py` (step-2 stub-raise guard REPLACED
by the behavioral gate, replacement noted in-file — audit trail) +
this receipt.

RED tail (literal, stub in place, behavioral gate run):
  NotImplementedError: PS010d step 2: wall_ratio is a stub
  tools/pyshader_measure.py:151
  FAILED tests/test_pyshader_measure.py::test_ps010d_pairing_medians_recomputable
  1 failed in 0.11s

GREEN tails (literal):
  structural gate: `5 passed in 1.43s`
    (python3 -m pytest tests/test_pyshader_measure.py -q, exit 0)
  PS-chain suite: `48 passed in 5.38s`
    (hart/ctl/fde/divergence, exit 0)

Gate clause delivered: forged host-pure cell lists -> per-leg medians
EXACTLY recomputable via statistics.median over the RAW walls lists;
ratio == adv_median/uni_median at both forged Ns (4/2 and 5/20);
ValueError refusals proven for empty, length-mismatch, n-mismatch,
and non-positive wall median; one REAL paired N=2 run through
measure_cell both legs -> ratio finite and > 0.

What this PASS does NOT prove: no full-scale leg (steps 3-4 pending);
the ratio numbers here are plumbing checks on forged + N=2 data, NOT
the divergence-cost curve; no verdict language yet — that is step 4's
receipt against roadmap :270-279. gate_divergence_cost remains a
stub-raise guard, still live.

next: PS010d step 3 (full-scale recorded leg)

next: PS010d step 2 (wall_ratio + _pair_medians)

## PS010d receipt — step 3 (full-scale recorded leg)

Commits: 0d56a414 (step 3 populate, behavioral gate replacing the
stub-raise guard) at revision glyph-transpiler-autoloop @ 5ab8b240
parent. Scope held to the exclusive write set:
`tools/pyshader_measure.py` (additive `full_scale_recorded` helper
ONLY — signatures, docstring pins, and MEASURE_NS/REPS untouched;
step-4 stub-raise guard stays live) + `tests/test_pyshader_measure.py`
(guard replaced, never deleted; import extended).

RED (per contract: the step-3 stub-raise guard against the live stub
was the only evidence before this run — `1 passed in 0.09s` because it
asserted the NotImplementedError; the behavioral gate did not exist):

GREEN tails (literal):
  python3 -m pytest tests/test_pyshader_measure.py::test_ps010d_full_scale_recorded -q
  `1 passed in 8.87s` (exit 0, real GPU)
  structural: `5 passed in 9.01s`; PS-chain: `48 passed in 5.20s`

Recorded curve (REPS=3, this machine's device, 2026-09-20 — DATA,
never a threshold):
  N=  4096  uni_med=0.0974s  adv_med=0.1442s  ratio=1.481
  N= 65536  uni_med=1.3016s  adv_med=2.3010s  ratio=1.768
Ratios recomputed from raw walls inside the gate (exact ==, per the
recomputability pin). Curve reading is STEP 4's job (three named
outcomes, roadmap :270-279) — no verdict language here beyond noting
the ratio MOVES with N, which is precisely what PS010b's algebraic
proxy could never do.

What the PASS does NOT prove: no ratio threshold asserted anywhere;
the pytest.skip lane (device acquisition) was NOT exercised on this
machine (device present — `_cached_device()` returned live) — its
message-prefix contract mirrors pyshader_golden.py:172 / PS011
step-2 discipline, untested here; walls remain host-driven
round-scheduler numbers (one dispatch per ROUND, full-buffer readback
in BOTH legs), not profiling-counter warp-execution efficiency; the
adversarial leg is the deterministic x5 PRELOAD split.

Parallel-lane note: `tools/bare_metal_poc/pristine_reverify.sh` was
observed modified in the shared worktree (Qoder lane's file, per
BM905_MANUAL_LANE_STATE.md) — untouched by this run; only the two
in-scope files were staged and committed.

Incident (recovery protocol): the first behavioral-gate run hit a
Pyright undefined-name on the new import — fixed by extending the
existing import list, no scope impact.

next: PS010d step 4 (gate_divergence_cost — THE rung gate)

## PS010d receipt — step 4 (gate_divergence_cost — THE rung gate)

Revision glyph-transpiler-autoloop @ 735c8b92 parent. Scope held to the
exclusive write set: `tools/pyshader_measure.py` (additive body for
`gate_divergence_cost` ONLY — locked signature
`(measure_ns=MEASURE_NS, reps=REPS, _measure_cell=measure_cell)`
untouched; discipline constants untouched; MEASURE_NS default run
unchanged) + `tests/test_pyshader_measure.py` (step-4 stub-raise guard
REPLACED by the behavioral gate; never deleted).

RED (literal tail, behavioral gate against the live stub):
  NotImplementedError: PS010d step 4: gate_divergence_cost is a stub
  `1 failed in 0.09s`

GREEN tails (literal):
  python3 -m pytest tests/test_pyshader_measure.py::test_ps010d_gate_divergence_cost -q
  `1 passed in 1.22s` (exit 0, real GPU, mutant + tiny-N live legs)
  structural: `5 passed in 9.05s`; PS-chain: `48 passed in 5.30s`

Gate structure proven: warmup executed before the first timed cell and
recorded (warmup_wall > 0, measured); per N both legs back-to-back in
one process (pairing discipline); pins (a) parity/steps_ok per cell,
(b) wall_median recomputable from its own walls list — pin NAMES the
cell, (c) ratios per N via _pair_medians, (d) all walls > 0. Receipt
never raises on pin failure (ok flag). NON-VACUITY: a mutant
measure_cell (forged wall_median = median*1.5 + 7.0) through the SAME
gate path via the _measure_cell seam yields ok=False with
"wall_median recompute failed at uniform/n=2" naming the forged cell —
the gate can fail and did (RED-adjacent leg, first assertion in the
test).

Measured curve (REPS=3, this machine's device, 2026-09-20 — DATA,
never a threshold; full MEASURE_NS run through the populated gate):
  N=     2  uni=0.0122s  adv=0.0218s  ratio=1.780
  N=    64  uni=0.0107s  adv=0.0268s  ratio=2.498
  N=  4096  uni=0.0931s  adv=0.1639s  ratio=1.760
  N= 65536  uni=1.3061s  adv=2.2402s  ratio=1.715
warmup_wall=0.7543s; ok=True, pin_failures=[].
Verdict field: "tolerable" (endpoint rule: ratios[-1]=1.715 <= 2.0,
i.e. NOT needs_scheduling_discipline). Honest curve reading: the ratio PEAKS at
N=64 (2.498 — warp-fill artifact, the roadmap's predicted low-N
phenomenon) and DECAYS toward ~1.72 at scale — divergence cost at
65536 harts is ~72% overhead vs the uniform leg, and the curve is
flat from 4096 to 65536. Whether ~1.7x is "tolerable" for GeoASM at
agent scale is Jericho's [J-DECISION] call — this rung supplies the
curve, not the verdict-ruling (roadmap :270-279 names the outcomes;
PS012 is reserved).

What the PASS does NOT prove: host-driven round-scheduler numbers (one
dispatch per ROUND, full-buffer readback per round, in BOTH legs);
readback cost symmetric across legs but present; deterministic x5
PRELOAD split, not intra-loop data-dependent divergence; NO profiling
counters (warp-execution-efficiency / IPC / spills remain unbuilt);
the pytest.skip device-acquisition lane was NOT exercised live
(message-prefix contract only); the verdict heuristic reads endpoints
only — the N=64 peak (2.498) is DATA a human reads from the curve
above, not something the endpoint rule summarizes; single-run wall
numbers (medians of 3 paired reps, one process, one machine).

Parallel-lane note: Qoder bare-metal files (pristine_reverify.sh, PXC1
frames, guest_state.json) were dirty in the shared worktree throughout
this run — untouched; only the two in-scope files staged and committed.

next: PS010d COMPLETE (steps 1-4 green) — final receipt above; PS-chain
supply next is PS011 (golden-trace cross-validation) per roadmap, and
[J-DECISION] rows remain Jericho's.

## PS010d receipt — DATED CORRECTION 2026-09-20 (RULING_ps012 clause 1)

Not a silent edit of the step-4 receipt above — a dated correction, per
the ruling's "receipts updated by dated correction rather than silent
edit" requirement.

**Superseded:** the step-4 receipt's verdict paragraph ("Verdict field:
'tolerable' (endpoint rule: ratios[-1]=1.715 <= 2.0 ...)") — the
endpoint reading rule it used is retired. The recorded curve numbers
(1.780 / 2.498 / 1.760 / 1.715) STAND; only the reading rule changed.

**Correction in force:** RULING_ps012 (.builder_queue/RULING_ps012.md,
landed 36571703) clause 1 required the verdict to be derived from the
whole curve. Landed as 4972ccee: `curve_verdict()` in
tools/pyshader_measure.py (max-over-N and where it occurs, peak-to-tail
relation, spread); `gate_divergence_cost`'s endpoint rule REPLACED (not
deleted) by `curve_verdict`; the receipt now carries `verdict_basis`
(peak_n / peak_ratio / tail_n / tail_ratio / decayed_to_tail / spread),
recomputable from ratios.per_n. Guard replaced, not deleted: the
behavioral test for the new rule is
tests/test_pyshader_measure.py::test_ps012_clause1_curve_verdict_reads_whole_curve
(forged 9.5x mid-range spike must NOT read like the flat curve and must
name the peak cell; the recorded curve reads
bad_at_low_n_tolerable_at_scale, peak_n=64, decayed_to_tail=True).
Clause 1.4 wording for any closure record: the divergence result is
"1.7–2.5x across four orders of magnitude in N, peaking at N=64 and
decaying toward ~1.72x at 65536" — NOT a bare "tolerable".

GREEN tail for the corrected rule (literal, this correction's landing
session): `python3 -m pytest tests/test_pyshader_measure.py -q` →
`6 passed in 8.87s`; live re-run of gate_divergence_cost on the same
device: ok=True, pin_failures=[], verdict=
bad_at_low_n_tolerable_at_scale, verdict_basis peak_ratio 2.76 @ N=2,
tail_ratio 1.70 @ N=65536, decayed_to_tail=True (single-run re-measure;
the pinned receipt numbers above remain the receipt of record).

What this correction does NOT prove: the step-4 honest-boundary list
above is unchanged (no profiling counters, host-driven round scheduler,
single-process single-machine walls); the live re-measure naturally
differs run-to-run and was not used to update any pinned number.

next: PS012 clause 2 (closure record) landed → lane idle-on-record per
RULING_ps012 clause 2.3 — stop and say so.
