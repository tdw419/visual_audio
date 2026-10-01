# RECEIPT — Floor reconciliation and the voiding of R0's FABRICATED charge

**Landed:** 2026-09-21 ~10:47 CDT by the seat lane, on Jericho's direction,
under POLICY_standing_decision_delegation.md (the 48h-measurement-flip rule's
first live application — both directions).
**Verification method:** every claim below was re-verified first-hand from
code and files, not accepted from any report (the PS rereceipt, the Qoder
observer, or the seat-side concurrence — all three of which contained errors,
listed in §5).

## 1. What R0 (396bc8ed) got wrong — the FABRICATED charge is VOID

`R0_REGIME_RERECEIPT.md` declared the correction section of
`RULING_ps009_fork_cleared_ps010_go.md` (060a03e8) "FABRICATED — artifacts
did not exist on disk or in any commit." First-hand check:

- The cited artifacts exist: `~/Documents/Qoder/2026-09-20/c14f2b54/
  builder_watch/{calibrate_floors.py, ps009b_regime_run.py, floors.json,
  reports/PS009B_REGIME_RECEIPT_20260920.md}` — mtimes 2026-09-20 12:54-12:58,
  floors re-measured 09-21 07:44. The Qoder observer's standing boundary
  ("writes only inside builder_watch/, never into the watched repo") places
  them in its own workspace repo, which the R0 lane never searched. "Not in
  any commit [of zion]" was guaranteed true and proved nothing.
- The ruling file was never actually edited: `git log --` shows exactly one
  commit (060a03e8); its header still reads as issued. R0's "corrective
  action 1" (mark the ruling FABRICATED) was never executed against the
  file it accuses.

**Status correction:** RULING_ps009_fork_cleared_ps010_go.md was NEVER
marked FABRICATED; the charge existed only inside R0's own receipt. Any
document citing that charge must stop.

## 2. What 060a03e8's opponents got right — and what R0 got right anyway

**The units error is real (verified in code, both calibrators):**
`.builder_queue/calibrate_floors.py` measures "step" as ONE
dispatch_workgroups + ONE blocking readback of a 4-word constant-write
shader (calibrate_floors.py:92-107). The code the paired probe actually
times — `SpatialRV32ICore.step()` (tools/spatial_rv32i_cpu.py:296) — calls
`get_state()` twice (:299, :321), each issuing TWO blocking
`queue.read_buffer()` calls (:196-200): **4 round trips per step()**, plus a
write_buffer and a full pipeline dispatch. Its "get_state floor" is a bare
map_sync with no submission in flight — API overhead, not a round trip. So
R0's "285/451 µs vs 243.4 µs floor ⇒ admissible" compared a 4-readback call
against a 1-readback constant: a units mismatch, on the order of 4x. R0's
central technical conclusion does not survive.

**What survives of R0 (also true, also first-hand):** the paired-probe
re-runs were real, unmodified, and their pin checks were real; the
requirement that floors come from a separate process and be attached to
claims is sound policy form and is retained — it just needed to measure the
right quantity. And the non-stationarity finding is real: this seat re-ran
R0's own proxy calibrator twice 38 minutes apart and watched the step floor
move 243.4 → 98.6 µs (2.5x) with no intervention.

## 3. The authoritative floor (lands today)

`.builder_queue/calibrate_floors_authoritative.py` — new, committed with
this receipt. It imports the REAL classes and times the REAL methods in a
dedicated process: `SpatialRV32ICore.step(1)` / `get_state()` on the FIB
program, plus the GEN-path shader construction mirroring
probe_ps009b_paired.py. First run (2026-09-21T15:46Z, RTX 5090 Laptop,
Vulkan, 30 reps):

| floor | median | min | p10 / p90 |
|---|---|---|---|
| step(1) — real, 4 readbacks | **4,870.7 µs** | 4,387.8 | 4,553.9 / 5,252.4 |
| get_state() — real | 2,408.3 µs | 2,104.6 | — |
| GEN dispatch+map (batch=256) | 410.2 µs | — | — |

