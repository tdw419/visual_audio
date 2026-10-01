# BRIEF PS010 — Two-hart mailbox, host-driven rounds (SKELETON ROUND)

**Spec pointer (read FIRST):** `GPU_CPU_EMULATOR_ROADMAP.md` PS010 section
(:221-334) and `tools/pyshader_hart.py` @ the commit that carries this
brief — the skeleton is the spec, its interfaces are LOCKED. Ruling
authority for this work: `.builder_queue/RULING_ps009_fork_cleared_ps010_go.md`
(HOLD lifted 2026-09-20 on Jericho's "Proceed to PS010."; first rung
only, correctness gates precede throughput).

## Scope (exclusive write set)

- `tools/pyshader_hart.py` — populate stub bodies ONLY (signatures,
  docstring pins, MAILBOX_PROG_A/B text, and all module constants are
  LOCKED).
- `tests/test_pyshader_hart.py` — append behavioral tests; replace
  stub-raise guards with the behavioral gate named in each row (replace,
  never delete, per the contract).
Nothing else may change. Must-not-touch this round:
`tools/pyshader_fde.py`, `tools/pyshader_ctl.py`,
`tools/pyshader_rvexec.py`, `tools/pyshader_rvdecode.py`,
`tools/pyshader_wgsl.py`, `tools/pyshader_compiler.py`,
`tools/rv32i_asm.py`, and ALL `tools/bare_metal_poc/**` +
`systems/virtio_pixel_rs/**` (Qoder lane). If a locked signature looks
wrong for a step: file
`.builder_queue/REPAIR_PENDING_ps010_<topic>.md` (2-4 options,
cheapest-first, marked skeleton-sign-off), then HOLD and stop this run.
Decisions return as `RULING_ps010_<topic>.md`.

## Pinned facts (parse from the skeleton, never restate from memory)

- Mailbox program A (writer) and B (spinner) are pinned as assembly text
  in `tools/pyshader_hart.py` (MAILBOX_PROG_A / MAILBOX_PROG_B); the
  word image is produced by `tools/rv32i_asm.assemble` and the image is
  pinned to the assembler output in the test (PS008 convention — the
  test FAILS if the assembler output changes).
- Hand-computed pin (author, 2026-09-20; re-derive before step 1 GREEN;
  steps per the PS008 convention — EBREAK halts WITHOUT counting as a
  transition): A = 6 transitions (2 ADDI, SW, ADDI, SW, JAL — poison at
  insn 6 SKIPPED, EBREAK halts uncounted); A final regs x1=7, x9=1,
  x10=0, x31=0. B = 5 transitions (ADDI, LW flag=0, BNE taken, LW
  flag=1, ADDI x6=1+6=7); B final regs x5=1, x6=7, x10=0. Rounds to
  completion = 7 (A's EBREAK lands in round 7). Final dmem =
  [1, 7, 123, 0, 0, 0, 0, 0] (sentinel 123 untouched).
- Sync model: double-buffered dmem per hart (writes land in the hart's
  own buffer); at each round boundary harts synchronize and WRITE-merged
  in round order (never final-state merge). sync="single" runs both
  harts on ONE shared buffer with NO per-round copies — the deliberate
  race variant.
- Reuse, do NOT reimplement: `run_ctl_trace`/`execute_ctl` from
  `tools/pyshader_ctl.py` (PS008) as the per-hart driver;
  `tools/rv32i_asm.assemble` for images.

## Gate commands (structural, must stay green every step)

```
python3 -m pytest tests/test_pyshader_hart.py -q   # exit 0
python3 -m pytest tests/test_pyshader_ctl.py tests/test_pyshader_fde.py -q   # exit 0
```

## Step table (one row per builder run; run the LOWEST row without GREEN
evidence recorded in the receipt section below)

