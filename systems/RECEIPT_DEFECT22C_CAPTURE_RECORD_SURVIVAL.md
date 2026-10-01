# RECEIPT — DEFECT-22c: the capture runner's verdict survives a scope OOM

**Date:** 2026-09-13 (builder cron `af3e62239ce2`, tick ~13:15–13:30 CDT)
**Base revision:** `9ef7b49` (the sibling fix for `tools/arc_lega.sh`)
**Changed file:** `tools/arc_lega_capture.sh` (+22 / −4)
**New gate:** `tools/gate_arc_lega_capture_record_survival.sh` (exit 0 = all legs pass)
**Falsifier/evidence:** `output/d22c_capture_record_survival_gate.txt`, `/tmp/d22c_pre_change_capture_gate.txt`,
`/tmp/d22c_telemetry_rerun.txt`

## The property

A leg-A **capture** run killed by the kernel OOM killer inside a scope with `OOMPolicy=kill` must still leave a
parseable machine-readable record naming its seed and head. Before this change it left **nothing**: the sidecar
was written only by the parse step *after* GDB returned, and the kill takes the writing shell with it.

This is the follow-on named in
`systems/RECEIPT_DEFECT22_PRESSURE_CLASS_AND_RECORD_SURVIVAL.md` § "What this PASS does NOT prove", bullet 3, and in
`.builder_queue/DEFECT-22_arc_legA_instability.json` (`record_loss_fixed_2026_09_13_1310`, NOT-fixed clause). The
sibling fix for `tools/arc_lega.sh` (commit `9ef7b49`) used the same shape; this tick applies it to the capture
runner and mirrors the gate.

## The fix (one gate-able step)

`tools/arc_lega_capture.sh`:

1. **Start record**, written with `printf` (not `$PY` — a third interpreter call shape would need a new route in the
   stub-PY naming legs) immediately after `T0`/`START_ISO` and **before** the GDB invocation:
   `{"state": "RUNNING", "seed": …, "head": …, "started_utc": …, "rc": null, "crashes": null, "note": "start record …"}`.
2. **`"state": "DONE"`** added to **both** terminal writers (the dry-run writer and the parse-step writer); every other
   key and every printed line format unchanged.
3. **The instrument-failure guard is tightened, not loosened** (`:382-387`): it used to pass on file existence
   (`[ ! -s "$JSON" ]`), which after this change would green a start-record-only file. It now requires the terminal
   record — `[ ! -s "$JSON" ] || ! grep -q '"state": "DONE"' "$JSON"` → loud `FATAL` on stderr, `exit 2`, and the
   verdict line is never printed. A file left in `state="RUNNING"` is by definition a lost or failed run, not a
   verdict.

## Gate legs and their measured output (literal tails)

```
-- L0 premise: pinned pre-fix runner (9ef7b49) lacks the start record
   L0 PASS: pinned copy has no 'state": "RUNNING"', working tree does
-- L1 RED: pre-fix runner under MemoryMax=1200M OOMPolicy=kill
   systemd-run rc=137  sidecar_count=0 (expected 0)
   L1 PASS (RED observed): the property is genuinely absent pre-fix
-- L2 GREEN: working-tree runner, identical scope and params
   systemd-run rc=137  sidecars=1  sidecar=/tmp/gate_d22c_survival.4D2RXE/out_fix/arc_lega_capture_seed2026091307_9ef7b49.json
   L2 PASS: killed run left state=RUNNING seed=2026091307 head=9ef7b49 started_utc=2026-09-13T18:25:06Z
-- L3 instrument-failure: parse failure refuses verdict (exit 2) while sidecar survives in state=RUNNING
   rc=2 (expected 2)
   L3 PASS: parse failure refused verdict with exit 2 and FATAL log; sidecar survived in state=RUNNING
-- L4 no-regression: TELEMETRY_ONLY=1 dry run and landed gates
   dry run rc=0  sidecar_count=1  sidecar=/tmp/gate_d22c_survival.4D2RXE/out_dry/arc_lega_capture_seed1_9ef7b49.json (expected rc=0, one sidecar)
   L4 dry-run PASS: state=DONE dry_run=True rc=None
   gate_arc_lega_naming.sh rc=0
   gate_arc_lega_telemetry.sh rc=0
   gate_arc_lega_record_survival.sh rc=0
   gate_arc_lega_capture.sh rc=0
   L4 PASS: dry run valid and all 4 landed gates exit 0
-- L5 non-vacuity: removing start record from working-tree copy reproduces record loss (sidecar_count=0)
   systemd-run rc=137  sidecar_count=0 (expected 0)
   scratch copy md5 before: c4599c0f5031c2d5e4e515afb8ef7a66
   scratch copy md5 after:  c4599c0f5031c2d5e4e515afb8ef7a66
   L5 PASS: non-vacuity confirmed (record loss reproduced when start record is stripped; md5s match)

GATE rc=0 — capture record survival: RED observed pre-fix, GREEN post-fix, refusal on parse failure, non-vacuous, dry-run contract intact
```

