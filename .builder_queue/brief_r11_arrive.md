# BRIEF — R1.1 post-boot job arrival: mailbox receive-while-busy at a running supervisor

## Spec pointer (READ FIRST)

- `PRODUCT_ROADMAP.md` (RATIFIED 1827f6cb), phase P1 rung R1.1: agent fleet
  "supervised by the seat"; `.builder_queue/RECEIPT_R11_task_queue.md`
  residual-gap item: "post-boot job ARRIVAL at a running supervisor
  (queue drain ≠ mailbox receive-while-busy)".
- `.builder_queue/PRODUCT_LANE_STATE.md` — lane ledger (STATUS: ACTIVE);
  names this exact unit as next.
- `tools/glyph_gpt/agent_resident.py` module docstring — Bug 1-8
  discipline is the contract for any new daemon body.

## Scope

MAY change:
- `tools/glyph_gpt/agent_resident.py` — ADDITIVE only: new arrive
  constants, new `_agent_task_a_arrive()`, new `mode="arrive"` branches
  (task selection + mode-conditional zeroing of the three new words).
  Existing `resident`/`paged`/`fault`/`queue` mode images byte-for-byte
  unchanged (shared code paths must not reorder).
- `tests/test_gh26_arrive.py` — new gate (force-add past .gitignore).
- `.builder_queue/probe_r11_arrive.py` — new probe.
- `.builder_queue/PRODUCT_LANE_STATE.md`, `.builder_queue/RECEIPT_R11_arrive.md`
  — ledger/receipt at session end.

MUST NOT change:
- `tools/glyph_gpt/baker.py`, `tools/glyph_isa_v2.py`,
  `tools/glyph_gpt/runner.py`, WGSL shaders — LOCKED (locked signature
  looks wrong → REPAIR_PENDING + hold, do not edit).
- Existing tests' assertions, protected assets per AGENTS.md
  (`voicebook/`, `.rts/`, `rs_fixtures.json`).

## Gate commands

```
python3 -m pytest tests/test_gh26_arrive.py -q          # expect: 5 passed
python3 -m pytest tests/test_gh26_task_queue.py tests/test_gh26_resident.py tests/test_gh264c_teleop.py tests/test_bk3_signals.py tests/test_glyph_linter.py -q   # expect: 33 passed
python3 .builder_queue/probe_r11_arrive.py              # expect exit 0, VERDICT=PASS
python3 .builder_queue/probe_r11_arrive.py --corrupt    # expect exit 1, VERDICT=FAIL
python3 .builder_queue/probe_r11_arrive.py --no-post    # expect exit 1, VERDICT=FAIL (no arrival receipt without a post)
python3 tools/glyph_linter.py tools/glyph_gpt/agent_resident.py   # expect 0 errors
```

## Gate clause

- GREEN (exit 0) iff, host-stepping the mode="arrive" image: the seeded
  queue (7,11,13) drains to (21,33,39) with depth @740 → 0 and drain
  receipt 0x5EED0003 @759; the host THEN posts one job (payload 9,
  flag @742=1) while the daemon is live in its wait loop; the daemon
  computes 3×9=27 in-place @760, posts arrival receipt 0x5EED0004 @761,
  kernel status 0xCAFE0026, done word 717 == 3. Any slot, depth,
  receipt, or status deviation → exit 1.
- The daemon's wait loop is BOUNDED (2000 polls): a run where the seat
  never posts must end with @761 == 0 and must NOT publish the arrival
  receipt — the --no-post leg fails (exit 1) if @761 is ever nonzero
  without a post (non-vacuity: proves the receipt can only come from a
  real post-boot arrival, not from boot-state or drain residue).
- --corrupt shifts the expected arrival result +1 and must flip to
  VERDICT=FAIL exit 1 (discriminating).
- Full regression (33 tests) stays GREEN — arrive branches are additive.

## Failure evidence (RED-first, must be DISCRIMINATING)

Before trusting GREEN: run `--corrupt` (expectation shift → must FAIL)
and `--no-post` (receipt-must-be-absent check inverted → must FAIL).
A gate that cannot reject a forged receipt is decoration. Additionally
the third pytest leg asserts a corrupted expectation set is rejected
in-process.

## Definition of done

Receipt `RECEIPT_R11_arrive.md` with GREEN+RED tails pasted literally,
"what this PASS does NOT prove" list, and ledger updated. No rate
claims → no floor line; check_regime recorded N/A with that reason.

## Never weaken a live guard

If the BOX2 bounds check, box-isolation tests, or any pre-existing gate
blocks a step, the step is wrong — do not widen windows or weaken
guards to make it pass.
