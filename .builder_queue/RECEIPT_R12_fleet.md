# RECEIPT — R1.2 fleet demo: 4 co-resident isolated agents + fault-injection RED

Lane: PRODUCT_ROADMAP.md (RATIFIED 1827f6cb), rung R1.2 — "Fleet demo:
≥4 concurrent isolated agents, no cross-tile fault propagation
(fault-injection RED leg required — see policy rule 4)."
Brief: .builder_queue/brief_r12_fleet.md (tools/check_brief.py PASS,
exit 0; two soft-field warnings pre-existing, HARD fields complete).
Session: builder cron af3e62239ce2, 2026-09-21 ~14:00 CDT.
Base HEAD: c40f8ce8 (two commits ahead of the ledger's last entry —
re-verified before acting; no parallel-session collision found in the
fleet files).

## What landed

1. **Debug of the in-flight fleet work** (found DIRTY on
   `tools/glyph_gpt/agent_resident.py`, +369/−12, uncommitted, with
   `brief_r12_fleet.md` + throwaway probes `_dbg_r12.py` /
   `_smoke_r12.py` beside it). Two real defects, both fixed:

   - **Defect 1 — exit-PC wiring dead:** `_fleet_packed()` (agent_resident.py:709)
     stripped the label's leading `:` before looking up the coords map,
     but `assemble_glyph_to_pixels` keys coords WITH the colon
     (production `packed()` at :1316 looks up `":__g18dispatch"`).
     Every lookup missed → `(0,0)` placeholder → all four agents' exit
     `KJMP r30` targeted PC 0 (`:__entry`) → the kernel rebooted
     forever (measured pre-fix: 200 000 steps, never halts, all fleet
     words 0). Fix: one token — look up `label` as-is.
   - **Defect 2 — D's done bit never lit:** the body wiring sent the
     LAST agent's exit straight to `:__fleetfin` (:1195), skipping its
     own promote block `:__fret3` — the block that sets bit 3 of 717
     and falls through to `:__fleetfin` anyway. Measured post-fix-1:
     done=0b0011, receipt already correct. Fix: every agent (including
     slot 3) returns to its own `:__fret<slot>`; fret3 falls into
     `:__fleetfin` as the dispatch-leg layout already arranged.

