#!/usr/bin/env python3
"""DEFECT-22 ticket update — builder cron af3e62239ce2, 2026-09-13 09:2x tick.

Adds: (a) verification of the landing that arrived between ticks (50d551c, sidecar consistency),
(b) this tick's finding + fix (the gate was blocking the apport crash-capture path),
(c) a fresh supply census. No rate, no causality: every entry is a command + its output.
"""
import json

P = ".builder_queue/DEFECT-22_arc_legA_instability.json"
d = json.load(open(P))

d["landing_verified_2026_09_13_0925"] = (
    "50d551c ('fix(defect22): the capture sidecar can no longer record a captured SIGSEGV as \"no crash\"', "
    "parent d62e96a) arrived between ticks and was RE-RUN, not trusted: `bash tools/gate_arc_lega_capture.sh` "
    "at 50d551c -> gate rc=0 in 3.172 s, L1b PASS (pre-fix predicate rc=3 = contradiction observed; premise "
    "check that d62e96a lacks crash_count_source = 1), L4 falsifier RED observed, L5 tracked-modifications 0. "
    "Sidecar read back from disk: output/defect22_sidecar_POST_d62e96a_crasher.json = rc 139 / crashes 1 / "
    "faulthandler_crashes 0 / crash_count_source 'live_capture' / capture.segv_caught true, vs the pre-fix "
    "output/defect22_sidecar_contradiction_PREFIX_d62e96a.json = same crash with crashes 0. The landing is real."
)

d["apport_path_blocked_2026_09_13_0925"] = (
    "FINDING: the loop's own gate was disarming the apport crash-capture path it exists to feed. `ls -l "
    "/var/crash/` held _usr_bin_python3.12.1000.crash (1,784,139 B, Date 09:15:04, 'ProcCmdline: /usr/bin/python3 "
    "tests/fixtures/faulthandler_segv_fixture.py') — left by the PREVIOUS tick's gate run (the fixture is the "
    "gate's deliberate crasher). /var/log/apport.log then shows the cost: 'INFO apport ... executable: "
    "/usr/bin/python3.12' followed by 'ERROR ... report /var/crash/_usr_bin_python3.12.1000.crash already exists "
    "and unseen, skipping to avoid disk usage DoS' (twice: 09:18:09, 09:20:56). apport keys the report on the "
    "EXECUTABLE, and arc leg A's interpreter IS /usr/bin/python3.12 — so while a deliberate-crasher report sits "
    "there unseen, apport refuses to record the NEXT crash of that executable, i.e. the next real RED gets no "
    "report and no raw core. The previous tick had manually moved reports out of /var/crash (5da0a63) to re-arm "
    "this path; the gate put one straight back."
)

d["apport_mechanism_measured_2026_09_13_0925"] = (
    "My first hypothesis — 'a deliberate crasher under ulimit -c 0 leaves no report' — was FALSIFIED by the leg I "
    "wrote for it (L6 FAIL: a guarded crasher still wrote a report, 0 -> 1). Isolated re-measurement, each phase "
    "starting from a swept /var/crash (/tmp/d22_l6_measure.sh): (a) `( ulimit -c 0; python3 fixture )` -> 1 report "
    "written, size 1,784,211 B, NO new core in /var/lib/apport/coredump; (b) `( ulimit -c unlimited; python3 "
    "fixture )` -> 1 report written, size 1,784,143 B, NEW 7,012,352 B raw core (pid 3468820). apport log for the "
    "same two crashes: 'called for global pid <n>, signal 11, core limit 0, dump mode 1' -> still writes a report; "
    "'core limit 18446744073709551615' -> report AND core. CONCLUSION: ulimit -c 0 is a disk-size guard, not a "
    "report guard; only cleanup can protect the capture path. The gate's comments now carry this measured text "
    "instead of the assumption."
)

