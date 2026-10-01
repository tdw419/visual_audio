# BRIEF PS010c — N-hart GPU kernel, correctness rung (SKELETON ROUND)

**Skeleton (read FIRST — it is the spec):** `tools/pyshader_multihart.py`
@ the commit that carries this brief (NEW file — the rung-1 precedent,
commit 30a7007c, landed brief + skeleton + harness together). Interfaces
are LOCKED. **Authority:** GPU_CPU_EMULATOR_ROADMAP.md:233-310 (PS010
non-vacuity requirement) + the PS010b step-4 CORRECTION
(brief_ps010b_divergence_sweep.md, 2026-09-20 ~16:20, observer lane on
Jericho's order): the host round-scheduler proxy is algebraically
scale-invariant (useful and slots both ∝ N under a fixed mix), so the
divergence verdict is NOT REACHED until a leg exists whose numbers can
move — a real GPU N-hart leg. RULING_ps009_fork_cleared_ps010_go.md sets
the order: correctness gates precede throughput claims (the PS009a→009b
pattern). This rung is that correctness rung. The MEASUREMENT rung
(wall-clock uniform-vs-adversarial on real lanes) is a LATER row of
PS010c or a new brief — do not claim any divergence-cost verdict here.

## Why this rung exists (measured)

PS010b's gate passed at every N with the identical 4dp efficiency
(0.5294/0.5556 at N=2 AND N=65536) — the signature of the ratio being
an algebraic identity, not a measurement. The correction names the fix:
real lane occupancy under actually divergent execution, or a GPU leg.
PS009a (tools/pyshader_fde_gpu.py, commit 2c2cffbf) already proved the
GPU seam: hand-written WGSL loop + GENERATED step_r/step_i bodies via
tools.pyshader_rvexec._alu_body_wgsl, one storage buffer, host
re-dispatch. This rung extends that seam from 1 hart to N invocations
with the PS010b round semantics (inter-hart state visible only at
boundaries; here the programs are dmem-free, so harts are independent
and bit-for-bit parity vs the host stepping is the whole gate).

## Scope (exclusive write set)

**Files in scope (only these may change):**
- `tools/pyshader_multihart.py` — NEW; populate stub bodies ONLY
  (signatures, docstring pins, program texts, and all constants LOCKED
  from the moment this brief lands).
- `tests/test_pyshader_multihart.py` — NEW; append behavioral tests;
  replace stub-raise guards with the behavioral gate named in each row
  (replace, never delete, per the contract).
- `.builder_queue/brief_ps010c_gpu_multihart.md` — receipt section only.
**Must-not-touch this round:** `tools/pyshader_hart.py`,
`tools/pyshader_divergence.py`, `tools/pyshader_fde.py`,
`tools/pyshader_ctl.py`, `tools/pyshader_fde_gpu.py`,
`tools/pyshader_rvexec.py`, `tools/pyshader_rvdecode.py`,
`tools/pyshader_wgsl.py`, `tools/pyshader_compiler.py`,
`tools/rv32i_asm.py`, ALL `tools/bare_metal_poc/**` +
`systems/virtio_pixel_rs/**` (Qoder lane). If a locked signature looks
wrong for a step: file `.builder_queue/REPAIR_PENDING_ps010c_<topic>.md`
(2-4 options, cheapest-first, marked skeleton-sign-off), then HOLD and
stop this run. Decisions return as `RULING_ps010c_<topic>.md`.

## Pinned facts (probe-verified 2026-09-20; do NOT restate from memory)

Program texts are the LOCKED constants imported from
tools/pyshader_divergence (LOW_PROG, MIX_PROG_SHORT, MIX_PROG_LONG,
DIVERGENT_PROG — words from assemble(), NEVER hand-encoding, the
tools/pyshader_hart.py:286-289 lesson). Probe-measured transition
counts (probe_ps010b_pins.py discipline, ALU steps COUNTED per the
PS008 convention; probe_ps010b receipt): LOW=5, SHORT=1, LONG=17,
DIVERGENT taken(x5=4)=2 / not-taken(x5=0)=18. The GPU kernel executes
the SAME subset as PS009a: R-type 0x33, ALU-Imm 0x13, BNE 0x63
funct3=1, EBREAK (0x00100073) = halt UNCOUNTED (running=0, the PS008
convention); anything else = STOP_BAD_OPCODE. SPEC branch semantics:
target = pc + imm//4 (RULING_ps008_branch_convention); pc counts
INSTRUCTION INDICES.

## Gate commands (structural, must stay green every step)

```
python3 -m pytest tests/test_pyshader_multihart.py -q   # exit 0
python3 -m pytest tests/test_pyshader_multihart.py tests/test_pyshader_hart.py tests/test_pyshader_ctl.py tests/test_pyshader_fde.py tests/test_pyshader_divergence.py -q   # exit 0
```
(GPU legs need the 5090 via pyshader_wgsl._cached_device — the
device-exhaustion lesson: NEVER create a second device; import the
cached one. If wgpu is unavailable in the builder env, the GPU rows
fail loudly — do not stub them green; file REPAIR_PENDING instead.)

## Step table (one row per builder run; run the LOWEST row without GREEN
evidence recorded in the receipt section below)

