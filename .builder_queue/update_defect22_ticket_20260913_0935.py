#!/usr/bin/env python3
"""DEFECT-22 ticket update — builder cron af3e62239ce2, 2026-09-13 09:3x tick.

Verification-only tick: the previous tick's L6 landing RE-RUN rather than trusted, plus one
bounded measurement of the property L6 asserts (the gate vs the shared apport report path).
Every entry is a command + its own output. No rate and no causality is claimed anywhere: the
leak search is reported as trials, and the occupancy windows are one run's samples.
"""
import json

P = ".builder_queue/DEFECT-22_arc_legA_instability.json"
d = json.load(open(P))

d["landing_verified_2026_09_13_0935"] = (
    "2654f49 ('harden(defect22): the sweep's predicate is the report's own ProcCmdline, not the whole file', "
    "parent 0676e79 = the L6 leg's landing) RE-RUN, not trusted: `bash tools/gate_arc_lega_capture.sh` at 2654f49 "
    "-> rc=0 in 7.179 s (my run), and again rc=0 in 7.2 s (repeat, so the gate is not one-shot green); legs as "
    "printed: L1 marker 1 / si_addr (void *) 0x0, L1b PASS (pre-fix record self-contradictory), L2 PASS "
    "(neutralised run loses si_addr + attribution), L3 PASS (instrument plumbing + no-clobber), L4 PASS with the "
    "falsifier observed RED, L5 PASS (tracked modifications 0), L6 PASS (L6a selectivity PASS, L6b RED observed, "
    "L6c swept 1 / 0 left). `git status --short` filtered to tracked paths: empty before and after every probe "
    "below. Landing is real at this head."
)

d["crashpath_occupancy_2026_09_13_0935"] = (
    "MEASURED (one run, not a rate): while the instrument gate RUNS, the shared apport report path "
    "/var/crash/_usr_bin_python3.12.1000.crash is occupied by instrument-caused reports for ~5.25 s of a 7.1 s run "
    "(3 windows: 0.00-1.53 s = the planted positive control, 2.29-3.56 s, 5.34-7.13 s), sampled every 0.25 s by "
    ".builder_queue/probe_defect22_crashpath_occupancy.sh (29 samples, max fixture count 1, control seen -> the "
    "sampler is not blind). apport's log for the same run shows the consequence on the gate's own successive "
    "crashers: 09:33:41.403 'wrote report' (L2 crasher) -> 09:33:42.949 'ERROR ... this executable already crashed "
    "2 times, ignoring' (L4 gdb-falsifier crasher). The same mechanism was seen in a run 4 min earlier as "
    "'already exists and unseen, skipping to avoid disk usage DoS' (09:32:58.734, L4 crasher while L2's report was "
    "unseen). BOUND, NOT REPAIRED: this is benign for the gate's own verdicts (they come from the gdb transcript "
    "and the sidecar, never from the apport report), and a per-leg sweep would shrink ~1.6 s windows on a 7 s, "
    "few-times-a-day gate — recorded as the honest boundary of the L6 fix instead of another instrument patch. "
    "RESIDUAL RISK (named, unmeasured): a GENUINE python3.12 crash landing inside a gate run would also have its "
    "report suppressed, i.e. the apport fallback capture path is unavailable for ~5 s per gate run."
)

d["probe_vacuity_2026_09_13_0935"] = (
    "My OWN first sampler was vacuous and reported success: it launched its watcher before creating the flag file "
    "the watcher waited on, so samples.txt was empty and the verdict printed 'fixture occupancy: none observed'. "
    "Caught only by checking the sample count (0 lines) — the same failure mode the repo's Evidence Discipline "
    "names ('a verification that cannot fail is not a verification'). The corrected sampler "
    ".builder_queue/probe_defect22_crashpath_occupancy.sh creates the flag BEFORE the watcher, samples each report "
    "with its own is_fixture predicate, and PLANTED a fixture report as a positive control that it then had to "
    "observe (it did: max fx=1). Both scripts are committed so the trap is reproducible."
)

d["leak_search_2026_09_13_0935"] = (
    "HYPOTHESIS TESTED AND NOT SUPPORTED (n=5 runs, reported as trials, NOT a rate): 'the gate leaves a fixture "
    "report in /var/crash AFTER exit, re-arming the apport DoS guard it was fixed to clear'. Method: "
    ".builder_queue/probe_defect22_crashpath_exit_leak.sh (quarantine + 30 s post-exit watch) and "
    ".builder_queue/probe_defect22_crashpath_leak_trials.sh 4 15 (R=4 trials, entry count recorded, 15 s watch "
    "after each exit). Result: clean entry 4/4 trials, post-exit reports 0/5 runs (4 trials + the single probe), "
    "/var/crash count 0 immediately at every exit and 0 at the end of every watch. The observation that first "
    "looked like a cross-run leak — 'stale fixture reports swept: 1' at L6 start after a run I had seen exit "
    "clean — is explained by the gate's OWN earlier legs: the L1/L2/L4 crashers each write a report ~1.4-2.6 s "
    "after their crash (apport.log: called 09:32:55.731 -> wrote 09:32:57.182), so L6's start sweep legitimately "
    "clears this run's own reports. L6c's 'left clean (0)' held in every trial I ran."
)

d["ledger_2026_09_13_0935"] = (
    "2654f49: 0 arc runs this tick (deliberate — 12 plain runs / 0 disturbed post-194844c, so a 13th green is "
    "noise, and the capture series is at n=2 green for the same reason). Work was verification of the 09:25 "
    "landing plus one bounded measurement of the property L6 asserts (see the three entries above). Third tick in "
    "this family to measure, rather than trust, a prose claim about the crash-capture path — and the first where "
    "the measurement found the claim HOLDING (naming 06:35 and sidecar 09:15 were real warts; the exit leak is "
    "not reproducible in 5 runs). Supply unchanged: 0 open roadmap rows, backlog exhausted, one open ticket = the "
    "monitor's level trigger."
)

d["supply_2026_09_13_0935"] = (
    "Live supply = THIS ticket only, re-measured independently this tick: roadmap census "
    "`python3 .builder_queue/census_roadmap_rows.py` -> every printed row carries done_marker=True (48 id rows, 0 "
    "open; the 7 marker-less rows remain the known GH-18/20/21/22/23/24/25 'valid checkmark, no literal done' "
    "false positives); GLYPH_BACKLOG.md exhausted (BK-1..BK-14 + OBS-1 all promoted and landed); both skeletons "
    "complete (OS-SKELETON Phase 3 steps 1-9, SPINE R1 + R2 wire-in); SUBSTOR-1 landed; OSS GL-6/GL-7 "
    "artifact-done and publication-reserved (GL-8 needs an outside human's friction report, not machine-"
    "checkable); lane choice / publication / Tier C reserved to Jericho. queue=1 == this ticket, so "
    "state=REPAIR_PENDING is a LEVEL trigger on a defect at 0/12 reproduction post-194844c. Jericho's call, "
    "unchanged: renew lane supply, or accept DEFECT-22 as a documented stability bound and release the trigger "
    "(move this .json to .builder_queue/resolved/ — that is what turns the level trigger off; see "
    "REPAIR_PENDING_lane_supply_exhausted.md)."
)

json.dump(d, open(P, "w"), indent=2)
print("updated", P, "keys:", len(d))