This is consistent with Qoder's independent same-morning measurement (step
median 10,098 µs on a contended GPU / mins 7,170 µs) and with the ORIGINAL
060a03e8 estimate (~3,500–4,200 µs) — and inconsistent with R0's 243.4 µs
by ~20x.

**Authority decision (Jericho, 2026-09-21):**
`floors_authoritative.json` is THE floors file for zion-repo receipts.
- 12h freshness window (not 7d) — this host's floors are non-stationary.
- `.builder_queue/floors.json` (proxy-shader floors) is superseded/dead;
  the lane is barred from re-running the proxy calibrator for gate purposes.
- Cross-repo floors (Qoder builder_watch) are not citable in zion receipts.

## 4. What this means for the PS009 numbers

**None of {6.15x, 1.42x, 0.45x} is a clean, correctly-floored datum**, and
all three are hereby barred from citation as settled. What remains
established:
- 6.15x did not reproduce in 2/2 subsequent paired attempts (real runs,
  real pins — R0 got this part right).
- The Gen-batched-vs-ModeB relationship is a DISTRIBUTION on this host
  (observed draws: 0.32–6.15), not a number. The honest datum is the spread
  plus correctly-floored admissibility per leg, which nobody has yet
  computed against the authoritative floor. That computation, when done,
  supersedes this paragraph.
- PS012's RV32-stop ruling never depended on the ratio and is unaffected.

## 5. Errors by lane, on the record

- **PS lane (R0, 396bc8ed):** wrong-repo search presented as verification;
  FABRICATED charge void; corrective action claimed but not executed;
  units-mismatched floor presented as the load-bearing gate.
- **Qoder observer:** right on the technical units claim and the void
  charge; described its artifacts as checkable "in the repo," which they
  are not (different repo); "not in any commit" was its own boundary's
  guaranteed consequence.
- **Seat lane (this lane's prior concurrence):** verified R0's artifacts
  existed and check_regime.py's RED/GREEN behavior, but never read what
  code path the floor measured — the concurrence was procedurally clean
  and substantively hollow. The policy's rule 1 (floors attached) was
  satisfied in form and failed in content; rule-enforcement must include
  "the floor measures the timed path's round-trip shape," now encoded in
  calibrate_floors_authoritative.py's `readbacks_per_step_call` field.

## 6. Actions taken

1. `calibrate_floors_authoritative.py` + `floors_authoritative.json` landed.
2. This receipt supersedes R0's FABRICATED charge (§1) and R0's floor-based
   admissibility verdict (§2); the old rereceipt file is preserved unedited,
   SUPERSEDED per policy convention.
3. check_regime.py: freshness window and floors source updated to the
   authoritative file (see companion diff in the same commit).
4. Product lane (af3e62239ce2) prompt: floors source pointed at
   floors_authoritative.json; citation ban on {6.15x, 1.42x, 0.45x} as
   settled numbers.
5. Policy afterword amendment drafted (see §7) for Jericho's ratification —
   he reserved that edit to himself or a delegated draft.

## 7. Draft afterword amendment (pending Jericho)

The policy's §3 afterword cites 396bc8ed as the proof-of-concept for the
rules. Amendment: the citation demonstrates the rules' FORM (separate-process
floors, RED legs, rereceipts) but the receipt's own floor measured the wrong
quantity and its FABRICATED charge was void — which is itself the strongest
evidence for the rules: form-compliance without quantity-correctness sailed
through two independent verifications. Proposed addition to rule 1:
*"A floor attached in form must also measure the timed path's round-trip
shape (readback count, buffer sizes, submission count). The floor's
calibration code is subject to the same verification standard as the claim
it polices."*

/s/ seat lane, 2026-09-21 · supersession chain: 060a03e8 (units right,
est. ~3.5-4.2ms) → 396bc8ed R0 (charge VOID, units wrong) → this receipt