| # | Populate | New gate (test name) | Gate clause |
|---|---|---|---|
| 1 | `run_multihart_gpu` — uniform leg, single shared program, N invocations per dispatch (workgroup WG_SIZE, one transition per hart per dispatch = the round model) | `test_ps010c_uniform_parity_n8` | N=8 harts all LOW_PROG, no x5 inits: rounds==5, useful==40, every hart steps==5, and EVERY hart's final regs are bit-for-bit equal to host_reference(LOW_PROG, x5=0)'s regs (all zero except none — LOW leaves x1=0 at halt; assert full 32-reg equality anyway, not a sampled lane). No input mutation. RED evidence: NotImplementedError tail from the stub. |
| 2 | Static population-mix leg (per-hart imem base pointers — two programs packed into one imem region) | `test_ps010c_static_mix_parity_n8` | N=8: harts 0-3 MIX_PROG_SHORT, harts 4-7 MIX_PROG_LONG: rounds==17, useful==4*1+4*17=72; per-hart steps match [1,1,1,1,17,17,17,17]; every hart's final regs bit-for-bit == host_reference of its own program. RED first on the stub. |
| 3 | Adversarial register-split leg (SAME program text, per-hart x5 preload) | `test_ps010c_adversarial_parity_n8` | N=8, all DIVERGENT_PROG, x5 inits [4,4,4,4,0,0,0,0]: rounds==18, useful==4*2+4*18=80; per-hart steps [2,2,2,2,18,18,18,18]; every hart's final regs bit-for-bit == host_reference(DIVERGENT_PROG, its x5). RED first on the stub. |
| 4 | THE gate: `gate_multihart_parity` — 3 legs × N ∈ {2, 8, 64, 4096, 65536}, bit-for-bit + wall-clock informational | `test_ps010c_gate_multihart_parity` | Receipt dict (ok flag, does NOT raise on mismatch): per (leg, N) cell — rounds, useful, slots(=N*rounds), wall_seconds, parity_ok (sampled harts 0, N/2, N-1 bit-for-bit vs host_reference + SUM of steps exact vs the analytic pin). Pins: (a) parity_ok True at every cell; (b) rounds match the probe pins at every N (5/17/18); (c) wall_seconds REPORTED per cell (informational — never gated on; the uniform-vs-adversarial wall RATIO is the measurement rung's deliverable, NOT this gate's). The N=65536 cells must RUN (buffer ≈ 65536×HART_BLOCK_WORDS×4 bytes — assert it completed, report wall). RED first on the stub; non-vacuity: a mutant run that reports parity_ok hardcoded True with wrong reg values must be rejected by pin (a). |

## Hard constraints

- Additive only; never weaken a live guard to make a step pass.
- One GPU device, ever: import `_cached_device` from tools.pyshader_wgsl;
  creating a second device is the device-exhaustion defect class.
- Reuse, do NOT reimplement: step_r/step_i WGSL bodies come from
  tools.pyshader_rvexec._alu_body_wgsl over compile_function (the PS009a
  seam, tools/pyshader_fde_gpu.py:_build_shader is the pattern); decode
  field extraction may mirror PS009a's shader header; host_reference
  composes the LOCKED primitives (decode_ref/execute_one/execute_ctl)
  exactly as tools/pyshader_divergence.sweep does — no second decoder,
  no new executor.
- No performance claim anywhere in THIS rung: wall_seconds are recorded
  because they are free, but the uniform-vs-adversarial comparison that
  answers roadmap :246-268 is the NEXT rung (same-process pairing, the
  RULING_ps009 floor-attaching rule will apply to it).
- Budget discipline: max_rounds default 64; if any hart is still
  running at exhaustion, RuntimeError naming the budget — never a
  silent partial result (PS010 step-3 lesson). STOP_BAD_OPCODE on any
  hart surfaces in the receipt (stop list), never swallowed.
- Stdlib + existing toolchain only; no new dependencies.
- One gate-able step = one run = one commit. STOP after the row even if
  early. Receipt section updated in the same commit.

## Receipt section (append per-row GREEN evidence: commit + gate tail)

### Step 1 — `run_multihart_gpu` uniform leg + `host_reference` — GREEN 2026-09-20

