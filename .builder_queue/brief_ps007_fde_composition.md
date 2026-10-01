# BRIEF PS007 — Fetch-decode-execute composition (SKELETON ROUND)

**Skeleton (read FIRST — it is the spec):** `tools/pyshader_fde.py` @
the commit that carries this brief. Interfaces are LOCKED. Do not
change signatures, the `State` shape, or the pinned program.
**Modules to populate:** bodies of `fetch`, `execute_one`, `run_fde`,
`gate_fibonacci` in `tools/pyshader_fde.py`; behavioral tests appended
to `tests/test_pyshader_fde.py`.
**Write set (exclusive):** those two files ONLY. Everything else —
including `tools/pyshader_rvexec.py`, `tools/pyshader_rvdecode.py`,
`tools/pyshader_wgsl.py`, `tools/pyshader_compiler.py` — is
must-not-touch this round. If one of those looks wrong for a step,
that is a skeleton-sign-off issue: file
`.builder_queue/REPAIR_PENDING_ps007_<topic>.md` (measured conflict +
2-4 options cheapest-first + what you hold on) and pick the next
eligible step. Decisions come back as `RULING_ps007_<topic>.md`.
**Structural gate (must stay green every step):**
`python3 -m pytest tests/test_pyshader_fde.py -q` → exit 0 (10 legs).
Full suite also stays green: `python3 -m pytest tests/test_pyshader_compiler.py -q`.

## Why the skeleton exists (measured)

Three builder ticks (15:27, 15:58, and one earlier) produced plans but
no code: PS007-as-one-rung does not fit one tick's context window.
The architecture is locked here instead; each step below fits ONE run.
One gate-able step = one run = one commit. Finishing early = stop, do
NOT roll into the next row.

## Pinned facts (parse/verify, never restate from memory)

- Fibonacci program (7 words, encoded in the skeleton docstring):
  `ADDI x1,x0,1 / ADDI x2,x0,1 / ADD x3,x1,x2 / ADDI x1,x2,0 /
   ADDI x2,x3,0 / ADDI x5,x5,-1 / BNE x5,x0,-2`
  with x5 preloaded to 8 iterations.
- Hand-computed (host session, measured 9/19): x3 sequence per loop
  iteration = 2, 3, 5, 8, 13, 21, 34, 55; final state x1=34 (F9),
  x2=55 (F10), x3=55, x5=0; total executed instructions = 42
  (2 init ADDIs + 5 per iteration x 8).
- Reuse, do NOT reimplement: decode from `tools/pyshader_rvdecode`
  (PS005), ALU step sources from `tools/pyshader_rvexec`
  (`STEP_R_SRC`/`STEP_I_SRC`, PS006), GPU dispatch through
  `pyshader_wgsl._cached_device()` (device-exhaustion lesson).

## Step table (one row per builder run)

