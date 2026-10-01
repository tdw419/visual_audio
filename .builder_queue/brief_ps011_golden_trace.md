# BRIEF PS011 — Golden-trace cross-validation (SKELETON ROUND)

**Skeleton (read FIRST — it is the spec):** `tools/pyshader_golden.py`
@ the commit that carries this brief. Interfaces are LOCKED (verified
by test_ps011_signatures_locked). Do not change signatures, the trace
entry shape ({'pc','instr','regs'}), or the pinned gate program.
**Roadmap row:** GPU_CPU_EMULATOR_ROADMAP.md, `### PS011` (~line 329):
">=1 non-trivial program (>=1k instructions, branches+memory) with
100% trace match; any divergence produces a named spec-rule verdict."
**Modules to populate:** bodies of `golden_trace`, `pixel_trace`,
`diff_traces`, `build_gate_program`, `gate_golden_trace` in
`tools/pyshader_golden.py`; behavioral tests appended to
`tests/test_pyshader_golden.py`.
**Write set (exclusive):** those two files ONLY. Everything else —
including `tools/diff_qemu_gpu_traces.py`, `tools/pyshader_ctl.py`,
`tools/pyshader_fde.py`, `tools/spatial_rv32i_cpu.py`,
`tools/rv32i_asm.py` — is must-not-touch this round. If one of those
looks wrong for a step, that is a skeleton-sign-off issue: file
`.builder_queue/REPAIR_PENDING_ps011_<topic>.md` (measured conflict +
2-4 options cheapest-first + what you hold on) and pick the next
eligible step. Decisions come back as `RULING_ps011_<topic>.md`.

## Why the skeleton exists (measured)