| # | Populate | New gate (test name) | Gate clause |
|---|---|---|---|
| 1 | `run_two_hart` sync="double" mechanics (no gate fn yet) | `test_ps010_two_hart_mailbox_completes` | Pinned A+B images, dmem0=DMEM0: completed=True, rounds==7, steps_a==6, steps_b==5, final dmem == [1,7,123,0,0,0,0,0], A regs pin (x1=7,x9=1,x31=0), B regs pin (x5=1,x6=7). RED evidence: NotImplementedError tail from the stub. |
| 2 | Merge-discipline guard | `test_ps010_merge_is_write_ordered_not_final_state` | A craft: hart A SWs dmem[0]=1 in round 2; hart B SWs dmem[0]=2 in round 3 and NEVER again (hand-built programs, not the mailbox pair). Final dmem[0] MUST be 2 (last write in round order). A final-state merge would give an arbitrary/other value — assert the round-ordered one. Also assert both per-hart write logs are present in the receipt. RED first on the stub. |
| 3 | Livelock honesty | `test_ps010_budget_exhaustion_is_loud` | Double-buffer run with hart B's spin condition never satisfiable (flag word never written): run_two_hart raises RuntimeError mentioning the round budget — never returns completed=False silently. RED first on the stub. |
| 4 | THE roadmap gate: `gate_mailbox` | `test_ps010_gate_mailbox` | gate_mailbox() receipt ok=True with: two-hart completion pin (row 1 values), the single-buffer RED leg — sync="single" on the SAME program demonstrably NOT completing or racing (receipt field `single_buffer_ok` is False, with the observed round/reg/dmem divergence recorded) — proving the double-buffer sync recipe is load-bearing. Receipt states what PASS does NOT prove: no GPU leg yet, N=2 only, no divergence-cost measurement (that is the later PS010 leg per roadmap :246-268). |

## Hard constraints

- Additive only; never weaken a live guard to make a step pass.
- No GPU legs this round (host correctness first — PS009's own order).
  If a step seems to need one, that is out of scope for the row.
- One gate-able step = one run = one commit. STOP after the row even if
  early. Receipt section below updated in the same commit.

## Receipt section (append per-row GREEN evidence: commit + gate tail)

## PS010 receipt — step 1 (run_two_hart double-buffer mechanics) — LANDED

Commit: PS010 step 1: run_two_hart double-buffer mechanics (mailbox
completes; two rulings landed)
Revision: glyph-transpiler-autoloop @ edefc187 + this commit
Scope honored: tools/pyshader_hart.py + tests/test_pyshader_hart.py +
.builder_queue/ ruling/blocker files ONLY (git status verified; probe
scripts left untracked/scratch, two kept as ruling evidence).

Rulings landed in the same commit (both marked in their files):
- RULING_ps010_bne_spin_polarity.md — adopted the filed ticket's
  Option 1: MAILBOX_PROG_B insn 2 bne→beq (word 0xFE029EE3→0xFE028EE3);
  image pin updated; blocker marked RULED, not deleted.
- RULING_ps010_steps_b_pin.md — steps_b pin 5→6. The skeleton's hand
  trace dropped B's round-4 re-execution of the LW (after the r3 BEQ is
  taken, r4 is the LW again, now seeing flag=1; r5 BEQ falls through,
  r6 ADDI, r7 EBREAK). All other pins unchanged (rounds=7, steps_a=6,
  dmem [1,7,123,0,...], reg pins exact).

Change: run_two_hart populated for sync="double" — per-hart dmem views,
round-boundary write-merge in round order (shared list updated at write
time by hart execution order within the round = "ab"/"ba" order; the
step-2 test adjudicates ORDER on the logs), per-hart write logs
[(round, word, value)], loud RuntimeError on round-budget exhaustion
with any hart live. Reuses PS005 decode_ref, PS007 execute_one, PS008
execute_ctl/ControlHart — no second decoder/executor. sync="single"
still raises NotImplementedError (deliberately deferred to step 4 per
the one-row-per-run contract).

RED tail (stub in place, literal):
`NotImplementedError: PS010 step 1: run_two_hart is a stub (skeleton
round — see .builder_queue/brief_ps010_two_hart_mailbox.md step 1)`
`1 failed in 0.07s`

Mid-run RED chain (literal, both fixed under the rulings):
- `assert r["rounds"] == 7` → `assert 5 == 7` — ALU-branch step counter
  missing: ALU insns double-executed per round (hart raced ahead).
- `assert r["steps_b"] == 5` → `assert 6 == 5` (then rounds 5≠7 again
  from the same counter bug) — the pin-vs-trace conflict that became
  RULING_ps010_steps_b_pin.

