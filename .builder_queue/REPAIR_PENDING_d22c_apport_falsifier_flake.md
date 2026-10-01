# REPAIR_PENDING — `gate_arc_lega_capture.sh` L6 reports FAIL where the condition is environmental

> **CLOSED 2026-09-13 ~13:50 CDT by builder cron `af3e62239ce2`** — implemented as options (1)+(2) (retry, then a
> controlled necessity control plus a printed environment NOTE), landed with its own harness
> `tools/gate_L6_env_skip.sh` and receipt `systems/RECEIPT_DEFECT22D_L6_ENV_NOT_A_VERDICT.md`. The live guard was
> **tightened, not weakened**: with the sweep neutered, the forced no-report path still reports `L6b-alt FAIL`, and
> the real path still shows `L6b RED observed`. Kept here (never deleted) as the record of the flake and its options.

**Filed:** 2026-09-13 ~13:30 CDT by builder cron `af3e62239ce2`, during DEFECT-22c
(`systems/RECEIPT_DEFECT22C_CAPTURE_RECORD_SURVIVAL.md`).
**Not a skeleton-sign-off change.** No locked interface is involved; this is a gate-quality ticket.

## The measurement (n=4, not a rate)

`tools/gate_arc_lega_capture.sh` L6 (the apport-pollution falsifier) exited **1** on one of four runs this tick:

| run | tree | rc | L6 |
|---|---|---|---|
| 13:22, invoked by `gate_arc_lega_telemetry.sh` L4 | working tree (DEFECT-22c change present) | 1 | `L6 FAIL: falsifier vacuous — the deliberate crasher wrote no apport report, so the cleanup proves nothing` |
| 13:24, pre-change `arc_lega_capture.sh` restored from HEAD (md5 `990635d22e4e553a92a463f950c7df53`) | pre-change | 0 | PASS (`L6c PASS: swept 1 report(s); /var/crash left clean (0)`) |
| 13:25, `gate_arc_lega_telemetry.sh` re-run | working tree | 0 | — (nested leg rc=0) |
| 13:26, full `gate_arc_lega_capture_record_survival.sh` | working tree | 0 | `gate_arc_lega_capture.sh rc=0` |

So the failure is **not** attributable to the DEFECT-22c change (pre-change arm passed; every post-change arm
passed), and the flaky leg is a **false FAIL**: the deliberate crasher genuinely segfaulted (`line 485:
Segmentation fault (core dumped)`), but no apport report landed in `/var/crash`, so the leg's own precondition was
not met.

## Why it matters

The leg exists to prove the *cleanup* is non-vacuous. When the environment suppresses the report (the same
suppression class `tools/arc_lega_capture.sh`'s hygiene header documents — a real python3.12 crash inside a window
where a report "already exists and unseen" is skipped), the leg cannot distinguish "cleanup works" from "nothing to
clean up" — but it reports **FAIL**, which reads as "the cleanup is broken" and turns any gate that depends on it
(here: `gate_arc_lega_telemetry.sh` L4, and DEFECT-22c's L4) red for reasons unrelated to the tree.

## Options (cheapest first)

1. **Widen the existing SKIP** (`tools/gate_arc_lega_capture.sh:458-465`): the code already emits
   `L6 SKIP: a pre-existing non-fixture report occupies the apport path …` for the occupied-path case. Add the
   sibling case — crasher segfaulted but no fixture report appeared **and** `CRASH_DIR` is empty → `L6 SKIP
   (environment: apport did not record the crasher)`, exit unaffected, and print the evidence (crasher rc, report
   count before/after). Cheapest, keeps the RED leg's discriminating power when apport *does* work.
2. Same as (1) plus a **retry once** before skipping (the suppression may be transient), recording both attempts.
3. Treat a missing apport report as a hard environment precondition: check the apport config
   (`/proc/sys/kernel/core_pattern`, apport enabled) in an L0 premise leg, and exit 2 with "environment cannot run
   this leg" — louder, but makes the whole gate unrunnable in environments without apport.
4. Leave as-is and accept the flake, documenting it as a known false-FAIL (not recommended: a gate that goes red on
   environment state trains people to ignore it).

**Recommendation: option (1).** It preserves the falsifier where it can discriminate and stops the environment from
voting on the tree.

## Hold rule

Per the skeleton-handoff contract: this ticket is a **hold**, not new scope. The DEFECT-22c change was NOT weakened
to accommodate it — its L4 keeps the strict `rc=0` requirement on all four landed gates, which is exactly how this
flake was detected.