The PS-chain precedent (PS007, PS010, PS010b): one-row-per-tick fits
the context window; a whole roadmap row per tick produced plans but no
code (PS007's three stub-only ticks). The architecture is locked here;
each step below fits ONE run. One gate-able step = one run = one
commit. Finishing early = stop, do NOT roll into the next row.

## Pinned facts (parse/verify from the skeleton docstring, never from
## memory)

- Gate program (8 words, locked in tools/pyshader_golden.py docstring):
  ADDI x1,x0,0 / ADDI x2,x0,250 / SW x1,0(x0) / LW x3,0(x0) /
  ADD x1,x1,x2 / ADDI x2,x2,-1 / BNE x2,x0,loop(insn 6 -> insn 2) /
  EBREAK. Loop body is 5 insns x 250 iterations + 2 init = 1252
  executed transitions (>= GOLDEN_MIN_TRANSITIONS by formula,
  re-verified against the measured trace length at step 4).
- Branch convention: SPEC semantics, taken next pc = pc + imm//4, no
  +1 (RULING_ps008_branch_convention — supersedes everything older).
- Reuse, do NOT reimplement: driver from `tools.pyshader_ctl`
  (run_ctl_trace + ControlHalt), decode from `tools.pyshader_fde`
  (decode_ref), assembly from `tools.rv32i_asm` (assemble — never
  hand-encode), pixel CPU from `tools.spatial_rv32i_cpu`
  (SpatialRV32ICore). The skeleton deliberately does NOT import
  tools/diff_qemu_gpu_traces.py — the comparison is re-implemented
  honestly for the PS-chain trace shape (rationale in the skeleton
  docstring); importing it would drag in kernel-boot assumptions.

## Step table (one row per builder run)

| # | Populate | New gate (test name) | Gate clause (RED first, then GREEN) |
|---|---|---|---|
| 1 | `golden_trace` | `test_ps011_golden_trace_shape_and_pins` | Run the pinned 8-word program (assembled via rv32i_asm.assemble, words NOT yet pin-verified — that is step 4): trace length == 1253 (initial snapshot + 1252 transitions, measured not hoped); trace[0] == {'pc':0, 'instr':decoded-word-0-string-or-int, 'regs': fresh state}; final regs match hand-derived pins x1==31375, x2==0; input state not mutated; max_steps exhaustion raises RuntimeError. RED evidence: NotImplementedError tail from the stub. |
| 2 | `pixel_trace` (SMOKE LANE) | `test_ps011_pixel_trace_smoke_lane` | Same 8 words through SpatialRV32ICore: entries in the SAME {'pc','instr','regs'} shape; length recorded; test SKIPS (pytest.skip) with the measured reason string when wgpu device acquisition fails or the GPU is absent — never fails the suite on hardware. Asserts ONLY shape invariants (length >= 2, keys present) when the device IS present; the ref-vs-pixel diff is recorded in receipts, never gated (determinism clause). RED evidence: NotImplementedError tail from the stub. |
| 3 | `diff_traces` | `test_ps011_diff_traces_spec_verdicts` | (a) identical traces -> ok=True, compared==len, spec_verdict None; (b) mutant with one wrong register value -> ok=False, first_mismatch names the index + reg, spec_verdict is a NON-EMPTY string citing the SPEC rule (not an engine name); (c) length mismatch -> ok=False with a named verdict; (d) x0 violated on one side -> detected (x0 is NOT excluded); (e) ignore_regs mechanism works when explicitly passed. RED evidence: NotImplementedError tail from the stub. |
| 4 | `build_gate_program` + `gate_golden_trace` — THE roadmap gate | `test_ps011_golden_gate` | build_gate_program returns (imem, dmem) with ALL 8 words decode-verified via decode_ref (fmt/opcode/funct3/imm each asserted, PS007 step-6 discipline; BNE imm == -16); gate_golden_trace returns a receipt dict: {'ok': True, 'transitions': 1252 (exact), 'final': {'x1': 31375, 'x2': 0}, 'trace_len': 1253 (exact), 'spec_verdicts': [], 'pixel_diff': RECORDED-or-'skipped' (never asserted)}. Non-vacuity REQUIRED: a mutant golden_trace (x1 += counter-1, one-off arithmetic slip) run through the gate receipt path must produce ok=False with a named verdict — the probe lives in the test file and is exercised in the leg. |

## Hard constraints

- Additive only. Do not edit tools/pyshader_golden.py signatures, the
  docstring pins, or the pinned program shape. The docstring's
  hand-derived FORMULA pins are the authority; if a step's measured
  arithmetic DISAGREES with the formula, STOP -> REPAIR_PENDING
  (do not adjust the program to fit a broken pin — that is exactly the
  PS007 word-6 failure shape).
- Keep live guards live: the structural harness's stub-raise tests are
  guards. REPLACE each stub-raise leg with its behavioral gate test —
  never delete a guard silently, never weaken one to pass.
- Stdlib + existing toolchain only; no new dependencies. No GPU in the
  gating lane (wgpu is the smoke lane only).
- The gate adjudicates against HAND-DERIVED pins (formula + measured
  agreement), never engine-vs-engine self-agreement: no engine
  adjudicates itself (PS004 lesson).

## Receipt discipline

- RED first (save the literal output tail), then GREEN; paste both
  tails in the commit message.
- After every step, the structural gate stays green:
  `python3 -m pytest tests/test_pyshader_golden.py -q` -> exit 0.
  Full PS-chain suite stays green:
  `python3 -m pytest tests/test_pyshader_hart.py tests/test_pyshader_ctl.py tests/test_pyshader_fde.py tests/test_pyshader_divergence.py -q`
  -> exit 0.
- Commit message ends with the skeleton-contract next-step line:
  `next: PS011 step N+1 (<row name>)`.

## Definition of done

Steps 1..4 each with RED->GREEN evidence; structural harness green
(stub tests replaced per the constraint above; the 10 original legs'
INTENT stays covered); PS-chain suite green; a receipt (appended to
this brief as `## PS011 receipt`) stating: what is proven, and what is
NOT — including that the pixel-CPU leg is a smoke lane (shape + diff
RECORDED, never gated), that QEMU itself was NOT in the loop this
round (the golden trace comes from the PS008 host driver — QEMU
adjudication is the follow-up rung if the roadmap names it), and that
"100% trace match" is claimed for ref-vs-ref-pins + ref-vs-pixel as
measured-and-recorded, per the determinism clause.

## What this round does NOT claim

- No QEMU-in-the-loop adjudication (the roadmap row's phrase
  "vs SPATIAL_RV64I/QEMU" — the pixel CPU is the in-loop second
  engine this round; wiring QEMU's insn stream is a later rung if
  PS012's [J-DECISION] keeps this lane alive).
- No RV64 anything (PS012 is a reserved branch point).
- No WGSL/GPU execution of the gate program (the PS-chain GPU legs
  smoke-lane discipline continues; batching is PS009, closed).
- No PS012 work: [J-DECISION] rows are RESERVED to Jericho.

## PS011 receipt — step 2 (pixel_trace — smoke lane)

Commit: bd272d7e (feat(ps011): step 2 — pixel_trace). Revision:
glyph-transpiler-autoloop @ e33f096d + this commit. Scope honored:
tools/pyshader_golden.py + tests/test_pyshader_golden.py ONLY (git
status verified before commit; the other dirty files in the tree are
parallel-session churn, untouched).

Change: pixel_trace (tools/pyshader_golden.py:135-210) populated —
drives SpatialRV32ICore one step per WGSL dispatch, projects each
get_state() into the golden {'pc','instr','regs'} shape. Two measured
semantics baked in (parse-verified in SPATIAL_RV32I.wgsl, not
assumed): (1) the pixel core's pc is BYTE-addressed (next_pc =
state.pc + 4u; taken branch = pc + imm) so the insn-index projection
is pc//4 at ram_base=0; (2) EBREAK at M-mode with mtvec=0 sets halted
with pc unchanged (raise_trap), so the trace ends after the last real
transition — same shape as golden_trace. Non-multiple-of-4 pc =
leave-image, terminal. Device acquisition raises
RuntimeError('wgpu device acquisition failed: ...') on any wgpu
failure (PS005 device-exhaustion discipline); the smoke-lane test
SKIPS on exactly that string. Budget exhaustion raises RuntimeError.
The stub-raise guard test_pixel_trace_stub_raises was REPLACED by
test_ps011_pixel_trace_smoke_lane per the keep-guards-live constraint
(removal noted in the test docstring — audit trail kept).

RED tail (literal, stub in place):
`NotImplementedError: PS011 step 2: pixel_trace is a stub` —
`1 failed in 0.10s` (exit 1)

Mid-run RED (shape leg caught numpy leakage, literal):
`+  where False = isinstance(np.uint32(0), int)` — `1 failed,
9 passed in 6.35s`; fixed by coercing pc/halted to int in the
projection (implementation fixed, not the guard).

GREEN tails (literal):
`10 passed in 7.79s` (tests/test_pyshader_golden.py, exit 0)
`PS011 smoke-lane record: ref_len=1253 pixel_len=1253
first_mismatch=None` (the -s record line; RECORDED, never gated)
`58 passed in 13.30s` (PS-chain suite: hart + ctl + fde + divergence
+ golden)

**What this PASS does NOT prove:**
- The ref-vs-pixel 1253/1253 no-mismatch line is a RECORDED smoke
  observation on ONE program at ONE revision — it is NOT the PS011
  gate and NOT the roadmap's "100% trace match" claim; the gate is
  step 4 (decode-verified words + hand-derived pins + non-vacuity
  mutant).
- The skip path was not exercised (wgpu device WAS present on this
  host); the skip leg is inspection-verified only.
- The budget-exhaustion RuntimeError is implemented but has no
  dedicated machine-checked leg.
- x0 behavior of the pixel core was not separately probed; x0
  adjudication belongs to diff_traces (step 3), where x0 is
  explicitly NOT excluded.
- 1253 pixel entries at 1 dispatch/step took ~6s wall on this host;
  no performance claim is made or gated.

next: PS011 step 3 (diff_traces)

## PS011 receipt — step 3 (diff_traces)

Commit: 867589ed (feat(ps011): step 3 — diff_traces). Revision:
glyph-transpiler-autoloop @ bd272d7e + this commit. Scope honored:
tools/pyshader_golden.py + tests/test_pyshader_golden.py ONLY (git
status verified before commit; the other dirty files in the tree are
parallel-session churn, untouched).

Change: diff_traces (tools/pyshader_golden.py:218-288) populated —
entry-by-entry compare, pc first, then every register present in BOTH
sides (intersection, never union — the diff_qemu_gpu_traces.py:65
lesson; that module is NOT imported or modified). Receipt dict
{'ok','compared','first_mismatch','spec_verdict'}: first_mismatch is
{'index','reg','ref_val','imp_val'} (reg None for pc mismatch);
spec_verdict is None on ok, else a NAMED RISC-V Unprivileged Spec rule
string per divergence class (x0!=0 / pc control flow / register
result / trace-length control-flow divergence) — the verdict cites the
SPEC, never an engine name (PS004 lesson, test-enforced). x0 is NOT
excluded by default; explicit ignore_regs excludes engine-specific
non-architectural state. Length mismatch refuses loudly with its own
verdict rather than silently zipping to the shorter side. The
stub-raise guard test_diff_traces_stub_raises was REPLACED by
test_ps011_diff_traces_spec_verdicts per the keep-guards-live
constraint (removal noted in the test docstring — audit trail kept).

RED tail (literal, stub in place):
`NotImplementedError: PS011 step 3: diff_traces is a stub (skeleton
round — see .builder_queue/brief_ps011_golden_trace.md step 3)` —
`1 failed, 9 passed in 7.50s` (exit 1)

GREEN tails (literal):
`10 passed in 7.79s` (tests/test_pyshader_golden.py, exit 0)
`58 passed in 12.71s` (PS-chain suite: hart + ctl + fde + divergence +
golden, exit 0)

Negative legs (gate proven able to fail):
- wrong x1 at entry 4 (counter=3 pinned-program variant, real ref
  engine vs deep-copied mutant) -> ok=False, index=4 reg=1, SPEC
  verdict present and asserted engine-name-free.
- one-entry-short trace -> ok=False with a named SPEC verdict.
- x0=7 on one side -> DETECTED (reg=0, x0 NOT excluded); passes only
  with explicit ignore_regs=frozenset({0}).

**What this PASS does NOT prove:**
- Gate clauses run the ref engine vs MUTANTS of the ref engine
  (determinism clause); no second live engine was diffed at this
  step — ref-vs-pixel remains the recorded smoke lane (step 2).
- instr words are compared only indirectly (both sides project from
  imem); a deliberate instr-only divergence is not machine-checked.
- The pc-mismatch verdict branch is implemented but its
  first_mismatch reg=None shape has no dedicated leg.
- build_gate_program / gate_golden_trace remain stubs (step 4 — THE
  roadmap gate).

next: PS011 step 4 (build_gate_program + gate_golden_trace — THE
roadmap gate)

## PS011 receipt — step 4 (build_gate_program + gate_golden_trace —
## THE roadmap gate) — PS011 COMPLETE

Commit: 9f728a60 (feat(ps011): step 4 — build_gate_program +
gate_golden_trace). Revision: glyph-transpiler-autoloop @ 01385e44 +
this commit. Scope honored: tools/pyshader_golden.py +
tests/test_pyshader_golden.py ONLY (git status verified before
commit; the other dirty files in the tree are parallel-session churn,
untouched).

Change: build_gate_program (tools/pyshader_golden.py:291-360) —
assembles the docstring-pinned 8-word program via rv32i_asm.assemble
(never hand-encoded) and decode-verifies ALL 8 words field-exact via
PS005 decode_ref (fmt/opcode/funct3/imm each asserted; BNE imm ==
-16 = insn 6 -> insn 2, SPEC semantics per
RULING_ps008_branch_convention — the assembler already emits the
SPEC-convention encoding, probe-verified at the landing revision).
gate_golden_trace (tools/pyshader_golden.py:363-494) — runs the gate
program through golden_trace and adjudicates against HAND-DERIVED
pins (formula + measured agreement), never engine-vs-engine
self-agreement: transitions == 1252 exact (>=
GOLDEN_MIN_TRANSITIONS), final x1 == 31375 (sum 1..250), x2 == 0,
x3 == 31374, all other regs 0, x3-per-iteration sampled at the ADD
snapshot with the closed-form descending-counter pin. pixel_diff is
RECORDED, never gated (determinism clause); the golden_self()
indirection makes the non-vacuity monkeypatch visible to the gate.
The stub-raise guards test_build_gate_program_stub_raises /
test_gate_golden_trace_stub_raises were REPLACED (not deleted) by
test_ps011_golden_gate per the keep-guards-live constraint (removal
noted in the test docstring — audit trail kept).

RED tail 1 (literal, tooling artifact — the patch channel doubled the
SRC line-continuation, so the assembler saw a literal backslash):
`ValueError: Unknown mnemonic: \\` — `1 failed, 8 passed in 7.89s`
(exit 1). Fixed the payload, not the engine.

RED tail 2 (literal, THE interesting failure — the brief's formula
pin for x3 disagreed with the measured engine):
`AssertionError: ['SPEC: final x3 31374 != hand-derived 31125 (acc at
last SW, sum 1..249) — load-result semantics ...']` and, after the
first re-derivation, `['SPEC: x3 at iteration 3 = 250, hand-derived 1
...']`. Root cause (probe .builder_queue/probe_ps011_x3_pin.py,
measured): trace entries are snapshots BEFORE execution, and
iteration k's SW is not visible to iteration k's own LW — iteration
k+1's LW loads it (the driver executes the LW before the ADD each
iteration). Hand-re-derived: x3 after iteration k's LW =
(k-1)*(502-k)//2 (descending adds 250+249+...), giving x3(250) =
31374 = exactly the docstring's "acc value at the last SW". This was
TEST-SIDE pin arithmetic, not engine drift and not a locked-interface
change — no REPAIR_PENDING was needed, and the engine body was not
altered (the docstring pins were never contradicted; my first
derivations were).