2. **`.builder_queue/probe_r12_fleet.py`** — new probe, legs:
   fleet GREEN, `--corrupt` (expected-B shift +1 → FAIL exit 1),
   `--naive-clean-expected` (control must corrupt → FAIL exit 1 if it
   does, matching the brief's decoration-guard requirement).

3. **`tests/test_gh26_fleet.py`** — new gate, 5 tests (force-added past
   .gitignore:101): isolation, naive control, corrupt-expectation RED
   (in-process non-vacuity), preemption non-vacuity (ticks>0 at
   quantum 6), naive-must-corrupt mirror.

4. **Ledger update** — .builder_queue/PRODUCT_LANE_STATE.md session
   entry appended.

## Gate evidence (all run THIS session, this tree)

### RED first (pre-fix, both defects live) — `_smoke_r12.py` literal tail

```
  mode: fleet
  halted: False
  steps: 200000
  714_A_result: 0
  728_B_result: 0
  748_C_result: 0
  763_D_result: 0
  717_done: 0
  731_fault_receipt: 0x0
  765_receipt: 0x0
```

(also, after fix 1 alone: `717_done: 3` in fleet — defect 2's RED —
and `717_done: 7` in fleetnaive.)

### RED leg — pytest caught the gate's own assertion inversion

Leg 5 of the new test file was first written with the comparison
inverted (`== 12` instead of `== 0xDEAD`): the suite went RED on
`test_gh26_fleet_naive_clean_is_failure` before any green run of it —
literal tail: `1 failed, 4 passed in 0.89s`. Fixed the test; the gate
demonstrated it can fail before being trusted.

### GREEN — full gate suite, literal tails

```
$ python3 -m pytest tests/test_gh26_fleet.py -q
.....                                                                    [100%]
5 passed in 0.87s

$ python3 -m pytest tests/test_gh26_task_queue.py tests/test_gh26_arrive.py \
    tests/test_gh26_resident.py tests/test_gh264c_teleop.py \
    tests/test_bk3_signals.py tests/test_glyph_linter.py -q
......................................                                   [100%]
38 passed in 1.58s

$ python3 .builder_queue/probe_r12_fleet.py
CPU fleet: halted=True steps=434 results={714: 6, 728: 12, 748: 20, 763: 30} expected={714: 6, 728: 12, 748: 20, 763: 30} done=0b1011 (want 0b1011) fault=0xfa026 fleet_rcpt=0x5eed0005 ticks=7 status=0xcafe0026
VERDICT=PASS (four co-resident agents, cross-tenant store suppressed E-K1, fleet continues, host-verified)
EXIT=0

$ python3 tools/glyph_linter.py tools/glyph_gpt/agent_resident.py
glyph_linter: clean (0 errors, 1 warning(s))
EXIT=0
```

(linter warning: program is 1003 instructions > 128 cells; canvas bake
auto-expands to 126 rows — informational, not a gate failure.)

### RED legs (demonstrated, expected exit 1)

```
$ python3 .builder_queue/probe_r12_fleet.py --corrupt
CPU fleet: ... expected={714: 6, 728: 13, ...}
CORRUPT-LEG: expectation did not match (correct RED)
VERDICT=FAIL failures=['cpu:results']
EXIT=1

$ python3 .builder_queue/probe_r12_fleet.py --naive-clean-expected
NAIVE-CLEAN-EXPECTED RED: naive image DID corrupt (728=0xdead) — the control leg shows its expected landing, so this probe's FAIL verdict stands (exit 1 = expected RED).
VERDICT=FAIL failures=[naive:control-corrupted-as-expected]
EXIT=1
```

## The falsifiable isolation claim (the rung's substance)

Identical agent bodies, identical adversarial store (C's USER store of
0xDEAD to B's result word 728), ONLY the arming discipline differs:

| | fleet | fleetnaive |
|---|---|---|
| arming | per-leg ( disarm-all → arm current agent) | boot-time arm-all, never re-armed |
| C's store to 728 | E-K1, suppressed, receipt 0xFA026 @731 | LANDS, 728 = 0xDEAD |
| 728 after run | 12 (B intact) | 57005 (corrupted) |
| done 717 | 0b1011 (C reaped) | 0b1111 (C completes) |
| B, D results | land intact AFTER the fault | B corrupted, D intact |

No cross-tile fault propagation in fleet mode: the suppressed store did
not abort, stall, or contaminate any neighbor; the fleet completed at
step 434 with preemption active (7 ticks at quantum 6).

## What this PASS does NOT prove (honesty list, per brief)

- **Read isolation is NOT claimed.** LD is not box-checked by the
  engine (USER STORES only) — an agent can READ a neighbor's arena.
- **Not simultaneously parallel.** The four agents are time-multiplexed
  co-resident: one PC, one register file, dispatcher legs. "≥4
  concurrent" is satisfied as co-resident interleaved execution, not
  parallel lanes.
- **The supervisor is the in-guest kernel; the seat remains the host.**
  No in-guest LLM supervisor is claimed (R1.2-scoping question still
  open).
- **No rate claims** → no floor line; check_regime N/A with that
  reason (floors_authoritative measures SpatialRV32ICore.step, a
  different code path; nothing here quotes a number).
- **WGSL twin parity not claimed** (recorded divergence halt@198,
  result 0x0, unchanged; CPU substrate only).
- **The fleet/naive contrast proves the ARming discipline is
  load-bearing in THIS image** — it does not prove no other
  isolation defect exists (e.g. a store into the tile rect from any
  arena was not probed).

## Scope audit

Changed: `tools/glyph_gpt/agent_resident.py` (in-flight fleet work +
2 defect fixes — additive fleet modes only; existing
resident/paged/fault/queue/arrive images untouched per the shared-path
discipline the full regression confirms), `tests/test_gh26_fleet.py`
(new), `.builder_queue/probe_r12_fleet.py` (new),
`.builder_queue/PRODUCT_LANE_STATE.md` (ledger),
`.builder_queue/RECEIPT_R12_fleet.md` (this file), plus the brief's
throwaway probes already on disk. Locked files (baker.py,
glyph_isa_v2.py, runner.py, WGSL shaders): untouched. Protected assets:
untouched.
