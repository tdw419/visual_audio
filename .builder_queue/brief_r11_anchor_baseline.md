# BRIEF — R1.1 anchor workload: one full agent task completes in-guest, verified host-side

## Spec pointers (read FIRST, in this order)

1. `PRODUCT_ROADMAP.md:24-27` — R1.1 row (the gate text is the spec): "one full
   agent task completes in-guest, output verified host-side." P1 is the anchor
   workload: autonomous agent fleet, mailbox-supervised, real tasks.
2. `PRODUCT_ROADMAP.md:86-93` — standing policy hook: work executes under
   `POLICY_standing_decision_delegation.md` (ratified 2026-09-21) +
   `POLICY_decision_delegation_20260918.md` (in force). Floors on every rate,
   RED legs at landing, never weaken a live guard.
3. `systems/GH26_AGENT_IN_THE_LOOP_SPEC.md` — the box-citizen agent mechanism
   that already exists and passes its gates.

## Task (this run's step)

Produce a **R1.1 feasibility receipt + measured baseline**: run ONE complete,
real agent task end-to-end inside the guest box via the existing GH-26.4
resident mechanism (`tools/glyph_gpt/agent_resident.py`), with the output
verified from the HOST side against an independently computed expectation.
Concretely:

- Choose a deterministic task the box can actually perform with its current
  syscall surface (e.g. sort/sum/hash a fixed word array delivered via argv
  mailbox @750, result published @754). Pinned input, recorded SEED/revision.
- Drive it the way the existing tests do (host-side Python through the engine
  API or `experiments/glyph_interactive_shell.py` batch mode — either is
  acceptable; state which).
- Measure the round trip with the standing-rule-1 floor discipline: the
  adapter summary, round-trip count, and per-trip cost, measured from a
  process OTHER than the one making the claim (the `check_regime.py`
  pattern, see `396bc8ed`).
- Write the receipt to `.builder_queue/RECEIPT_R11_anchor_baseline.md`
  including: what the PASS does not prove, the floor line printed by the
  linter, and the exact repro command.

Explicitly IN scope for this step: the receipt, a new probe script
`.builder_queue/probe_r11_anchor_baseline.py`, and (if and only if the
existing mechanism cannot complete the chosen task) a MINIMAL fix inside
`tools/glyph_gpt/agent_resident.py` with its own RED→GREEN evidence.

Explicitly OUT of scope for this step: fleet scaling (R1.2), host-console
UX changes, WGSL/shader edits, anything under `tools/bare_metal_poc/`,
rung trees rung1..rung9, BM-4xx/5xx/8xx/9xx rows, TASK_BM001,
`BM905_MANUAL_LANE_STATE.md` files, protected assets (`voicebook/`,
`.rts/`, `rs_fixtures.json`).

## Scope (positive — files this step may change)

- `.builder_queue/probe_r11_anchor_baseline.py` (new)
- `.builder_queue/RECEIPT_R11_anchor_baseline.md` (new)
- `tools/glyph_gpt/agent_resident.py` (only with the conditional above;
  any change requires worktree-isolation per AGENTS.md blast-radius rule
  and its own RED→GREEN tails in the commit)

## Must-not-touch

- `tools/bare_metal_poc/**`, rung1..rung9 trees, `systems/virtio_pixel_rs*`
  bootloaders (GOVERNANCE_PROTOCOL ban; `systems/virtio_pixel_rs` exempt),
- WGSL shaders, `tools/glyph_gpt/baker.py`, `glyph_dispatch/**`,
- protected assets, BM905/BM000 lane state files.

## Gate commands

```
python3 -m pytest tests/test_gh26_resident.py tests/test_gh264c_teleop.py -q
# expected: all pass, exit 0

python3 .builder_queue/probe_r11_anchor_baseline.py
# expected: exit 0, prints VERDICT=PASS with the host-verified result and
# the floor line

python3 tools/check_regime.py
# expected: exit 0 (linter accepts the receipt's legs as above-floor)
```

## Gate clause (falsifiable)

The step is done when ALL of the following hold; any one failing = not done:

1. The probe prints `VERDICT=PASS` where the result word(s) read from the
   mailbox (@754 region) EQUAL a host-side independently computed expectation
   for the pinned input — equality checked with `==`, not eyeballed. A
   wrong result, a mailbox timeout, or a guest fault (KTICK_PC/KFAULT
   latched) must produce `VERDICT=FAIL` and exit 1.
2. The probe is DISCRIMINATING: feeding it a deliberately corrupted
   expectation (documented one-line mutation in the receipt) yields
   VERDICT=FAIL / exit 1. The RED tail is pasted literally in the receipt.
3. The receipt contains a floor line (adapter summary + round-trip count +
   per-trip cost, measured from a separate process) and `tools/check_regime.py`
   exits 0 against it.
4. `git status --short` after the run shows only the three in-scope paths
   (plus the conditional agent_resident.py edit).

## Failure evidence (RED first)

Before trusting GREEN: run the probe against a stubbed/corrupted expectation
or an unwritten result word and paste the literal failing tail into the
receipt AND the commit body. A probe that has never printed FAIL is not a
gate (standing rule 4).

## Definition of done

Receipt landed with RED tail + GREEN tail + floor line + repro command +
"what this does NOT prove" section (must state at minimum: single task, not
fleet; deterministic task, not LLM-driven; host-driven, not resident-prompted
— Tier C residency remains unbuilt). R1.1 itself is NOT declared complete by
this step; this step delivers the measured baseline that says what R1.1's
full gate still needs.

## Interfaces are LOCKED

`tools/glyph_gpt/agent_resident.py` mailbox contract (argv @750/@752, result
@754, GH-22 word semantics) is LOCKED. If it cannot express the chosen task,
file `REPAIR_PENDING_r11_task_abi.md` with options cheapest-first and HOLD —
do not redesign the mailbox.