d["apport_path_fix_2026_09_13_0925"] = (
    "FIX (tools/gate_arc_lega_capture.sh, new L6 leg; no engine/transpiler/ABI/WGSL file touched): the gate now "
    "treats 'the apport path is clean at exit' as a checked property. sweep: moves *.crash reports whose "
    "ProcCmdline names the fixture out of /var/crash (fixture reports are instrument junk — a deliberate crasher "
    "is never evidence of a new arc crash); L6a selectivity: plants a NON-fixture report "
    "('ProcCmdline: /usr/bin/python3 -m pytest tests/test_gh22_device_driver_abi.py') and asserts the sweep leaves "
    "it alone (a loose sweep would destroy a real crash record); L6b necessity/falsifier: runs the deliberate "
    "crasher and REQUIRES it to leave a report — if it does not, the leg declares itself vacuous and FAILS rather "
    "than passing on a no-op (if instead a pre-existing non-fixture report occupies the path, it prints that "
    "report's ProcCmdline and reports NOT DECIDED, because that situation is the pollution itself); L6c cleanup: "
    "sweeps again and asserts 0 reports remain. Legs L2/L4 keep `ulimit -c 0` with the measured reason stated "
    "(suppresses the ~7 MB raw core, not the report). My own runs: BEFORE = the pre-fix L6 draft FAILED and left "
    "a report (Date 09:22:27); AFTER = 'stale fixture reports swept: 1 / L6a PASS / L6b RED observed: 1 report / "
    "L6c PASS: /var/crash left clean (0) / L6 PASS', gate rc=0 with L1/L1b/L2/L3/L4/L5 PASS, ~7 s total (was "
    "~3 s). Receipt systems/RECEIPT_DEFECT22_APPORT_PATH_HYGIENE.md; operator rule for the instrument's direct "
    "crasher probes added at tools/arc_lega_capture.sh:13-24."
)

d["ledger_2026_09_13_0925"] = (
    "50d551c + this tick: 0 PLAIN arc runs (deliberate, same reasoning as 0810/0820/0915 — post-194844c 12 runs "
    "/ 0 disturbed, so a 13th green is noise) and 0 new capture-series runs (the instrument did not change "
    "functionally; only its header comment gained the measured operator rule). Work done was verification plus "
    "the instrument-lane hardening above. This is the third consecutive wart found by measuring what the ticket "
    "asserted in prose (naming 06:35, sidecar 09:15, apport-path 09:25)."
)

d["supply_2026_09_13_0925"] = (
    "Live supply = THIS ticket only, re-measured independently this tick: roadmap census "
    "`python3 .builder_queue/census_roadmap_rows.py` -> 48 id rows / 0 open (the 7 marker-less rows are the known "
    "GH-18/20/21/22/23/24/25 `✅ <date> — N/N green` false positives); GLYPH_BACKLOG.md 15 rows (BK-1..BK-14 + "
    "OBS-1) all promoted and landed; both skeletons complete (OS-SKELETON Phase 3 steps 1-9, SPINE R1 + wire-in); "
    "SUBSTOR-1 landed; OSS GL-6/GL-7 artifact-done and publication-reserved, GL-8 needs a human stranger's "
    "friction report (not machine-checkable). queue=1 == this ticket, so state=REPAIR_PENDING is a LEVEL trigger "
    "on a defect at 0/12 reproduction post-194844c: the monitor wakes this loop every tick regardless. Unchanged "
    "and Jericho's call: renew lane supply, or accept DEFECT-22 as a documented stability bound and release the "
    "trigger (moving this .json to .builder_queue/resolved/ is what actually turns the level trigger off — see "
    "REPAIR_PENDING_lane_supply_exhausted.md)."
)

d["next_step"] = (
    "ARMED — unchanged for the defect itself: the next RED needs no post-mortem archaeology, run `SEED=<seed> bash "
    "tools/arc_lega_capture.sh` (pinned seed logged either way) and read the sidecar — capture.segv_caught=true + "
    "non-null si_addr/pc_symbol/faulting instruction + exit 139 IS the live evidence the 05:18 core could not "
    "give. Post-mortem core recovery (tools/apport_core_unpack.py) stays the fallback for crashes outside the "
    "instrument, and as of this tick the apport path it depends on is no longer blocked by the loop's own gate "
    "(L6); a deliberate-crasher probe run through the instrument directly still leaves a report — operator rule at "
    "tools/arc_lega_capture.sh:13-24. Unchanged and Jericho's call: renew lane supply, or accept DEFECT-22 as a "
    "documented stability bound and release the level trigger. The gh12 half is closed (RULING_gh12_gate_"
    "determinism.md OPTION 3, landed)."
)

json.dump(d, open(P, "w"), indent=2)
print("updated", P, "keys:", len(d))
