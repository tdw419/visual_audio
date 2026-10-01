# BRIEF PS010b — Divergence-cost sweep: the measured verdict leg (SKELETON ROUND)

**Skeleton (read FIRST — it is the spec):** `tools/pyshader_divergence.py`
@ the commit that carries this brief (NEW file — the rung-1 precedent,
commit 30a7007c, landed brief + skeleton + harness together; the
orchestrator pre-verified every pin below through the existing PS008/PS007
machinery, see the probe receipt at the bottom). Interfaces are LOCKED.
**Authority:** `.builder_queue/RULING_ps009_fork_cleared_ps010_go.md`
(the PS010 go) + `GPU_CPU_EMULATOR_ROADMAP.md:233-310` (the non-vacuity
requirement this rung implements — divergence cost is a MEASURED OUTPUT,
reported as a sweep at realistic scale, "numbers in the receipt, not
prose").

## Why this rung exists (measured)

PS010 steps 1-4 (brief_ps010_two_hart_mailbox.md, ALL LANDED @ 42c63cff)
closed the two-hart CORRECTNESS gate and explicitly deferred the
divergence-cost leg: "remaining PS010 scope (N-hart divergence-cost
sweep, GPU leg) is per GPU_CPU_EMULATOR_ROADMAP.md :246-268 and needs a
new brief." This is that brief. It is HOST-side only (Path B's GPU SIMD
lane is a later rung; roadmap :284-292 scopes divergence cost to Path B
ONLY — this rung measures the HOST round-scheduler's efficiency decay,
which is the sequential-vs-parallel model the GPU leg must later beat).

## Scope (exclusive write set)

**Files in scope (only these may change):**
- `tools/pyshader_divergence.py` — NEW file; populate stub bodies ONLY
  (signatures, docstring pins, program texts, and all constants LOCKED
  from the moment this brief lands).
- `tests/test_pyshader_divergence.py` — NEW file; append behavioral
  tests; replace stub-raise guards with the behavioral gate named in
  each row (replace, never delete, per the contract).
- `.builder_queue/brief_ps010b_divergence_sweep.md` — receipt section
  only.
**Must-not-touch this round:** `tools/pyshader_hart.py`,
`tools/pyshader_fde.py`, `tools/pyshader_ctl.py`,
`tools/pyshader_rvexec.py`, `tools/pyshader_rvdecode.py`,
`tools/pyshader_wgsl.py`, `tools/pyshader_compiler.py`,
`tools/rv32i_asm.py`, ALL `tools/bare_metal_poc/**` +
`systems/virtio_pixel_rs/**` (Qoder lane). If a locked signature looks
wrong for a step: file `.builder_queue/REPAIR_PENDING_ps010b_<topic>.md`
(2-4 options, cheapest-first, marked skeleton-sign-off), then HOLD and
stop this run. Decisions return as `RULING_ps010b_<topic>.md`.

## Pinned facts (probe-verified 2026-09-20 through execute_ctl/execute_one;
do not restate from memory — the test re-derives them from assemble())

Word images (assembler ground truth, little-endian u32):
- `LOW_PROG` (4 words): `0x00200093, 0xFFF08093, 0xFE009EE3, 0x00100073`
  — addi x1,x0,2 / loop: addi x1,x1,-1 / bne x1,x0,-4 / ebreak.
  Transitions: 5 (2 ADDI + 3 loop body… measured: 5).
- `MIX_PROG_SHORT` (2 words): `0x00000093, 0x00100073` — transitions: 1
  (ADDI only; EBREAK halts UNCOUNTED per the PS008 convention).
- `MIX_PROG_LONG` (4 words): `0x00800093, 0xFFF08093, 0xFE009EE3,
  0x00100073` — transitions: 17.
- `DIVERGENT_PROG` (5 words): `0x00029663, 0x00800093, 0xFFF08093,
  0xFE104EE3, 0x00100073` — bne x5,x0,12 / addi x1,x0,8 /
  spin: addi x1,x1,-1 / blt x0,x1,-4 / ebreak. With x5=4 (taken):
  2 transitions. With x5=0 (not-taken): 18 transitions.
  (Spin counts down with BLT-signed; a BNE-down-to-zero spins ~2^32
  because the u32 wraps past 0 — probe-measured, hence BLT.)