GREEN tails (literal):
`9 passed in 24.50s` (tests/test_pyshader_golden.py, exit 0)
`57 passed in 33.12s` (PS-chain suite: hart + ctl + fde + divergence
+ golden, exit 0)

Negative legs (gate proven able to fail — non-vacuity in-test):
mutant golden_trace (x1 += counter-1, one-off arithmetic slip) run
through the SAME receipt path -> ok=False, spec_verdicts[0] = 'SPEC:
final x1 31374 != hand-derived 31375 (sum 1..250) — register-result
semantics, RV32I Unprivileged Spec §2.4' — engine-name-free, and the
mutant's final x1 != the pin. The pins DISCRIMINATE.

Recorded (never gated): pixel_diff = {'ok': True, 'compared': 1253,
'first_mismatch': None, 'spec_verdict': None} — a FULL ref-vs-pixel
match on THIS run's device. The skip path ('skipped' string) is
inspection-verified only; the device was present on this host.

**What this PASS does NOT prove:**
- QEMU was NOT in the loop this round: the golden trace comes from
  the PS008 host driver (run_ctl_trace); the pixel CPU is the
  in-loop second engine as a SMOKE lane, and its 1253/1253 match is
  a recorded observation at one revision, not a formal claim.
- "100% trace match" is claimed as: ref-vs-hand-derived-pins
  (gated) + ref-vs-pixel (measured-and-RECORDED, non-blocking) — per
  the determinism clause.
