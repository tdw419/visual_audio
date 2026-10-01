# BRIEF — R1.2 fleet demo: 4 co-resident isolated agents + fault-injection RED

## Spec pointer (READ FIRST)

- `PRODUCT_ROADMAP.md` (RATIFIED 1827f6cb), phase P1 rung R1.2: "Fleet demo:
  ≥4 concurrent isolated agents, no cross-tile fault propagation
  (fault-injection RED leg required — see policy rule 4)."
- `.builder_queue/PRODUCT_LANE_STATE.md` — lane ledger (STATUS: ACTIVE);
  session entry ~12:1x names R1.2 as next unit.
- `tools/glyph_gpt/agent_resident.py` module docstring — Bug 1-8
  discipline is the contract for any new daemon body.
- Substrate facts (measured 2026-09-21 this session, HEAD 303e3d89):
  `_addr_in_box` (tools/glyph_isa_v2.py:740) is PER-CPU: 3 box ranges +
  1 GO-2 tile rect; unset range (HI==0) never matches (:742); only USER
  STORES are box-checked (LD is not — read-isolation is NOT claimed);
  ticks resume the same task (DEFECT-18 snapshot, :1339); fault path
  suppresses the store and vectors KFAULT_PC (:1050-1065).

## Scope

MAY change:
- `tools/glyph_gpt/agent_resident.py` — ADDITIVE only: new fleet
  constants, new `_agent_fleet_body()` (+ fault variant), new
  `mode in ("fleet", "fleetnaive")` branches in
  `_resident_kernel_program_text` (zeroing, seeding, arming, legs, fault
  routing), new pass-1 PC globals for the three new task labels, new
  `packed()` reads + `finally` resets in `resident_image()`.
  Existing `resident`/`paged`/`fault`/`queue`/`arrive` mode images
  byte-for-byte unchanged (shared paths must not reorder).
- `tests/test_gh26_fleet.py` — new gate (force-add past .gitignore:101).
- `.builder_queue/probe_r12_fleet.py` — new probe.
- `.builder_queue/PRODUCT_LANE_STATE.md`, `.builder_queue/RECEIPT_R12_fleet.md`
  — ledger/receipt at session end.

MUST NOT change:
- `tools/glyph_gpt/baker.py`, `tools/glyph_isa_v2.py`,
  `tools/glyph_gpt/runner.py`, WGSL shaders — LOCKED (if a locked
  signature looks wrong → REPAIR_PENDING + hold, do not edit).
- Existing tests' assertions, protected assets per AGENTS.md
  (`voicebook/`, `.rts/`, `rs_fixtures.json`).

## Gate commands

```
python3 -m pytest tests/test_gh26_fleet.py -q          # expect: 5 passed
python3 -m pytest tests/test_gh26_task_queue.py tests/test_gh26_arrive.py tests/test_gh26_resident.py tests/test_gh264c_teleop.py tests/test_bk3_signals.py tests/test_glyph_linter.py -q   # expect: 38 passed
python3 .builder_queue/probe_r12_fleet.py              # expect exit 0, VERDICT=PASS
python3 .builder_queue/probe_r12_fleet.py --corrupt    # expect exit 1, VERDICT=FAIL
python3 .builder_queue/probe_r12_fleet.py --naive-clean-expected  # expect exit 1 (naive MUST corrupt; if it does not, the guard is decoration)
python3 tools/glyph_linter.py tools/glyph_gpt/agent_resident.py   # expect 0 errors
```

## Gate clause

- Fleet image `mode="fleet"`: FOUR agent arenas, pairwise disjoint —
  A [700,717) argv@713 result@714 done@716; B [718,735) argv@727
  result@728 done@734; C [736,752) argv@747 result@748 done@751;
  D [752,768) argv@762 result@763 done@766. Boot seeds argv
  (A=2,B=3,C=4,D=5) as SUPER direct stores. Verbs distinct:
  A 3×→6, B 4×→12, C 5×→20, D 6×→30.
- GREEN (exit 0) iff: every result word holds ITS OWN agent's value
  (714==6, 728==12, 748==20, 763==30 — no cross-contamination);
  done word 717 == 0b1011 (A, B, D completed; C faulted mid-store);
  fault receipt 731 == 0xFA026; kernel status 0xCAFE0026; run halts.
- FAULT-INJECTION (the R1.2 RED requirement): agent C's body attempts
  a USER store of 0xDEAD to B's result word 728 — OUTSIDE C's armed
  box [736,752). Per-leg arming (dispatcher SUPER-stores BOX0_LO/HI =
  current agent's range, BOX1_HI=0, BOX2_HI=0 before each KJMP) must
  make that store E-K1-fault: suppressed (728 stays 12), C never
  completes (bit2 of 717 stays 0), B's and D's results land intact
  AFTER the fault (no propagation, no abort of the fleet).
- DISCRIMINATOR (`mode="fleetnaive"` control): identical bodies, but
  all three boxes armed at boot and NEVER re-armed. The same C store
  to 728 is then LEGAL (728 is inside armed BOX1's range): it LANDS,
  B's result reads 0xDEAD afterwards, C completes (717 == 0b1111).
  The gate FAILS (exit 1) if the naive image does NOT show the
  corruption landing — a guard that cannot be shown bypassable is
  decoration (policy rule 4).
- Preemption non-vacuity: fleet at quantum 6 → mem[732] > 0 and all
  leg-1 word assertions still hold (tick-snapshot isolation, Bug 8
  contract: fleet bodies touch no r25-r28).
- Full regression (38 tests across 6 files) stays GREEN — fleet
  branches are additive; existing modes byte-identical.

## Failure evidence (RED-first, must be DISCRIMINATING)

Before trusting GREEN: run `--corrupt` (expectation shift → FAIL) and
`--naive-clean-expected` (naive image failing to corrupt → FAIL; proves
the isolation mechanism is what separates the two outcomes, not test
luck). In-process pytest leg 4 asserts a corrupted expectation set is
rejected. The two-image fleet/naive contrast IS the falsifiable
isolation claim: same store, same body, only the arming discipline
differs — one faults, one lands.

## Definition of done

Receipt `RECEIPT_R12_fleet.md` with GREEN+RED tails pasted literally,
"what this PASS does NOT prove" list (must include: read-isolation NOT
claimed — LD is unboxed; agents are time-multiplexed co-resident, not
simultaneously parallel — one PC exists; supervisor is in-guest kernel,
seat still host; no rate claims → no floor line, check_regime N/A with
that reason), and ledger updated.

## Never weaken a live guard

If the BOX2 bounds check, box-isolation tests, or any pre-existing gate
blocks a step, the step is wrong — do not widen windows or weaken
guards to make it pass.
