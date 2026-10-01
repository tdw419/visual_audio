# RECEIPT — round-3 item 8: RUN-lane twin-status truthing (spec + rot-guard, no engine code)

**Builder:** cron af3e62239ce2, 2026-09-22, branch glyph-transpiler-autoloop @ 0e351c21
**Spec read first:** `.builder_queue/PRODUCT_LANE_STATE.md` item 8 (lines 382-390);
`docs/SYSCALL_ABI_SPEC.md`; `tools/wgsl_glyph_isa_v2.py:807,829`; `tests/test_pillar21_abi_spec_rotguard.py`.

## The measurement (both engines, live; GPU twin = Intel ARL iGPU via Vulkan, GlyphRunner.run_wgsl)

Probe: `.builder_queue/probe_item8_run_lane_twin_status.py` (empty path r1=0,
no GLYPH_RUN_ALLOW → Python returns the containment refusal -1 on 0x07/0x12):

```
0x03 FILE_WRITE  python=  -1 twin=  0 (u32=0)  DIVERGENT   (spec said STUB-0 — correct)
0x04 FILE_READ   python=  -1 twin=  0 (u32=0)  DIVERGENT   (spec said STUB-0 — correct)
0x07 RUN         python=  -1 twin= -1 (u32=4294967295)  PARITY  (spec said UNIMPLEMENTED/-1 — correct)
0x12 RUN2        python=  -1 twin=  0 (u32=0)  DIVERGENT   (spec said UNIMPLEMENTED/-1 — WRONG)
```

Root cause of the 0x12 lie: 18 decimal falls inside the twin's GeOS
reserved-range bridge `syscall_num >= 16u && syscall_num <= 255u` → returns 0
(a FALSE spawn-success: indistinguishable from "child exited 0"). The old
spec claimed "no branch — returns -1", which is source-true (there IS no
`syscall_num == 18u` branch) but behaviorally false — and the rot guard's L3
leg could not catch it because L3 only greps for standalone branches.

## The decision (per syscall; ledger item 8's option (a)/(b) framework)

- **0x07** — option (a): "twin returns -1" codified as the NORMATIVE twin
  contract (host process spawn is foreign to the shader threat model;
  containment is the Python engine's job). True today, measured PARITY.
- **0x12** — option (b): the twin's 0 is a MEASURED defect, not a contract.
  Spec corrected to `twin: BRIDGED` + `twin_contract: GAP-ITEM8-0x12-bridge-exclusion`
  with the divergence named loudly; ticket
  `.builder_queue/TICKET_ITEM8_0x12_bridge_false_success.md` filed with the
  bounded fix (one-line bridge exclusion → unknown path → -1, matching 0x07).
- **0x03/0x04** — option (a): stub-0 codified as the NORMATIVE twin contract
  (no host FS exists on the shader path; SE021 glyph-sh v2 exec runs on the
  Python engine; no on-shader exec lane consumes file I/O today). The "IF
  glyph-sh v2 exec needs them on-shader" condition was evaluated: it does not.

## Landed

1. `docs/SYSCALL_ABI_SPEC.md` — 0x12 twin status corrected (the one factual
   lie); new machine-readable `twin_contract` field (NORMATIVE/GAP) on the
   four RUN-lane + FS blocks; normative-contract prose for 0x07 and 0x03/0x04.
2. `tests/test_pillar21_abi_spec_rotguard.py` — L3.5 legs:
   - `test_l35_run_lane_twin_contract_claims` — field presence + pairing.
   - `test_l35_gap_pin_0x12_bridge_exclusion_absent` — GAP pin: spec documents
     the twin as it physically is; the ticket's landing (adding
     `syscall_num != 18u` to the bridge) turns this leg RED and forces the
     0x12 re-sync in the same commit. Also asserts the ticket file exists
     (a GAP without a ticket is an unanchored lie).
   - `test_l35_gap_pairing_python_side` — Python 0x12 branch + HOST storage
     (the divergence is genuinely twin-side).
   - `test_l35_mutated_gap_claim_is_caught` — in-memory doc mutation
     GAP→NORMATIVE makes the pairing leg RED (non-vacuity).
   - Header docstring corrected (it was right all along: 0x12 BRIDGED-0).

## Gate arc (RED first, then GREEN)

RED (new legs vs OLD spec, `git stash` of the doc): `3 failed, 21 passed`
— `test_l35_run_lane_twin_contract_claims`,
`test_l35_gap_pin_0x12_bridge_exclusion_absent`,
`test_l35_mutated_gap_claim_is_caught` all fail on the un-corrected doc.
GREEN (corrected spec): `24 passed` (tests/test_pillar21_abi_spec_rotguard.py).

## Regression

- `tests/test_pillar23_parity_ci.py` — **8 passed** (GPU corpus, both engines).
- Twin copies md5-identical and UNTOUCHED (4df41c619fa939790b0059d62142a0d1,
  tools/ and glyph_dispatch/) — no engine code changed, per the item-8 gate.

## What this PASS does NOT prove

- The twin still physically returns 0 for 0x12 — the GAP is documented, not
  fixed. The fix is ticketed (option b), deliberately not landed this item
  ("no engine code changed" is the item's own gate).
- No WGSL compile/GPU-compile leg was added for the future fix; when the
  ticket is picked up, its own gate (structural RED + behavioral PARITY +
  corpus regression) applies.
- The 0x03/0x04 NORMATIVE wording is a contract decision, not a measurement:
  what is measured is that both engines behave as documented TODAY.