RED (stub, literal tail):
```
E       NotImplementedError: PS010c step 1: run_multihart_gpu is a stub (skeleton round —
E       see .builder_queue/brief_ps010c_gpu_multihart.md step 1)
FAILED tests/test_pyshader_multihart.py::test_host_reference_divergent_pins
FAILED tests/test_pyshader_multihart.py::test_ps010c_uniform_parity_n8 - NotI...
2 failed, 3 passed in 0.13s
```
GREEN (same tests, after population):
```
tests/test_pyshader_multihart.py      5 passed in 0.91s
```
Full structural harness (brief gate command 2):
```
53 passed in 5.45s
```
(populated: tests/test_pyshader_multihart.py + tools/pyshader_multihart.py —
`host_reference` = LOCKED-primitive sweep stepping verbatim;
`run_multihart_gpu` = PS009a seam, one dispatch = one round, steps derived
from per-round pc-delta snapshots, rounds = max(steps) per the sweep
convention tools/pyshader_divergence.py:192). Two mid-fix defects caught by
the gate before GREEN: (1) compute pass missing `cp.end()` →
GPUValidationError "Encoder is locked"; (2) round-1 transition uncounted —
snapshot 0 was the post-round-1 readback instead of the initial payload,
giving steps=[4]*N; both were gate-caught, not silently shipped.
What PASS does NOT prove: static_mix / adversarial legs (steps 2-3),
`gate_multihart_parity` (step 4), any wall-clock or divergence-cost
verdict (measurement rung), shared-dmem ordering (programs are dmem-free).

### Step 2 — static population-mix leg — GREEN 2026-09-20

