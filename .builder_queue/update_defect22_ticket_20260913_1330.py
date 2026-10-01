#!/usr/bin/env python3
"""Append this tick's keys to the DEFECT-22 ticket (json.load/dump, indent 2, UTF-8)."""
import json
import pathlib

P = pathlib.Path("/home/jericho/projects/zion/projects/visual_audio/.builder_queue/DEFECT-22_arc_legA_instability.json")
d = json.loads(P.read_text(encoding="utf-8"))

d["l6_env_not_a_verdict_2026_09_13_1330"] = (
    "THE FLAKE IS DISPOSITIONED, not weakened (DEFECT-22d, commit with this key). "
    "REPAIR_PENDING_d22c_apport_falsifier_flake.md's option (1)+(2): tools/gate_arc_lega_capture.sh L6b now retries "
    "the deliberate crasher up to 2 attempts (re-sweeping before attempt 2) and, when apport still records nothing, "
    "proves sweep necessity against a CONTROLLED fixture-tagged report (L6b-alt) and prints "
    "'L6 ENV NOTE: apport did not record the deliberate crasher in 2 attempts ... environment condition, not a tree "
    "verdict'. The leg no longer sets L6_OK=0 for absence alone; a sweep that fails to remove the control still goes "
    "L6b-alt FAIL. Gate tools/gate_L6_env_skip.sh (NEW) rc=0 with H0 premise (pinned ecef274 contains the old vacuous "
    "FAIL and lacks L6_CRASHER_FIXTURE), H1 RED-first (pinned pre-fix gate under the non-crashing stub -> rc=1 with "
    "'L6 FAIL: falsifier vacuous'; working tree under the same stub -> L6b-alt PASS + L6 ENV NOTE), H2 discrimination "
    "preserved (neutered sweep on the forced no-report path -> 'L6b-alt FAIL', scratch copy md5 printed before/after), "
    "H3 the real path still discriminates (real fixture -> 'L6b RED observed (attempt 1)'; ENV NOTE occurrences in "
    "that run: 0), H4 no regression (/var/crash 0 reports after every leg; gate_arc_lega_naming/telemetry/"
    "record_survival all rc=0). Receipt systems/RECEIPT_DEFECT22D_L6_ENV_NOT_A_VERDICT.md. NOT proven: apport's "
    "suppression is not repaired (the condition is reclassified, not fixed), the ENV path no longer asserts that "
    "apport CAN record a crasher here (an environment premise is printed instead), the stub removes the crash so "
    "H1/H2 exercise the no-report path rather than apport's refusal mechanism, H1's rc=1 assertion is weak on a dirty "
    "tree (L5), and n=1 per arm - not a rate."
)

d["ledger_2026_09_13_1330"] = (
    "ecef274 + this tick: 1 CAPTURE-series arc run, fresh order (SEED=2026091306 -> rc=0 / 325 passed / 1 skipped / "
    "1 deselected / 132 s / segv_caught=false / crashes=0, output/arc_lega_capture_seed2026091306_ecef274.json); "
    "capture series now 7 runs / 0 disturbed over 7 distinct pytest-randomly orders. Plain post-194844c series "
    "unchanged at 14 runs / 0 disturbed. Whole series n=21 / 2 disturbed, both at 194844c - still two one-offs, NOT a "
    "rate. That run's own cgroup: mem_limit 4294967296, mem_peak 3910356992 = 91.0% of the cap, oom_kill_delta=0, "
    "journal_oom_kill_delta=3 (PRESSURE=yes from other lanes' kills in the window, not this run's cgroup). Work this "
    "tick: the L6 falsifier flake dispositioned (see the key above) instead of a 13th plain green."
)

d["supply_2026_09_13_1330"] = (
    "Live supply = THIS ticket only, re-measured this tick: python3 tools/supply_census.py -> TOTAL=59 OPEN=0; "
    "GLYPH_BACKLOG.md BK-1..BK-14 + OBS-1 all promoted and landed; OSS GL-6/GL-7 artifact-done and "
    "publication-reserved (GL-8 needs an outside human). queue=1 == this ticket, so state=REPAIR_PENDING is a LEVEL "
    "trigger on a defect at 0/21 disturbances outside 194844c. Two of the queue's mechanical tickets are now closed "
    "by landing, not by argument: DEFECT-22b (arc record survival, 9ef7b49), DEFECT-22c (capture record survival, "
    "ecef274) and this tick's DEFECT-22d (L6 environment note). Jericho's pending pick is unchanged: renew lane "
    "supply / accept DEFECT-22 as a documented stability bound and release the level trigger (move this .json to "
    ".builder_queue/resolved/) / re-point or slow the cron."
)

P.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("ticket keys:", len(d), "->", sorted(d)[-3:])