Sync model: identical to run_two_hart sync="double" semantics, N harts:
per-hart dmem views (here dmem is write-free; harts are independent, so
the round scheduler is the thing under test, not memory ordering — the
mailbox brief already adjudicated that). Metric (roadmap :250-252 names
it): **efficiency = useful_transitions / live_hart_slots**, where a
live_hart_slot = one round in which a hart was still live (halted harts
still occupy lanes in real warp hardware — that is exactly the cost
being measured). Report per (N, mix): rounds, useful, slots,
efficiency, and per-hart transition counts for the sampled harts.

## Gate commands (structural, must stay green every step)

```
python3 -m pytest tests/test_pyshader_divergence.py -q   # exit 0
python3 -m pytest tests/test_pyshader_hart.py tests/test_pyshader_ctl.py tests/test_pyshader_fde.py -q   # exit 0
```

## Step table (one row per builder run; run the LOWEST row without GREEN
evidence recorded in the receipt section below)

| # | Populate | New gate (test name) | Gate clause |
|---|---|---|---|
| 1 | `sweep` — N-hart round scheduler, per-hart programs from a list | `test_ps010b_sweep_uniform_no_divergence` | All N=8 harts run LOW_PROG: rounds==5, useful==8*5=40, slots==8*5=40, efficiency==1.0. Input program list NOT mutated; harts are independent (per-hart states, no shared dmem writes). RED evidence: NotImplementedError tail from the stub. |
| 2 | Static population-mix divergence (low-divergence vs mixed) | `test_ps010b_static_mix_efficiency_decays` | n=8: all-MIX_LONG → efficiency 1.0 (uniform); half SHORT(1)/half LONG(17) → rounds==17, useful==4*1+4*17=72, slots==4*1+4*17… computed from the round scheduler: SHORT harts halt in round 1 and still occupy slots for the remaining 16 rounds — efficiency must be strictly LESS than 1.0 and equal to 72/(8*17)=0.5294 (4dp). Assert the exact number: the ratio IS the deliverable (roadmap: numbers, not prose). RED first on the stub. |
| 3 | Mid-run register divergence (the adversarial leg) | `test_ps010b_adversarial_split_rounds_expose_divergence` | n=8, all harts run DIVERGENT_PROG, per-hart x5 init: first 4 harts x5=4 (2 transitions), last 4 x5=0 (18 transitions). Assert: rounds==18, both sub-populations' per-hart transition counts present in the receipt (sampled harts 0 and 7 == 2 and 18), efficiency == (4*2+4*18)/(8*18) = 80/144 ≈ 0.5556 (4dp). This is the roadmap's "half take one branch, half the other" leg, built on a REGISTER split (same program text, mid-run divergence — the honest worst case), not a static mix. RED first on the stub. |
| 4 | THE roadmap gate: `gate_divergence` — sweep + curve in the receipt | `test_ps010b_gate_divergence_curve` | gate_divergence() returns a receipt dict (ok flag, does NOT raise on mismatch): the sweep at N ∈ {2, 8, 64, 4096} × mix ∈ {uniform, half-mixed, adversarial} — 12 cells, each with rounds/useful/slots/efficiency, PLUS the wall-clock seconds per cell (time.perf_counter around the sweep; reported, NOT gated on — wall-clock is machine-dependent, the efficiency ratios are not). Adjudication pins: (a) uniform cells efficiency==1.0 at every N; (b) adversarial efficiency at N=8 equals the row-3 pin (4dp); (c) the decay is MONOTONE: efficiency(adversarial) < efficiency(uniform) at every N; (d) N=65536 adversarial cell included and completes (the roadmap :275-279 realistic-scale demand) — assert it RAN and report its efficiency; do not assert a value for it in the gate (host scheduler ≠ warp hardware; the curve is the deliverable). Receipt states what PASS does NOT prove: no GPU leg, host-side sequential scheduler only, wall-clock informational. RED first on the stub; non-vacuity: a mutation probe that makes sweep() report slots==useful (efficiency hardcoded 1.0) must FAIL row 2's exact-number assert. |

## Hard constraints

- Additive only; never weaken a live guard to make a step pass.
- No GPU legs this round (host correctness first — the PS lane's own
  order). This rung measures the HOST round scheduler; its numbers are
  the sequential baseline the future GPU-SIMD leg must beat or match.