| # | Populate | New gate (test name) | Gate clause (RED first, then GREEN) |
|---|---|---|---|
| 1 | `fetch` | `test_ps007_fetch_bounds_and_values` | fetch(0..len-1, imem) returns the right masked word; fetch(len, imem) raises IndexError; fetch(-1, …) raises IndexError. RED evidence: NotImplementedError tail from the stub. |
| 2 | `execute_one` — straight-line R/I | `test_ps007_exec_addi_and_add_straightline` | ADDI x1,x0,1 then ADD x3,x1,x2 executed from a fresh state: returned state has pc=2, x1=1, x3=2, every other register untouched; input state dict NOT mutated. |
| 3 | `execute_one` — B-type taken/not-taken | `test_ps007_bne_taken_and_fallthrough` | Same word executed with x5=3 → pc = 4 + (-2)... i.e. branch target = pc + 1 + offset(insns) — assert BOTH directions: taken (x5≠0) jumps back, not-taken (x5=0) advances pc+1. Include offset arithmetic for the -2-insn encoding; wrong sign = RED. |
| 4 | `execute_one` — x0-write suppression | `test_ps007_x0_write_suppressed` | ADDI x0,x0,7 leaves regs[0]==0 and advances pc. (This closes PS006's documented honest boundary.) |
| 5 | `run_fde` | `test_ps007_run_fde_trace_shape` | trace length == n_steps+1; trace[0] is the input state (unmutated); no input mutation (deep-compare before/after). |
| 6 | `gate_fibonacci` — THE roadmap gate | `test_ps007_fibonacci_gate` | Build the pinned program, run_fde 42 steps, final regs match the hand-computed pin above (x1=34, x2=55, x3=55, x5=0) AND the x3-per-iteration sequence appears in the trace; GPU leg: the composed step dispatch for insn 2 (ADD) and insn 6 (BNE) each verified via `run_triple_differential` + hand-computed ref on the actual operand values from the trace (4-way check, PS004 lesson). |

## Hard constraints

- Additive only. Do not edit `tools/pyshader_fde.py` signatures,
  docstring pins, or the pinned program. Do NOT touch the PS006
  honest-boundary comment except by closing it in the step-4 receipt.
- Keep live guards live: the structural harness's stub-raises tests
  are guards. When you populate a body, REPLACE that stub's raise with
  the implementation and UPDATE the corresponding stub test to the
  behavioral one — never delete a guard silently; never weaken one to
  pass (a stub-raise test for a now-implemented function becomes a
  `pytest.raises(IndexError)` bounds test per the gate clause).
- Stdlib + existing toolchain only; no new dependencies.
- BNE decode: reuse PS005's decode output for opcode/funct3/imm; the
  branch offset is the I/B-immediate the PS005 decoder already
  sign-extends. If the PS005 fixture set lacks B-type fields you need,
  STOP → REPAIR_PENDING (do not fork a second decoder).

## Receipt discipline

- RED first (save the literal output tail), then GREEN; paste both
  tails in the commit message.
- After every step, both structural gate and full suite stay green.
- Commit message ends with the skeleton-contract next-step line:
  `next: PS007 step N+1 (<row name>)`.

## Definition of done

Steps 1..6 each with RED→GREEN evidence; structural harness green
(stub tests updated per the constraint above, count may grow but the
10 original legs' INTENT stays covered); full suite green; a receipt
(appended to this brief as `## PS007 receipt`) stating: what is
proven, and what is NOT — including that the multi-hart layout was
NOT exercised (that is PS010) and the GPU leg only samples the two
named dispatches, not every instruction of the trace.

## What this round does NOT claim

- No SLT/SLTU family (PS006b, unchanged).
- No JAL/JALR/LW/SW — PS008+ scope; the Fibonacci program deliberately
  fits the PS006 ALU subset + BNE.
- No multi-hart anything. Single hart, host-driven dispatch.

## PS007 receipt — step 6 (gate_fibonacci — THE roadmap gate) — RULED + LANDED

Commit: PS007 step 6: gate_fibonacci populated (Fibonacci gate GREEN;
word-6 pin per RULING_ps007_fib_branch_offset)
Revision: glyph-transpiler-autoloop @ ee2d14fc + this commit

Un-HOLD: RULING_ps007_fib_branch_offset.md (commit ee2d14fc) adopted
OPTION 1 — word 6 = `BNE x5,x0,-20` (0xFE0296E3). The blocker is
marked RULED in REPAIR_PENDING_ps007_fib_branch_offset.md (not
deleted). Brief line 33's `-2` is superseded by the ruling: -5 insns
/ -20 bytes.

Scope honored: tools/pyshader_fde.py + tests/test_pyshader_fde.py ONLY
(git status verified before commit).

Change: `gate_fibonacci` (tools/pyshader_fde.py:209-283) populated —
builds the pinned `FIB_PROGRAM` (all 7 words decode-verified field-exact
via PS005 decode_ref at the landing revision), runs 42 steps with
x5=FIB_LOOP_COUNT_DEFAULT, adjudicates against the HAND-COMPUTED pin:
final regs x1=34/x2=55/x3=55/x5=0 + all-others-zero, x3 sequence
2,3,5,8,13,21,34,55 sampled at the ADD commit, trace shape 43. GPU legs
(4-way, PS004 lesson): ADD dispatch via run_alu_differential and BNE
comparison via run_triple_differential, each on ACTUAL trace operand
values with a hand-computed ref — no engine adjudicates itself. Receipt
returned as a dict (ok=False on mismatch; does not raise). The
stub-raise guard test_gate_fibonacci_stub_raises was REPLACED by
test_ps007_fibonacci_gate per the brief's hard constraints (removal
noted by comment in the test file — audit trail kept).

RED tail (literal, stub still in place):
`ImportError: cannot import name 'FIB_PROGRAM' from 'tools.pyshader_fde'`
`1 failed in 0.08s` (exit 1)

Mid-run RED (guard transition, literal):
`Failed: DID NOT RAISE NotImplementedError` (test_gate_fibonacci_stub_raises
vs the populated body) — the guard was then replaced by the behavioral
gate, per the brief.

GREEN tail (literal):
`12 passed in 0.75s` (tests/test_pyshader_fde.py, exit 0)
`66 passed in 2.20s` (tests/test_pyshader_compiler.py full suite)

Negative legs (gate proven able to fail):
- corrupted word 3 (ADDI x1,x1,0 instead of x1=x2): gate ok=False,
  final_ok=False, x3 seq head [2,3,4,5] — refusal PASS.
- the ORIGINAL -8 pin (0xFE029CE3): run_fde raises
  `IndexError: fetch: pc 7 out of bounds (imem len 7)` at step 22 —
  the exact defect the ticket probe measured; loud refusal either way.

**What this PASS does NOT prove:**
- The GPU leg samples ONE ADD dispatch and ONE BNE comparison on
  operand values taken from the trace — NOT every instruction of the
  42-step trace on the GPU.
- The pixel-CPU and oracle legs run inside run_triple_differential's
  own ok flag; they were not separately re-derived here.
- No multi-hart layout exercised (PS010). No JAL/JALR/LW/SW (PS008+).
- FIB_EXPECTED_TRACE_HEAD remains a placeholder string ("FIB-TRACE-
  PINNED-IN-BRIEF"); the brief's pins live in FIB_X3_SEQUENCE /
  FIB_EXPECTED_FINAL / FIB_EXPECTED_STEPS instead. Interface unchanged.
- gate_fibonacci's ok is computed against the hand-computed pin plus
  the three GPU/oracle/CPU legs of two sampled dispatches; it is not
  a formal proof of execute_one for arbitrary programs.

What this round does NOT claim (unchanged from the brief): no SLT/SLTU
family, no JAL/JALR/LW/SW, no multi-hart anything.

PS007 DEFINITION OF DONE: steps 1..6 all landed with RED→GREEN
evidence; structural harness green (guard count 12; every stub-raise
guard replaced by a behavioral gate per the constraints); full suite
green. next: PS007 COMPLETE — no further steps in this brief.

---

## PS007 receipt — step 6 (HOLD: skeleton-sign-off conflict, not populated) [SUPERSEDED by the receipt above]

Commit: none (no gate-able step landed; tree left green at the
step-5-inclusive HEAD 557073ba).

Rule 3 of the skeleton contract fired: the LOCKED pinned program in
`tools/pyshader_fde.py:62` cannot reach the hand-computed pin the SAME
brief mandates — with imm=-8 the branch at pc=6 targets pc=5 (a
x5--/BNE spin that falls off imem at step 22, `IndexError: fetch: pc 7
out of bounds (imem len 7)`, probe-measured) instead of the loop head
pc=2 the brief's 42-step / x3=2,3,5,…,55 pin requires. Fixing a locked
constant is a skeleton-sign-off change → filed
`.builder_queue/REPAIR_PENDING_ps007_fib_branch_offset.md` (cheapest
fix VERIFIED: word 6 → 0xFE0296E3, i.e. `BNE x5,x0,-20`; the 7-word
program then reproduces the pin exactly through the already-green
steps 1-5) and HOLD per the contract.

What this run did NOT do: populate `gate_fibonacci` (still raises
NotImplementedError), write `test_ps007_fibonacci_gate`, exercise any
GPU leg, or land a commit for step 6. The stub-raise guard
`test_gate_fibonacci_stub_raises` remains live and green.

next: PS007 step 6 (gate_fibonacci) — blocked on
RULING_ps007_fib_branch_offset.md

## PS007 receipt — step 3 (B-type taken/not-taken)

Commit: PS007 step 3: execute_one BNE taken/not-taken
Revision: glyph-transpiler-autoloop @ 15b16915 + this commit
Scope honored: tools/pyshader_fde.py + tests/test_pyshader_fde.py ONLY
(probe scratch .builder_queue/probe_ps007_bne_encoding.py, untracked,
not part of the gate).

**What was done.** B-type leg added to `execute_one`
(tools/pyshader_fde.py:127-146): reuses PS005 `decode_ref` (no second
decoder — its B dict already carries rs1/rs2/funct3 and the
sign-extended byte imm), restricts to BNE (funct3=1), taken =
regs[rs1] != regs[rs2], taken → pc + 1 + imm//4, not-taken → pc + 1.
Branches never write registers; returned state is always a new dict.
Non-whole-insn offsets raise rather than silently truncating.
Behavioral gate `test_ps007_bne_taken_and_fallthrough` replaces the
step-2 raise for B words (guard UPDATED, not deleted — non-BNE funct3
still raises).

**RED tail (stub, literal):**
`NotImplementedError: PS007 step 2: execute_one covers R (0x33) and ALU-I (0x13) only; got fmt='B' (opcode 0x63) at pc=0`
Encoding pre-check: enc_b(-8,5,0,1) = 0xFE029CE3; decode_ref gives
fmt=B funct3=1 rs1=5 rs2=0 imm=-8 (bytes) — .builder_queue/probe_ps007_bne_encoding.py.

**Mid-run RED (test-side arithmetic slip, literal):**
`AssertionError: taken branch: expected pc=0 (2+1-2), got 1` — the
implementation was correct (target = pc + 1 + offset per the locked
docstring AND the gate clause's own "pc = 4 + (-2)" example); the
test's expected pc was wrong (2+1-2 = 1, not 0). Fixed the test, not
the guard.

**GREEN tail (literal):** `77 passed in 2.23s`
(tests/test_pyshader_fde.py + tests/test_pyshader_compiler.py, venv
python, PYTHONPATH=. per pytest.ini pythonpath).

**What this PASS does NOT prove:**
- Only funct3=1 (BNE) is exercised; BEQ/BLT/etc. still raise.
- GPU leg is absent at this step (it belongs to step 6's gate clause).
- The offset%4 refusal leg is implemented but not separately asserted
  as RED in a dedicated test (the raise is live; not machine-checked).
- run_fde / gate_fibonacci remain stubs (steps 5-6).
next: PS007 step 4 (x0-write suppression)

## PS007 receipt — step 4 (x0-write suppression)

Commit: PS007 step 4: execute_one x0-write suppression

Scope honored: tools/pyshader_fde.py + tests/test_pyshader_fde.py ONLY
(git status verified before commit).

Change: the step-2/3 write-back `regs[d["rd"]] = result` is now guarded
with `if d["rd"] != 0` (tools/pyshader_fde.py:163-168). The PS006
honest-boundary comment is CLOSED by this step's receipt, per the brief's
hard constraint — no other docstring or pin was touched. No signature
changed; guards (fetch bounds, BNE-only funct3 raise, non-R/I raise)
all remain live.

RED tail (literal):
`AssertionError: x0-write suppression: regs[0] must stay 0, got 7`
`assert 7 == 0` (tests/test_pyshader_fde.py:174, exit 1)

GREEN tail (literal): `78 passed in 2.39s`
(tests/test_pyshader_fde.py + tests/test_pyshader_compiler.py;
12/12 FDE legs incl. the new test_ps007_x0_write_suppressed).

**What this PASS does NOT prove:**
- Suppression is gated on the R/I ALU path only. B-type writes no
  registers at all (branches are read-only), so there is nothing to
  suppress there — verified by inspection, not by a dedicated leg.
- GPU leg is absent at this step (it belongs to step 6's gate clause).
- run_fde / gate_fibonacci remain stubs (steps 5-6).
next: PS007 step 5 (run_fde)

## PS007 receipt — step 5 (run_fde)

Commit: PS007 step 5: run_fde trace driver

Scope honored: tools/pyshader_fde.py + tests/test_pyshader_fde.py ONLY
(git status verified before commit).

Change: run_fde (tools/pyshader_fde.py:170-183) populated — drives
execute_one n_steps times, appends every returned snapshot; trace[0] is
a fresh COPY of the input state (pc + regs list-copied), so mutating
the input after the call cannot retroactively rewrite the trace. No
signature changed; fetch bounds / BNE-only / non-R/I / x0-suppression
guards all remain live. The structural guard test_run_fde_stub_raises
was REPLACED (not deleted) by test_ps007_run_fde_trace_shape per the
brief's keep-guards-live constraint.

RED tail (literal), against the still-stubbed body:
`NotImplementedError: PS007 step 5: run_fde`
`1 failed, 11 passed in 0.08s` (exit 1)

GREEN tail (literal):
`12 passed in 0.07s` (tests/test_pyshader_fde.py, exit 0)
`66 passed in 2.31s` (tests/test_pyshader_compiler.py full suite)

**What this PASS does NOT prove:**
- Trace shape is exercised on straight-line code only (NOP padding);
  a taken BNE inside run_fde is NOT machine-checked until step 6 runs
  the Fibonacci loop through the driver.
- n_steps=0 and negative n_steps are untested (unspecified corners).
- gate_fibonacci remains a stub (step 6 — the roadmap gate).
- GPU leg absent (belongs to step 6's gate clause).
next: PS007 step 6 (gate_fibonacci — THE roadmap gate)

## PS007 receipt — step 6 (gate_fibonacci — THE roadmap gate) [DONE-CLOSURE]

Commit: 094c559e (gate populated, GREEN) + e649cddf (RULING_ps008
effectuation: FIB word 6 -> 0xFE0298E3, SPEC branch semantics
pc+imm//4 for both executors; hand-computed pin unchanged — 42 steps,
x3 = [2,3,5,8,13,21,34,55], final x1=34/x2=55/x3=55/x5=0 still hold
under the corrected encoding, machine-checked below).

Scope honored: tools/pyshader_fde.py + tests/test_pyshader_fde.py ONLY
in 094c559e; e649cddf additionally touched the skeleton's own word-6
pin per RULING_ps008 (skeleton-author-side, not a builder signature
change).

Change: gate_fibonacci (tools/pyshader_fde.py:215-293) populated —
builds the pinned FIB_PROGRAM with x5=8, run_fde 42 steps, adjudicates
shape / final-regs / x3-per-iteration-sequence against the
HAND-COMPUTED pin, and runs TWO GPU legs on actual trace operand
values (4-way: GPU == oracle == pixel CPU == hand-computed ref): the
last-iteration ADD x3,x1,x2 (pc=2, operands 21+34) via
run_alu_differential, and a TAKEN BNE (pc=6, x5=1) via
run_triple_differential on a branch-free step source. The
stub-raise guard was REPLACED (not deleted) by
test_ps007_fibonacci_gate (tests/test_pyshader_fde.py:180).

RED tail (literal), against the still-stubbed body (step-6 landing
run): `NotImplementedError` from gate_fibonacci stub -> 1 failed
(exit 1). The branch-offset pin itself went RED mid-run and was
adjudicated by live probe: the skeleton's word 6 was mis-encoded for
its own stated convention; RULING_ps007_fib_branch_offset then
RULING_ps008_branch_convention resolved it (ee2d14fc, e649cddf).

GREEN tail (literal, re-verified at HEAD e649cddf+ post-RULING, this
run, exit 0):
`12 passed in 1.03s` (tests/test_pyshader_fde.py)
`66 passed in 4.05s` (tests/test_pyshader_compiler.py full suite)
gate_fibonacci receipt: ok=true, trace_len=43, x3_sequence
[2,3,5,8,13,21,34,55], final {x1:34, x2:55, x3:55, x5:0}, all
registers outside the pin zero; gpu_add 4-way all 55, gpu_bne 4-way
all 1 (ok / shape_ok / final_ok / sequence_ok / gpu_add_ok /
gpu_bne_ok all true).

**What this PASS does NOT prove:**
- The GPU legs exercise ONE ADD dispatch and ONE BNE dispatch on
  representative operands — not the full 42-instruction trace on the
  GPU (composition is host-side by design; per-insn GPU execution of
  the whole program is later-phase scope).
- BNE not-taken and offset-multiple-of-4 guards are unit-tested at
  step 3 but not re-exercised inside the Fibonacci gate itself.
- n_steps=0 / negative n_steps corners remain unspecified/untested.
- The pin is adjudicated against a hand computation + the PS004
  fixture discipline, not against an external ISA oracle (QEMU /
  pixel-CPU cross-trace-diff is PS010+ scope).

PS007 COMPLETE — all six step-table rows have GREEN receipts. No
[J-DECISION] row blocks between here and the roadmap's next supply.
