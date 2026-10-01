# BRIEF — R1.1 task-queue drain: one full agent task completes in-guest, host-verified

## Spec pointer (READ FIRST)

- `PRODUCT_ROADMAP.md` (RATIFIED 1827f6cb) — phase P1, rung R1.1: "Gate: one
  full agent task completes in-guest, output verified host-side."
- `.builder_queue/RECEIPT_R11_anchor_baseline.md` — the 10940dc7 baseline and
  its "What this PASS does NOT prove" list. This brief populates the first
  gap item ("R1.1 is not complete — one deterministic task, host-driven").
- `.builder_queue/PRODUCT_LANE_STATE.md` — lane ledger (STATUS: ACTIVE).
- `tools/glyph_gpt/agent_resident.py` — the resident-kernel module and its
  Bug 1-8 discipline (module docstring is the contract).

## Scope

MAY change:
- `tools/glyph_gpt/agent_resident.py` — ADDITIVE only: new queue constants,
  new `_agent_task_a_queue()`, new `mode="queue"` branches in
  `_resident_kernel_program_text()` and `resident_image()`. Existing
  `resident`/`paged`/`fault` mode behavior byte-for-byte unchanged.
- `tests/test_gh26_task_queue.py` — new gate (may be created; .gitignore
  force-add required).
- `.builder_queue/probe_r11_task_queue.py` — new probe.
- `.builder_queue/PRODUCT_LANE_STATE.md`, `.builder_queue/RECEIPT_R11_task_queue.md` —
  ledger/receipt updates at session end.

MUST NOT change:
- `tools/glyph_gpt/baker.py`, `tools/glyph_isa_v2.py`, `tools/glyph_gpt/runner.py`,
  WGSL shaders — LOCKED (if a locked signature looks wrong: REPAIR_PENDING,
  do not edit).
- Existing `tests/test_gh26_resident.py` assertions (750/752/754/717/732/733/736/755
  semantics are the compatibility contract queue mode must preserve).
- Protected assets per AGENTS.md (`voicebook/`, `.rts/`, `rs_fixtures.json`).

## Gate command

```
python3 -m pytest tests/test_gh26_task_queue.py -q          # expect: 4 passed
python3 -m pytest tests/test_gh26_resident.py tests/test_gh264c_teleop.py tests/test_bk3_signals.py tests/test_glyph_linter.py -q   # expect: 29 passed
python3 .builder_queue/probe_r11_task_queue.py              # expect exit 0, VERDICT=PASS
python3 .builder_queue/probe_r11_task_queue.py --corrupt    # expect exit 1, VERDICT=FAIL
```

## Gate clause

- `tests/test_gh26_task_queue.py` writes nothing outside pytest; it PASSES
  (exit 0, "4 passed") iff: 3 seeded jobs (7,11,13) appear tripled
  (21,33,39) in slots 756..758; mailbox depth @740 drains to 0 in memory;
  receipt 0x5EED0003 lands @759; kernel status = 0xCAFE0026; done flags
  @717 == 3; and the quantum=6 leg proves ticks were serviced mid-loop
  with identical results. It REFUSES (exit 1) when any slot, the depth
  word, the receipt, or the status word deviates; and its third test
  asserts a corrupted expectation set IS rejected (discriminating).
- The probe REFUSES (exit 1) unless the CPU queue-drain leg passes
  word-by-word; `--corrupt` shifts expectations +1 and must flip it to
  VERDICT=FAIL exit 1.
- Full regression (29 pre-existing tests) must stay GREEN — queue mode is
  additive; any regression means the queue branches leaked into other modes.

## RED-first / failure evidence (must be DISCRIMINATING)

- The probe's `--corrupt` leg IS the negative leg: run it BEFORE trusting a
  green; it must print VERDICT=FAIL and exit 1.
- The test file's `test_gh26_queue_gate_can_fail` embeds the discrimination
  inline (corrupted expectation must be rejected; zero-state image must not
  pass the drained check).
- Linter (`tools/glyph_linter.py`) on `agent_resident.py` must stay at
  0 errors — tick-isolation contract (no r25-r28 in task bodies).

## Determinism clause

CPU legs are fully deterministic (same image bytes -> same final memory;
the canonical replay fixpoint test in test_gh26_resident.py already pins
this property for resident images). The WGSL floor line in the probe is a
RECORDED DATUM ONLY: `floors_authoritative.json`'s `step` floor measures
`SpatialRV32ICore.step()` (4 blocking readbacks/call) — a different code
path from this probe's GlyphRunner WGSL loop (1 dispatch + 1 blocking
readback per step). The floor check CANNOT be adjudicated for this path;
expect check_regime.py to call the line INADMISSIBLE and treat that as the
expected units-mismatch datum, not a gate failure. GPU presence is not
required for the gate: `--skip-gpu` runs the gating CPU leg alone.

## Interfaces LOCKED

`resident_image(atlas, mode=..., timer_quantum=..., out_path=...)` signature
is unchanged; `mode="queue"` is a new value of the existing parameter. The
GH-18 box layout (BOX0=[700,717), BOX1=[718,735), BOX2=[736,768)) and the
mailbox words 750/752/754 are LOCKED; queue words 740/756-758/759 were
chosen inside BOX2's armed range precisely so no locked word moves.

## Definition of done

- All gate commands green (with the corrupt RED shown first).
- `RECEIPT_R11_task_queue.md` written: GREEN + RED tails pasted literally,
  floor-line adjudication honesty paragraph, what-PASS-does-NOT-prove list.
- `PRODUCT_LANE_STATE.md` session log updated; R1.1 marked COMPLETE only if
  the receipt supports the roadmap gate wording verbatim.