- One gate-able step = one run = one commit. STOP after the row even if
  early. Receipt section below updated in the same commit.
- Stdlib + existing toolchain only; no new dependencies. Reuse PS005
  decode_ref, PS007 execute_one/fetch, PS008 execute_ctl — no second
  decoder/executor. Program words come from assemble(), never
  hand-encoding (step-4 PS010 lesson, tools/pyshader_hart.py:286-289).
- Budget discipline: every sweep takes max_rounds (default 64; the
  N=65536 cell may pass max_rounds=64 explicitly) and a RuntimeError
  naming the budget if harts are still live at exhaustion — never a
  silent partial result (step-3 PS010 lesson).

## Receipt section (append per-row GREEN evidence: commit + gate tail)

## PS010b step 1 — GREEN (2026-09-20)

- RED (literal tail): `NotImplementedError: PS010b step 1: sweep is a
  stub (skeleton round — see .builder_queue/brief_ps010b_divergence_sweep.md
  step 1)` — raised by the pre-edit skeleton at the locked stub.
- GREEN: `python3 -m pytest tests/test_pyshader_divergence.py -q` →
  `7 passed in 0.12s`; structural harness
  `python3 -m pytest tests/test_pyshader_hart.py tests/test_pyshader_ctl.py
  tests/test_pyshader_fde.py -q` → `38 passed in 1.45s`, exit 0.
- Row-1 pin verified by direct call: rounds=5, useful=40, slots=40,
  efficiency=1.0, sampled_steps=[5,5]; input program list not mutated.
- Non-vacuity beyond the stub replacement: the budget leg
  (`test_ps010b_sweep_budget_loud`) drives an in-bounds JAL-to-self spin
  and requires the loud RuntimeError naming the budget.