- The GPU leg samples the full pixel trace once; no WGSL-side
  unit-level re-verification of every instruction was done.
- No multi-hart anything (PS010 territory); no JAL/JALR exercised by
  THIS gate program (PS008's own gate covers those).
- The mutant discriminates the PINS, not the decoder: a decode-level
  mutant (wrong word, right pins) is out of scope here —
  build_gate_program's field-exact asserts are the guard for that.
- gate_golden_trace's ok is against the hand-derived pins plus
  structural formulas for ONE pinned program; it is not a formal
  proof of the engine for arbitrary programs.

PS011 DEFINITION OF DONE: steps 1..4 all landed with RED->GREEN
evidence; structural harness green (guard count 9; every stub-raise
guard replaced by a behavioral gate per the constraints); PS-chain
suite green. next: PS011 COMPLETE — no further steps in this brief.

## HOLD receipt — PS-chain supply exhausted at [J-DECISION] (2026-09-20 ~20:05 CT, orchestrator run @ 5ac52019)

Measured, not hoped: PS010d COMPLETE (steps 1-4 green, receipt above in
brief_ps010d_divergence_measurement.md); PS011 COMPLETE (receipt above);
PS005/PS006/PS007 done-closures per roadmap. Re-ran the PS-chain legs on
this tree myself: tests/test_pyshader_golden.py + test_pyshader_measure.py +
test_pyshader_multihart.py + test_pyshader_divergence.py —
`32 passed in 31.11s` (exit 0, real GPU legs included).

Next roadmap row is PS012 (RV64 or harvest, GPU_CPU_EMULATOR_ROADMAP.md:338),
marked **[J-DECISION]** — three exits (extend to RV64 / harvest into
SPATIAL_RV64I.wgsl / stop-and-close), chosen on PS009+PS011 data. That is
Jericho's call, never self-promoted. PS013 is explicitly gated on PS012
closing. Bare-metal rows remain OUT OF SCOPE per the 2026-09-19 redirect.

**HOLD.** Supply resumes when Jericho rules on PS012 (RULING_ps012_<topic>.md
or in-channel). The curve PS010d supplied for that decision: divergence ratio
peaks at N=64 (2.498, warp-fill artifact) and decays to ~1.72 at 65536 harts
— flat from 4096 to 65536.

