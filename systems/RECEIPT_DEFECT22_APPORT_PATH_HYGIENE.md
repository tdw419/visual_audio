# RECEIPT — DEFECT-22: the loop's own gate was blocking the crash-capture path it feeds

**Date:** 2026-09-13 ~09:2x CDT · **Seat:** builder orchestrator (cron `af3e62239ce2`) · **Head at start:** `50d551c`
**Ticket:** `.builder_queue/DEFECT-22_arc_legA_instability.json` · **Type:** mechanical hardening of the capture instrument's gate (no engine/transpiler/ABI/WGSL file touched)

## Trigger

Monitor woke on the level trigger only (`head=d62e96a → 50d551c tracked_dirty=0 state=REPAIR_PENDING queue=1`).
Supply re-checked independently before doing anything (not copied from prose): roadmap census
`python3 .builder_queue/census_roadmap_rows.py` → **48 id rows / 0 open**; `GLYPH_BACKLOG.md` 15 rows
(BK-1..BK-14 + OBS-1) all promoted and landed. Live supply is this ticket, so the tick went at the instrument
lane rather than inventing a row.

## 1. Verified the landing that arrived between ticks (not trusted, re-run)

`50d551c` ("fix(defect22): the capture sidecar can no longer record a captured SIGSEGV as 'no crash'",
parent `d62e96a`) touched `tools/arc_lega_capture.sh`, added legs to `tools/gate_arc_lega_capture.sh`,
and added `systems/RECEIPT_DEFECT22_CAPTURE_SIDECAR_CONSISTENCY.md`. My own run at that head:

```
$ bash tools/gate_arc_lega_capture.sh        # pre-existing gate, head 50d551c
   L1b PASS: pre-fix predicate rc=3 (= contradiction observed); premise (d62e96a lacks
             crash_count_source) = 1
   L4 PASS: explicit falsifier observed RED (si_addr=none, pc_symbol=none without stop clause)
   L5 PASS: tracked modifications 0
   gate rc: 0      (real 0m3.172s)
```

Post-fix sidecar for the crasher-stub run, read back from disk (not from the commit message):
`output/defect22_sidecar_POST_d62e96a_crasher.json` → `rc=139, crashes=1, faulthandler_crashes=0,
crash_count_source="live_capture", capture.segv_caught=true`; pre-fix record
`output/defect22_sidecar_contradiction_PREFIX_d62e96a.json` → same crash with `crashes=0`. The landing is
real and its gate is green.

## 2. Finding — the gate disarms the apport path it exists to feed

`ls -l /var/crash/` held one report, `_usr_bin_python3.12.1000.crash` (1,784,139 B, **Date 09:15:04**,
`ProcCmdline: /usr/bin/python3 tests/fixtures/faulthandler_segv_fixture.py`) — i.e. left behind by the
previous tick's own gate run (the fixture is the gate's deliberate crasher). `/var/log/apport.log` then shows
what that costs:

```
INFO: apport (pid 3463668) 09:18:09: executable: /usr/bin/python3.12 (command line "/usr/bin/python3 tests/fixtures/faulthandler_segv_fixture.py")
ERROR: apport (pid 3463668) 09:18:09: report /var/crash/_usr_bin_python3.12.1000.crash already exists and unseen, skipping to avoid disk usage DoS
INFO: apport (pid 3466069) 09:20:56: ... same skip
```

apport keys the report on the **executable**, and the arc leg A interpreter *is* `/usr/bin/python3.12`. So while a
deliberate-crasher report sits there "unseen", apport **refuses to record the next crash of that executable** —
the apport core path that produced the 05:18 core (`RECEIPT_DEFECT22_...`/ticket `core_recovered_...`) is silently
disarmed by the loop's own verification run. The previous tick had manually moved reports out of `/var/crash`
(`5da0a63`) to re-arm it; the gate immediately put one back.

## 3. Mechanism measured (my hypothesis was wrong first, then corrected — the first fix was falsified by its own gate)

Assumption attempted first: a deliberate crasher under `ulimit -c 0` leaves no report. **Falsified by my own leg**
(`L6 FAIL: a guarded (ulimit -c 0) crasher still wrote an apport report`, 0 → 1). Isolated re-measurement, both
directions, each phase starting from a swept `/var/crash` (`/tmp/d22_l6_measure.sh`):

| crasher run | /var/crash report | report size | raw core in /var/lib/apport/coredump |
|---|---|---|---|
| `( ulimit -c 0; python3 fixture )` | **1 written** | 1,784,211 B | none (pid 3468672 has no core entry) |
| `( ulimit -c unlimited; python3 fixture )` | **1 written** | 1,784,143 B | **new 7,012,352 B core** (pid 3468820) |