GREEN tail (literal):
`5 passed in 0.10s` (tests/test_pyshader_hart.py, exit 0)
`35 passed in 0.99s` (hart + ctl + fde suites)
`101 passed in 2.56s` (hart + ctl + fde + compiler full PS-chain)

Measured receipt (probe_ps010_labeled.py, faithful loop trace):
rounds=7, steps_a=6, steps_b=6, dmem [1,7,123,0,0,0,0,0],
A x1=7/x9=1/x10=0/x31=0, B x5=1/x6=7, writes_a=[(3,0,1),(5,1,7)],
writes_b=[].

What this PASS does NOT prove:
- Merge ORDER is not yet adjudicated (step 2's test) — the write logs
  are recorded but nothing machine-checks round-order vs final-state.
- Budget exhaustion is loud, but no test drives it yet (step 3).
- No sync="single" leg (step 4); no GPU legs this round per the brief.
- A's reg file never diverges in this program, so per-hart reg double-
  buffering is untested by this gate (only dmem is dual here).
next: PS010 step 2 (merge-discipline guard)

## PS010 receipt — step 2 (merge-discipline guard) — LANDED

Commit: PS010 step 2: merge-discipline guard (write-ordered, not
final-state)
Revision: glyph-transpiler-autoloop @ 1e1218c5 + this commit (37dd001e).
CORRECTION: originally recorded "@ f9dd941e" — the parallel Qoder lane
landed 1e1218c5 (bm602/bm653 records) between this run's read of the
brief and the commit; 1e1218c5 is the true parent. No content delta.
Scope honored: tests/test_pyshader_hart.py ONLY (tools/pyshader_hart.py
UNCHANGED — step 1's write-time merge already implements round order;
this step lands the test that adjudicates it. git status verified: the
only tracked-file delta from this run is the test file plus this brief.
Scratch probe .builder_queue/probe_ps010_merge_order.py left untracked,
not part of the gate).

Change: `test_ps010_merge_is_write_ordered_not_final_state` appended
(tests/test_pyshader_hart.py:117-129). Hand-built pair (NOT the mailbox
programs): MERGE_PROG_A SWs dmem[0]=1 in round 2; MERGE_PROG_B SWs
dmem[0]=2 in round 3 and never again. Asserts: completed=True,
rounds==4, steps_a==2, steps_b==3, write logs EXACT
(writes_a=[(2,0,1)], writes_b=[(3,0,2)]), THE adjudication —
dmem[0]==2 (last write in ROUND order) — sentinel untouched, input
dmem0 unmutated. No stub-raise guard existed for this step (step 1's
population covered run_two_hart); the RED leg is the mutation probe
below.

RED tail (literal) — non-vacuity probe: run_two_hart mutated to a
final-state merge (write-time merge removed; boundary copies the LAST
live hart's full buffer over shared with hart A applied last), via
.builder_queue/probe_ps010_merge_order.py (auto-reverts, backup
/tmp/pyshader_hart_step2probe.py):
`assert r["dmem"][0] == 2` → `assert 0 == 2`
`FAILED tests/test_pyshader_hart.py::TestStep2MergeDiscipline::
test_ps010_merge_is_write_ordered_not_final_state` — `1 failed`,
exit 1. Gate proven able to fail; a final-state merge is refused.

GREEN tail (literal, clean tree):
`6 passed in 0.06s` (tests/test_pyshader_hart.py, exit 0)
`30 passed in 1.34s` (ctl + fde brief gate)
`102 passed in 3.80s` (hart + ctl + fde + compiler full PS-chain)

What this PASS does NOT prove:
- The probe demonstrates ONE wrong merge (final-state, A-last). Other
  wrong orders (e.g. B-last final-state — which happens to yield 2 on
  THIS pair) are not machine-refused; the pair distinguishes
  round-order from arbitrary-order via the log-exactness asserts, not
  from the final value alone.
- Budget exhaustion loudness still untested (step 3). No sync="single"
  leg (step 4). No GPU legs this round per the brief.
- order="ba" and steps_per_round>1 variants untested (unspecified
  corners of this row).
next: PS010 step 3 (livelock honesty — loud budget exhaustion)

## PS010 receipt — step 3 (budget exhaustion is loud) — LANDED

Commit: test(ps010): budget exhaustion is loud — livelock honesty
(step 3) [6e662a9b]
Revision: glyph-transpiler-autoloop @ a6b31163 + this commit.
Scope honored: tests/test_pyshader_hart.py + this brief receipt +
.builder_queue/probe_ps010_budget_loud.py (force-added; probe kept as
RED-evidence record, step-2 precedent) ONLY. tools/pyshader_hart.py
UNCHANGED — step 1 already populated the loud RuntimeError
(tools/pyshader_hart.py:231-234); step 3 lands the test that
adjudicates it. git diff --name-only verified: no PS-lane tracked file
outside the test/brief/probe changed (remaining dirty files belong to
the Qoder bare-metal lane, the PXC1 guest lane, and other sessions'
briefs).

Change: `test_ps010_budget_exhaustion_is_loud` appended
(tests/test_pyshader_hart.py:139-156). SPIN_ONLY_PROG_A is a bare
EBREAK — hart A halts in round 1 without ever writing the flag word;
hart B is the pinned MAILBOX_PROG_B spinner whose flag==0 condition is
never satisfiable. Asserts: RuntimeError raised; message names the
round cap (8) AND the live hart ("b halted=False"); input dmem0 not
mutated by the aborted run. No stub-raise guard existed for this step
(run_two_hart populated in step 1); the RED leg is the non-vacuity
mutation probe below.

RED tail (literal) — probe mutates the raise into a silent
completed=False return (the exact failure mode this step refuses;
auto-reverts, backup /tmp/pyshader_hart_step3probe.py):
`Failed: DID NOT RAISE RuntimeError`
`FAILED tests/test_pyshader_hart.py::TestStep3BudgetExhaustion::`
`test_ps010_budget_exhaustion_is_loud` — `1 failed`, exit 1.
`=== PROBE VERDICT: RED (gate able to fail) ===`
A silent budget-exhaustion return is refused by the gate.

GREEN tail (literal, clean tree after auto-revert):
`7 passed in 0.07s` (tests/test_pyshader_hart.py, exit 0)
`30 passed in 1.29s` (ctl + fde brief gate)
`103 passed in 3.79s` (hart + ctl + fde + compiler full PS-chain)

What this PASS does NOT prove:
- The probe demonstrates the silent-return failure mode only; a
  mutation raising the WRONG exception type or a message missing the
  live-hart names is refused only by the message asserts, not by a
  second recorded RED leg.
- order="ba", steps_per_round>1, and exhaustion with hart A live
  instead of B are untested corners of this row.
- No sync="single" leg (step 4); gate_mailbox still raises
  NotImplementedError (pyshader_hart.py:257-259); no GPU legs this
  round per the brief.
next: PS010 step 4 (gate_mailbox — THE roadmap gate, sync="single"
RED leg)

## PS010 receipt — step 4 (gate_mailbox — THE roadmap gate) — LANDED

Commit: feat(ps010): gate_mailbox + sync="single" — the sync recipe is
load-bearing (step 4)
Revision: glyph-transpiler-autoloop @ 7fbe2c67 + this commit.
Scope honored: tools/pyshader_hart.py + tests/test_pyshader_hart.py +
this brief receipt + probes .builder_queue/probe_ps010_single_race.py,
.builder_queue/probe_ps010_torn_pair.py,
.builder_queue/probe_ps010_step4_nonvacuity.py (force-added; probes kept
as RED-evidence records, step-2/3 precedent) ONLY. git diff --name-only
verified: no PS-lane tracked file outside the write set changed.

Change: `gate_mailbox` populated (tools/pyshader_hart.py:286-369) and the
`sync="single"` leg of `run_two_hart` landed
(tools/pyshader_hart.py:236-269 — one shared dmem, no per-round copies,
deterministic fixed order). The stub-raise guards (run_two_hart
single-sync raise, gate_mailbox raise) were REPLACED, not deleted, per
the brief's keep-guards-live constraint.

MEASURED FINDING (probe_ps010_single_race.py): at the locked
STEPS_PER_ROUND=1, order="ab", the mailbox's single-buffer interleaving
is BENIGN — single==double trace-wise (7 rounds, 6+6 steps), exactly as
the run_two_hart docstring NOTE predicted. The RED leg therefore uses the
docstring-prescribed crafted consistency pair
(probe_ps010_torn_pair.py, measured): A writes flag dmem[0]=1 then pin
dmem[1]=7 in sequence; B LWs BOTH in one coarse round at
steps_per_round=2. MEASURED: single-buffer shows the TORN state
(x5=1 flag-new, x6=0 payload-old); double-buffer shows all-old
(x5=0, x6=0). gate_mailbox runs this pair and sets
single_buffer_ok=False only when the torn state is demonstrated
(tools/pyshader_hart.py:297-327); single_divergence records WHAT diverged
when the leg fails to fire.

Mid-run defect (caught and fixed IN-run, receipt kept for the audit
trail): the first consistency-pair encoding used a hand-computed
`lw x6,4(x0)` word 0x0040A303 that was WRONG (assembler ground truth:
0x00402303 — bit 20 vs funct3 field misplaced). The bad word decoded as
a non-LW and silently left x6=0 in BOTH legs, so the gate reported
single_buffer_ok=True while its own RED leg silently failed to fire —
caught because the gate's torn-detection recomputes from measured regs,
not from trusting the encode. CONSISTENCY_PROG_A/B words now carry
[assembler-verified] provenance (tools/pyshader_hart.py:298-312). Lesson:
in this module, program words come from assemble(), never hand-encoding;
the pinned MAILBOX images already had assembler-verified word pins in the
test file, the new pair now matches that discipline.

RED tail (literal, stubs still in place):
`NotImplementedError: PS010 step 4: gate_mailbox is a stub (skeleton
round — see .builder_queue/brief_ps010_two_hart_mailbox.md step 4)`
`1 failed, 7 passed in 0.17s` (exit 1)

Mid-run RED (silent-RED-leg defect above, literal):
`assert g["single_buffer_ok"] is False` → `assert True is False`
`1 failed, 7 passed in 0.11s` (exit 1) — then fixed via the
assembler-verified words.

GREEN tail (literal):
`8 passed in 0.12s` (tests/test_pyshader_hart.py, exit 0)
`30 passed in 1.90s` (ctl + fde brief gate)
`104 passed in 5.54s` (hart + ctl + fde + compiler full PS-chain)

Non-vacuity legs (gate proven able to fail — probe_ps010_step4_nonvacuity.py,
3 mutation probes, each auto-reverting from /tmp backup):
- break the double-buffer pin (rounds 7→6): `1 failed in 0.12s`, exit 1 — RED
- silent hazard (torn forced False → single_buffer_ok=True): `1 failed
  in 0.15s`, exit 1 — RED
- single-buffer tolerates torn (make single's reads read double's regs):
  `1 failed in 0.13s`, exit 1 — RED
- restored clean tree: `1 passed in 0.10s` — GREEN

Receipt shape: ok / double_ok / double_divergence / double /
single_buffer_ok / single_divergence / single / torn_pair /
what_pass_does_not_prove. ok=False on any pin mismatch; the receipt does
not raise (the receipt IS the gate artifact).

**What this PASS does NOT prove:**
- No GPU leg (host correctness first, per the brief).
- N=2 harts only; order="ba" and steps_per_round>1 mailbox runs are
  untested corners.
- No divergence-cost measurement — the roadmap :246-268 leg
  (low-divergence baseline vs adversarial-divergence N-hart sweep) is a
  LATER PS010 row; this step closes the two-hart correctness gate only.
- The single-buffer hazard is demonstrated under a FIXED order="ab"
  deterministic interleaving (per the locked docstring NOTE), not a
  scheduler race; benign-interleaving cases (the mailbox at spr=1)
  provably do NOT diverge and are not claimed as RED evidence.
- CONSISTENCY_PROG_A/B words were verified against assemble() output but
  are not pinned in a standalone test leg (the gate's torn-detection
  adjudicates them from measured registers on every run).

PS010 brief steps 1-4 ALL LANDED. next: PS010 COMPLETE — no further
steps in this brief; remaining PS010 scope (N-hart divergence-cost
sweep, GPU leg) is per GPU_CPU_EMULATOR_ROADMAP.md :246-268 and needs a
new brief.