Note on RED discipline: `run_multihart_gpu` is ONE function covering all
three calling patterns and was populated in step 1, so step 2 has no
stub-raise to show. The brief's RED-first requirement is satisfied by a
DISCRIMINATION leg instead (the contract's "must be able to fail" form):
the swapped program assignment [LONG×4, SHORT×4] was run and measured
steps=[17,17,17,17,1,1,1,1] — rejected by the clause's per-hart steps
pin. That leg is baked into the test permanently (non-vacuity), with the
honest boundary stated: both MIX programs halt all-zero, so reg
equality alone cannot discriminate assignment — the steps pin carries it.

GREEN (tests/test_pyshader_multihart.py, after appending the gate):
```
6 passed in 1.00s
```
Structural harness (brief gate command 2):
```
54 passed in 5.73s
```
(clause pins: rounds==17, steps==[1,1,1,1,17,17,17,17],
useful==4*1+4*17==72, per-hart regs bit-for-bit == host_reference of
its OWN program, stops empty, no input mutation.)
### Step 3 — adversarial register-split leg — **UNBLOCKED (ruled) 2026-09-20**

HOLD lifted by `RULING_ps010c_blt_in_divergent_prog.md` (commit
1de7ee86): OPTION 1 adopted, shader B-type extended to all six funct3
verbatim from LOCKED `ref_ctl`; ticket marked RULED. RED evidence for
the step-3 gate is the pre-ruling GPU fault (steps [1,1,1,1,3,3,3,3],
8× STOP_BAD_OPCODE — pasted in the ruling commit body). The ruling
commit's GREEN probe already shows steps [2,2,2,2,18,18,18,18],
rounds 18, stops [], all-hart reg parity True — the builder run still
owes the behavioral test `test_ps010c_adversarial_parity_n8` in
tests/test_pyshader_multihart.py (write set: that file + this brief),
RED-first discipline satisfied by citing the ruling commit's RED/GREEN
tails.

### Step 3 — adversarial register-split leg — GREEN 2026-09-20

RED evidence: the pre-ruling GPU fault at HEAD 429b3b7a, machine-reproduced
and pasted in RULING_ps010c_blt_in_divergent_prog.md (BNE-only shader:
steps [1,1,1,1,3,3,3,3], rounds 3, stops 8x (hart, 3),
"AssertionError: PIN MUST FAIL (RED)"). Unblock: ruling commit 1de7ee86
extended the shader B-type to all six funct3 verbatim from ref_ctl;
steps 1-2 gates stayed green across that change (verified at HEAD
f0120afe before this run's edit).

GREEN (tests/test_pyshader_multihart.py::test_ps010c_adversarial_parity_n8
appended; N=8, all DIVERGENT_PROG, x5 [4,4,4,4,0,0,0,0]):
```
7 passed in 1.05s
```
Structural harness (brief gate command 2):
```
55 passed in 4.80s
```
(clause pins: rounds==18, steps==[2,2,2,2,18,18,18,18],
useful==4*2+4*18==80, stops empty, per-hart regs bit-for-bit ==
host_reference of its own x5. Non-vacuity beyond the ruling's RED: a
swapped-x5 leg measures [18,18,18,18,2,2,2,2] — proves the per-hart
preload reaches the shader and the reg pin can discriminate; the pre-ruling
fault itself proves the gate can fail on shader semantics.)
What PASS does NOT prove: `gate_multihart_parity` (step 4, still stub),
any wall-clock or divergence-cost verdict (measurement rung),
shared-dmem ordering (programs are dmem-free).

### Step 3 — adversarial register-split leg — **HOLD (REPAIR_PENDING) 2026-09-20**

NOT populated this run. Blocker: `.builder_queue/REPAIR_PENDING_ps010c_blt_in_divergent_prog.md`
(commit bd7a0523). The clause pin [2,2,2,2,18,18,18,18] is unreachable:
the not-taken path executes the spin-loop BLT (funct3=4) and the locked
shader is BNE-only — every hart faults STOP_BAD_OPCODE (measured:
steps [1,1,1,1,3,3,3,3], rounds 3, all stops (i,3)). Skeleton-sign-off
change required; next run: do NOT retry this row until
`RULING_ps010c_<topic>.md` lands and this blocker is marked RULED.
Steps 1-2 GREEN evidence above stands; structural harness green
(6 passed in 1.99s) at the tree this run measured.

What PASS does NOT prove: adversarial x5-split leg (step 3),
`gate_multihart_parity` (step 4), any wall-clock or divergence-cost
verdict (measurement rung), shared-dmem ordering.

### Step 4 — THE gate `gate_multihart_parity` — GREEN 2026-09-20 (RUNG DONE)

RED (stub, literal tail):
```
E       NotImplementedError: PS010c step 4: gate_multihart_parity is a stub
E       (skeleton round — see .builder_queue/brief_ps010c_gpu_multihart.md step 4)
FAILED tests/test_pyshader_multihart.py::test_ps010c_gate_multihart_parity
1 failed, 7 passed in 1.01s
```
Mid-fix builder defect (gate-caught, not silently shipped): the first
static_mix construction used `programs * half` (list duplication →
98,304 harts) and the gate loudly ValueError'd at MAX_TOTAL_WORDS —
fixed to `[SHORT]*half + [LONG]*(n-half)`.

GREEN (tests/test_pyshader_multihart.py after population):
```
8 passed in 8.12s
```
Structural harness (brief gate command 2):
```
56 passed in 12.71s
```
Full 15-cell receipt (parity_ok=True everywhere, stops empty,
pin_failures=[], rounds == probe pins 5/17/18 at every N):
```
uniform     N=2      rounds=5   useful=10      slots=10       wall=0.814s
uniform     N=8      rounds=5   useful=40      slots=40       wall=0.012s
uniform     N=64     rounds=5   useful=320     slots=320      wall=0.012s
uniform     N=4096   rounds=5   useful=20480   slots=20480    wall=0.085s
uniform     N=65536  rounds=5   useful=327680  slots=327680   wall=1.234s
static_mix  N=2      rounds=17  useful=18      slots=34       wall=0.037s
static_mix  N=8      rounds=17  useful=72      slots=136      wall=0.022s
static_mix  N=64     rounds=17  useful=576     slots=1088     wall=0.032s
static_mix  N=4096   rounds=17  useful=36864   slots=69632    wall=0.134s
static_mix  N=65536  rounds=17  useful=589824  slots=1114112  wall=2.022s
adversarial N=2      rounds=18  useful=20      slots=36       wall=0.041s
adversarial N=8      rounds=18  useful=80      slots=144      wall=0.017s
adversarial N=64     rounds=18  useful=640     slots=1152     wall=0.026s
adversarial N=4096   rounds=18  useful=40960   slots=73728    wall=0.149s
adversarial N=65536  rounds=18  useful=655360  slots=1179648  wall=2.645s
```
(wall_seconds are informational — the brief forbids gating on them, and
the uniform-vs-adversarial wall ratio is NOT a divergence-cost verdict;
the measurement rung prices that with same-process pairing and floors
attached. The N=65536 cells RAN the full buffer ≈ 65536*37*4 bytes.)

Non-vacuity: `test_gate_rejects_hardcoded_parity_mutant` corrupts a
sampled hart's register in a real receipt → parity pin names the
failure; a wrong step-sum → step-sum pin names it independently. Baked
in permanently. The mid-fix defect above is a second live failure path
(budget/guard fires instead of silent truncation).

Landing commit: 3b21e4bc.

## Definition of done (rung-level)

Steps 1..4 each with RED→GREEN evidence; structural harness green;
full PS-chain green; a receipt stating: bit-for-bit parity is proven at
the tested N values with sampled-hart reg equality plus exact step-sum
— and what is NOT: no wall-clock verdict (measurement rung), no shared-
dmem harts (the mailbox brief's ordering adjudication is separate), no
inter-hart communication, lanes are one-transition-per-dispatch so NO
divergence-cost number exists yet (that is the point of the next rung).
