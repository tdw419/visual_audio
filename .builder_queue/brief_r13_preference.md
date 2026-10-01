# BRIEF — R1.3 preference measurement (P1.3 kill switch)

## Spec pointer (READ FIRST)

- `PRODUCT_ROADMAP.md` (RATIFIED 1827f6cb) lines 41-46 — R1.3 AMENDED gate:
  GPU lane must win-or-tie on **failure rate** PLUS at least one of
  {wall-clock, cost}. Failure rate is load-bearing, not interchangeable.
- `.builder_queue/PRODUCT_LANE_STATE.md` — lane ledger (STATUS: ACTIVE);
  R1.2 entry names R1.3 as next unit.
- `.builder_queue/POLICY_standing_decision_delegation.md` — rules 1-4.
- Cron af3e62239ce2 prompt — P1.3 KILL SWITCH verbatim section.

## Scope

MAY change:
- `.builder_queue/probe_r13_preference.py` — new probe (additive file).
- `.builder_queue/probe_r13_wgsl_fleet.py` — WGSL divergence datum probe.
- `.builder_queue/RECEIPT_R13_preference.md` — receipt.
- `.builder_queue/PRODUCT_LANE_STATE.md`, `.builder_queue/PRODUCT_ROADMAP.md`
  status line — only on a measured PASS or FAIL verdict.
- `tests/test_r13_preference_gate.py` — optional gate wrapper.

MUST NOT change:
- `tools/glyph_gpt/agent_resident.py`, `tools/glyph_gpt/runner.py`,
  `tools/glyph_gpt/baker.py`, `tools/glyph_isa_v2.py`, WGSL shaders —
  the measurement runs against the LANDED R1.2 artifacts unmodified.
- Protected assets per AGENTS.md.
- RULING/RECEIPT files other than the new R1.3 receipt.

## Gate command

```
python3 .builder_queue/probe_r13_preference.py            # exit 0
python3 .builder_queue/probe_r13_preference.py --corrupt  # exit 1 (RED)
python3 .builder_queue/probe_r13_preference.py --naive    # exit 1 semantics
```

## Gate clause

- GREEN: GPU fleet lane completes 20/20 batches with 0 failures
  (results 6/12/20/30, B's slot not 0xDEAD, C faulted+reaped, receipt
  0x5EED0005); verdict computed from the AMENDED rule and printed.
- DISCRIMINATING: `--corrupt` (corrupted expectations) MUST exit 1;
  `--naive` control MUST show the adversarial store LANDING in-guest;
  Ubuntu no-isolation control MUST show corruption landing host-side.
- Verdict direction: FAILURE RATE leg decides first; wall-clock leg
  decides the "plus one of" clause. A GPU loss on failure rate =
  FALSIFIED, per the kill-switch, with no re-sampling.

## Failure evidence

All three RED legs above are demonstrated at landing time (tails in
RECEIPT_R13_preference.md). check_regime.py --leg / --self-test proven
able to reject. A PASS whose controls didn't first demonstrate they can
fail is not evidence.