**RED-first, not asserted:** L1 is the falsifier — the same command against the pinned pre-fix revision genuinely
loses the record (`sidecar_count=0`), and L5 reproduces that loss from the working tree with the start record
stripped, so L2 is not a tautology. Both md5s are printed and match, proving the probe copy was restored
byte-identical.

**L4 also re-runs the real capture runner end to end:** `tools/gate_arc_lega_capture.sh` (rc=0) exercises
`tools/arc_lega_capture.sh` itself under GDB with its stub-PY and crasher legs — so the changed script is covered by
a landed gate, not only by this new one.

## One-off flake observed and dispositioned (not hidden, not attributed to this change)

The first full gate run (13:22) exited **1**, and the failure was **not** in any leg of this change: the delegated
`gate_arc_lega_telemetry.sh` returned 1 because its internal `gate_arc_lega_capture.sh` leg came back 1 on **its**
L6 (`L6 FAIL: falsifier vacuous — the deliberate crasher wrote no apport report`). Two-arm disposition, same tree,
minutes apart:

| arm | capture gate |
|---|---|
| working tree, via the telemetry gate (13:22) | rc=1 — L6 FAIL (no apport report written) |
| **pre-change** `arc_lega_capture.sh` (from HEAD) | rc=0, L6 PASS, md5 `990635d22e4e553a92a463f950c7df53` |
| post-change, telemetry gate re-run | rc=0 |
| post-change, full gate L4 + final full-gate run | rc=0, rc=0 |

So the L6 apport falsifier failed **once in four capture-gate runs**, on an environment-dependent condition (the
crasher's report not landing in `/var/crash` — the suppression class `tools/arc_lega_capture.sh` itself documents
in its hygiene header), and it is **not** attributable to this change: the pre-change arm passed and every
post-change arm passed. **n is four observations — not a rate.** Filed as
`.builder_queue/REPAIR_PENDING_d22c_apport_falsifier_flake.md` rather than weakened here: `gate_arc_lega_capture.sh`
L6 should report SKIP (not FAIL) when the apport path is occupied, which it already does for the *pre-existing
report* case but not for the *no report at all* case.

## What this PASS does NOT prove

* It does **not** fix the OOM and does not make the arc fit its cap — it preserves a **name** for a lost run.
* It was measured through a transient user scope configured **identically** (`MemoryMax` + `OOMPolicy=kill`), **not**
  through the Hermes `tools/process_registry.py` wrapper; the production properties are read from source, the wrapper
  path itself was not exercised (same limitation as the sibling fix).
* Caps (1200M) are **below** production's 4 GiB: they force the OOM to make the property observable; they are not a
  claim about when production OOMs.
* **n is one run per arm** — two arms, four gate runs, not a rate, and DEFECT-22's own SIGSEGV was **not** reproduced
  (still 0 disturbances in the post-`194844c` series).
* The parse-failure leg (L3) uses a stub `PY` that fails the parse call; it does not prove anything about a *real*
  parse failure mode other than the refusal path itself.
* **The canonical arc (`tools/arc_lega.sh` / `tools/arc_lega_capture.sh` full runs) was NOT re-run this tick.** The
  changed file is an instrument script imported by no test; coverage this tick is the four instrument gates (one of
  which drives the changed script end to end under GDB), the dry run, and the two deliberately-killed arms.
* Deliberately-killed runs write to `mktemp -d` under `/tmp` only — never into `output/` — so a deliberate kill cannot
  enter the arc ledger. Ledger therefore unchanged: plain post-`194844c` series 14 runs / 0 disturbed, capture series
  6 runs, whole series n=20 / 2 disturbed, both at `194844c`.

## Provenance

* Brief: `.builder_queue/brief_defect22c_capture_record_survival.md` (`tools/check_brief.py` → PASS, 0 invalid).
* Delegated to `agy` (`TIMEOUT=45m bash ~/.hermes/scripts/agy_implement.sh -f …`); the delegate was interrupted by the
  orchestrator's own 420 s foreground-call ceiling **after** it had written both files and was iterating on its second
  gate attempt (`output/agy/agy_impl_20260913_131529.log`, final line `error: interrupted`). The orchestrator then ran
  and dispositioned the gate itself under the loop's fallback rule — no claim of the delegate's is load-bearing.
* Orchestrator-run gate: `bash tools/gate_arc_lega_capture_record_survival.sh` → **rc=0**.