- Accounting note (builder-verified, no interface change): the brief's
  step-2 arithmetic ("SHORT harts halt in round 1 and still occupy slots
  for the remaining 16 rounds"; efficiency 72/(8*17)) fixes slots ==
  n * rounds with rounds == max per-hart COUNTED transitions; EBREAK
  consumes an extra round but is UNCOUNTED (PS008) and contributes no
  slot. `sweep` implements exactly that: rounds=max(steps),
  slots=n*rounds. Row 1's numbers are identical under either reading;
  rows 2-3 will machine-check the mixed accounting.
- What this PASS does NOT prove: no mixed/adversarial population yet
  (rows 2-3), `gate_divergence` still a stub (step 4), no GPU leg, no
  N>8 sweep exercised, wall-clock informational only.

## PS010b receipt — orchestrator pre-lock probe (2026-09-20, no commit: probe scratch)

Before locking the pins above, the orchestrator verified them through
the LIVE PS005/PS007/PS008 machinery (`.builder_queue/probe_ps010b_pins.py`,
untracked scratch, run at the pre-brief tree): LOW=5, MIX_SHORT=1,
MIX_LONG=17, DIVERGENT taken(x5=4)=2 / not-taken(x5=0)=18 transitions —
all transition counts in the pins above are measured, not hand-computed.
Two pin defects were caught and fixed BEFORE locking (the lane's pattern
of hand-computed pins being wrong continues): (1) the original DIVERGENT
spin used `bne x1,x0,-4` counting down — the u32 wrap means it spins
~2^32 and never halts (probe-measured hang at 10k cap); fixed to
`blt x0,x1,-4` (signed) — halts at exactly 18; (2) the first probe
under-counted by tallying only ctl transitions (ALU steps never
incremented the counter) — fixed, counts re-measured. Word pins in this
brief are the assembler's ground-truth output at revision 42c63cff.

What this probe does NOT prove: the step-table's efficiency arithmetic
(slots accounting) is specified but not yet machine-checked — that is
step 1's and step 2's job; nothing here exercised the N-hart scheduler
itself (no sweep code exists yet).

## PS010b step 2 — GREEN (2026-09-20, commit c80891cf)

- RED (non-vacuity; `sweep` was already populated at step 1, so the
  RED leg is the brief-mandated mutation probe — a sweep mutant with
  slots:=useful, efficiency hardcoded 1.0, must FAIL row 2's gate):
  literal tail `NON-VACUITY OK: mutant REJECTED by the exact-number
  assert (AssertionError)` (probe at /tmp, untracked scratch, exit 1
  when the mutant passes).
- GREEN: `python3 -m pytest tests/test_pyshader_divergence.py -q` →
  `8 passed in 0.08s`; structural harness
  `python3 -m pytest tests/test_pyshader_hart.py tests/test_pyshader_ctl.py
  tests/test_pyshader_fde.py tests/test_pyshader_divergence.py -q` →
  `46 passed in 1.71s`, exit 0.
- Row-2 pins machine-checked: uniform 8×MIX_LONG rounds=17, useful=136,
  slots=136, efficiency 1.0; static mix 4×SHORT+4×LONG rounds=17,
  useful=72, slots=136, efficiency round(...,4)==0.5294, sampled_steps
  == [1, 17], input program list not mutated. The brief's step-2
  arithmetic (slots == n*rounds with EBREAK uncounted) is now
  machine-checked, closing the step-1 accounting note.
- What this PASS does NOT prove: no mid-run register divergence (row 3
  adversarial leg), `gate_divergence` still a stub (step 4), no GPU
  leg, no N>8 sweep exercised, wall-clock informational only.

## PS010b step 3 — GREEN (2026-09-20)

- RED (non-vacuity; `sweep` + `x5_inits` were already populated at step 1,
  so the RED leg is the brief-mandated mutation probe — a sweep mutant
  with slots:=useful, efficiency hardcoded 1.0, must FAIL row 3's gate):
  literal tail `NON-VACUITY OK: mutant REJECTED by the exact-number
  assert (AssertionError at tests/test_pyshader_divergence.py:124)`
  (probe at /tmp, untracked scratch, exits 1 if the mutant passes).
- GREEN: `python3 -m pytest tests/test_pyshader_divergence.py -q` →
  `9 passed in 0.07s`; structural harness
  `python3 -m pytest tests/test_pyshader_hart.py tests/test_pyshader_ctl.py
  tests/test_pyshader_fde.py tests/test_pyshader_divergence.py -q` →
  `47 passed in 1.41s`, exit 0.
- Row-3 pins machine-checked: adversarial 8×DIVERGENT_PROG, x5 inits
  [4,4,4,4,0,0,0,0] — rounds=18 (the not-taken harts set the makespan),
  useful=4*2+4*18=80, slots=8*18=144, efficiency round(...,4)==0.5556,
  sampled_steps==[2, 18] (harts 0 and 7 are the taken/not-taken
  representatives), input program list NOT mutated. Same program text
  on every hart — the split is mid-run REGISTER divergence only, the
  honest worst case the roadmap names.
- What this PASS does NOT prove: `gate_divergence` still a stub (step 4),
  no GPU leg, no N>8 sweep exercised, wall-clock informational only, and
  the x5 split here is a PRELOAD (deterministic split point); intra-loop
  data-dependent divergence shape is approximated by the static mix
  (step 2), not separately measured.

## PS010b step 4 — GREEN (2026-09-20)

- RED (literal tail, stub at tools/pyshader_divergence.py:230):
  `NotImplementedError: PS010b step 4: gate_divergence is a stub
  (skeleton round — see .builder_queue/brief_ps010b_divergence_sweep.md
  step 4)` — 1 failed in 0.13s
  (tests/test_pyshader_divergence.py::TestStep4GateDivergence).
- GREEN: `python3 -m pytest tests/test_pyshader_divergence.py -q` →
  `10 passed in 4.26s`, exit 0; structural harness
  `python3 -m pytest tests/test_pyshader_hart.py tests/test_pyshader_ctl.py
  tests/test_pyshader_fde.py tests/test_pyshader_divergence.py -q` →
  `48 passed in 6.19s`, exit 0. `git status` shows only the brief's
  exclusive write set changed (tools/pyshader_divergence.py,
  tests/test_pyshader_divergence.py, this brief).
- The curve (gate_divergence receipt, ok=True, pin_failures=[]; wall
  informational only):
  N=2     uniform 1.0000 / half-mixed 0.5294 / adversarial 0.5556
  N=8     uniform 1.0000 / half-mixed 0.5294 / adversarial 0.5556
  N=64    uniform 1.0000 / half-mixed 0.5294 / adversarial 0.5556
  N=4096  uniform 1.0000 / half-mixed 0.5294 / adversarial 0.5556
  N=65536 uniform 1.0000 / half-mixed 0.5294 / adversarial 0.5556
  All four adjudication pins hold at every N: uniform==1.0; adversarial
  N=8 == 0.5556 (4dp); adversarial < uniform at every N; the N=65536
  adversarial cell ran to completion (rounds=18, efficiency reported
  unpinned).

  **CORRECTION 2026-09-20 ~16:20 (observer lane, on Jericho's in-channel
  order).** This rung was first summarized here as "the cost is REAL and
  constant (~44% of slots wasted under adversarial split, ~47% under
  half-mixed) but does NOT grow with N". **That sentence is withdrawn.**
  Under a fixed preload mix `useful` and `slots` are both proportional to
  N, so their ratio is invariant under scaling — the flatness is an
  algebraic identity, not an observation of N-independence, and the
  identical-to-4dp values across N=2..65536 are the signature of that
  rather than a finding. Nothing in this leg can show how divergence cost
  behaves at scale, because the metric cannot move. Roadmap :270-279
  verdict: **NOT REACHED** — none of the three named outcomes (tolerable /
  needs scheduling discipline / bad-at-low-N-tolerable-at-scale) is
  expressible in this proxy. The numbers above stand only as the
  composition ratio of the static mix.

  Required before this rung is informative, and before any downstream text
  cites it: a proxy whose numerator and denominator do NOT scale
  identically — real warp occupancy (lane-active cycles under actually
  divergent execution) or an actual GPU leg, per roadmap :246-268. Until
  then, "PS010 rung 1 landed" means the two-hart correctness gate closed;
  it does NOT mean PS010's non-vacuity (divergence-cost) requirement is
  satisfied. The caveats below are unchanged — they were accurate; only
  the headline overclaimed.
- Non-vacuity (brief row 4; probe /tmp/probe_ps010b_step4_nonvacuity.py,
  untracked scratch, exits 1 if the mutant passes): a sweep mutant with
  slots:=useful and efficiency hardcoded 1.0 →
  `mutant gate ok: False pin_failures: ['adversarial-efficiency-at-N=8',
  'monotone-decay-at-N=2', ..., 'monotone-decay-at-N=65536']`
  `NON-VACUITY OK: mutant REJECTED by the pin checks` — the exact-number
  pin and the decay inequality both bite.
- What this PASS does NOT prove: no GPU leg (host sequential round
  scheduler only); efficiency is lane occupancy of a host loop, NOT
  warp-execution efficiency from profiling counters (roadmap :253-255,
  later GPU rung); wall_seconds informational, never gated on; the
  adversarial split is a deterministic x5 PRELOAD (deterministic split
  point), intra-loop data-dependent divergence only approximated by the
  static mix; the flat-in-N shape is a property of THIS model (per-hart
  independent programs, dmem-free), not a hardware measurement.

## Definition of done

Steps 1..4 each with RED→GREEN evidence; structural harness green; full
PS-chain suite green; a receipt (appended to this brief) stating what is
proven and what is NOT — including: no GPU leg (this is the sequential
baseline), efficiency is the HOST scheduler's lane-occupancy metric and
not warp execution efficiency (profiling-counter IPC is a GPU-hardware
metric, roadmap :253-255, later GPU rung), wall-clock is informational,
and the sweep's verdict language must match roadmap :270-279: three
honest outcomes (tolerable / needs scheduling discipline / bad-at-low-N-
tolerable-at-scale) — the curve decides, not any single cell.

## What this round does NOT claim

- No GPU/SIMD leg, no WGSL, no dispatch-batching change.
- No warp-coherent scheduling implementation (that is the contingency
  the roadmap names if the curve comes back bad — a later rung).
- No claim about real hardware divergence cost; this rung bounds the
  MODEL's serial-degradation shape, which is the input to that verdict.

## Open work this brief does NOT close (PS010 stays un-closed on divergence)

Steps 1-4 are landed and green, but per the step-4 correction above the
divergence question is UNMEASURED: the efficiency proxy is scale-invariant
by construction. A PS010c rung is required before roadmap :246-268 can be
marked satisfied — its deliverable is a metric that can move (real
lane-active-cycle occupancy under divergent execution, or the GPU leg
itself), reusing this sweep's harness and pin discipline. Whichever of
PS010's GPU rung / PS011 the queue takes first, do not read :246-268 as
done in the interim.