apport log for the same two crashes: `called for global pid … signal 11, core limit 0, dump mode 1` → still writes
a report; `core limit 18446744073709551615` → writes the report *and* the raw core. **So `ulimit -c 0` is a
disk-size guard, not a report guard**; the capture path can only be protected by cleaning up after the deliberate
crash. (This corrects the assumption I first wrote into the gate's comments, which are now measured text.)

## 4. Fix — `tools/gate_arc_lega_capture.sh` L6 leg

The gate now treats "the apport path is clean at exit" as a checked property, three sub-legs:

- **sweep** — moves `*.crash` reports whose `ProcCmdline` names the fixture out of `/var/crash` (fixture reports are
  instrument junk by definition: a deliberate crasher is never evidence of a new arc crash). Discarded with the
  gate's temp dir — reproducible in one command.
- **L6a selectivity** — plants a *non*-fixture report at the apport path
  (`ProcCmdline: /usr/bin/python3 -m pytest tests/test_gh22_device_driver_abi.py`, plus a body field that *mentions*
  the fixture path) and asserts the sweep leaves it alone. The sweep's predicate is the narrow one — the report's
  **own `ProcCmdline` line** — precisely because it is destructive: a first draft matched the tag anywhere in the
  report, which would have swept a real crash record whose stack or file list happened to name the fixture. L6a's
  planted report carries that body-field mention for exactly this reason.
- **L6b necessity (falsifier)** — runs the deliberate crasher and requires that it leaves a report; if it does not,
  the leg declares itself vacuous and FAILS (`L6 FAIL: falsifier vacuous … the cleanup proves nothing`) rather than
  passing on a no-op. If instead a *pre-existing non-fixture* report occupies the path, the leg prints that
  report's `ProcCmdline` and reports NOT DECIDED (that situation is the pollution itself, not a gate failure).
- **L6c cleanup** — sweeps again and asserts `/var/crash` is left with 0 reports.
- Legs L2/L4's crashers keep `ulimit -c 0`, now with the measured reason stated: it suppresses the ~7 MB raw core,
  not the report.

## 5. Verification, my own runs

```
BEFORE (pre-fix gate, 09:22 run — the warts as they were)
  $ bash tools/gate_arc_lega_capture.sh   # pre-fix L6 draft, no sweep
  ...  L6 FAIL: a guarded (ulimit -c 0) crasher still wrote an apport report
  $ ls /var/crash/      -> 1 report (_usr_bin_python3.12.1000.crash, Date 09:22:27)

AFTER (this commit's gate)
  $ bash tools/gate_arc_lega_capture.sh
  -- L6 leg: the gate must not leave the crash-capture path polluted (/var/crash)
     stale fixture reports swept: 1; fixture reports still present: 0
     L6a PASS: sweeper selectivity — a non-fixture (real-crash-shaped) report survives the sweep
     L6b RED observed: the deliberate crasher left 1 fixture report(s) — the sweep is necessary
     L6c PASS: swept 1 report(s); /var/crash left clean (0) — apport can record the next real crash
     L6 PASS
  -- gate rc: 0      (with L1/L1b/L2/L3/L4/L5 all PASS; ~7 s total, was ~3 s)
```

(`rc=0` requires a clean tracked tree: L5 fails the run while this change is uncommitted — the pre-commit run is the
RED for L5, and the post-commit run is the GREEN, which is the run pasted above.)

## Instrument-side enforcement — 2026-09-13 09:4x (builder cron `af3e62239ce2`)

The gap above ("the instrument's own ad-hoc crasher probes still leave a report … not yet enforced by code")
is now closed in code, not prose. `tools/arc_lega_capture.sh` carries `is_fixture_report`,
`sweep_fixture_reports` and `count_fixture_reports` (same predicate as the gate's L6/L6a: the report's OWN
`ProcCmdline`) and calls the sweep **before and after every run**, moving — never deleting — swept reports to
`QUARANTINE_DIR` (default `/tmp/d22q`). The run's rc semantics are untouched (rc is the inferior's verdict; a
leftover fixture report prints a WARNING on stderr instead of changing rc).

Evidence, own runs:

| Leg | Command | Result |
|---|---|---|
| P1 (fixed) | `bash .builder_queue/probe_defect22_instrument_sweep.sh` | **PROBE PASS** — planted fixture report swept (before=1, after=0, left=0), planted non-fixture report **survives**, 1 report moved to quarantine, instrument rc=0 unchanged (`output/d22_instrument_sweep_probe_20260913_094216.txt`) |
| P2 (falsifier) | same probe, pre-fix instrument from `git show HEAD:tools/arc_lega_capture.sh` | **RED observed** — the fixture report is still in `/var/crash` after the run, i.e. the property really was absent before the fix (a probe that cannot go red proves nothing) |
| Gate | `bash tools/gate_arc_lega_capture.sh` | re-run after staging the edit: **rc=0**, L1 / L1b / L2 / L3 / L4 (falsifier RED) / L5 / L6 PASS — see the commit body for both runs |

Run 1 of the gate in this tick reported `L5 FAIL: existing tracked files were modified` — that was the edit
itself still uncommitted (`git diff --name-only` non-empty, `tools/gate_arc_lega_capture.sh:346-353`), not a
defect in the change.

## NOT verified / not done

- **The real defect is still uncaptured.** Nothing here diagnoses the SIGSEGV; it protects the *record* of the next
  one. `si_addr`-on-the-real-defect remains unproven, and the crash mechanism from the 05:18 core is still
  undiagnosed.
- **No arc leg A run this tick** (plain series post-`194844c`: 12 runs / 0 disturbed — a 13th green is noise).
- **The instrument's own ad-hoc crasher probes **now** clean up after themselves** (enforced in code since
  2026-09-13 09:4x — see the *Instrument-side enforcement* section above; the manual operator rule survives as a
  fallback). Still not covered: a deliberate crasher invoked *outside* both the gate and the instrument, and
  crashes of an embedding process that is not `/usr/bin/python3`.
- **L6 is host-specific** (needs writable `/var/crash` + apport). On a host without apport it prints
  `L6 SKIP … (NOT a pass)` and `L6 NOT DECIDED` rather than failing — a leg that cannot be decided is not a
  verified property, and the output says so.
- The gate still does not sweep `*.crash` reports from *other* executables, and does not check
  `/var/lib/apport/coredump` growth (a real crash's raw core lives there).
