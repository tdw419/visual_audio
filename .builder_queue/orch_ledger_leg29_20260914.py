import json

TICKET = ".builder_queue/DEFECT-22_arc_legA_instability.json"
ROADMAP = "systems/GLYPH_SELF_HOSTING_ROADMAP.md"

d = json.load(open(TICKET))
d["ledger_2026_09_14_0140b"] = (
    "Capture-series leg #29 RUN, seed 2026091408, head 7802dfe, worker-scope launch "
    "systemd-run --user --scope -p MemoryMax=4G --unit=d22-leg29 (sidecar cgroup "
    "d22-leg29.scope, mem_limit 4294967296, state=DONE). GREEN: rc=0, 323 passed / 1 skipped / "
    "9 deselected in 65.97s, segv_caught=false (si_addr none, pc_symbol none), crashes=0, "
    "faulthandler_crashes=0, oom_kill_delta=0, journal_oom_kill_delta=0, mem_peak=1.61 GB - "
    "seventh consecutive worker-scope green (#23 2.19 GB, #24 1.72 GB, #25 1.73 GB, #26 1.59 GB, "
    "#27 1.73 GB, #28 1.72 GB, #29 1.61 GB), all far under the 4 GiB cap. Artifacts: "
    "output/arc_lega_capture_seed2026091408_7802dfe.{txt,json,gdb.txt}. Instrument gated first "
    "this tick: bash tools/gate_arc_lega_capture.sh -> L1/L1b/L2/L3/L4/L6 PASS incl. L6a/b/c "
    "(1 stale fixture report swept, /var/crash left 0); rc=1 SOLELY on L5 tracked-dirty hygiene - "
    "the same 9 sibling-lane dirty files (verified at #27 to have zero overlap with leg A's "
    "52-file selector). Series: n=29 / 0 disturbed outside 194844c (not a rate). Supply "
    "re-measured this tick: python3 tools/supply_census.py -> TOTAL=72 OPEN=0. Teleop: meta read "
    "only - snapshot age 287448 s (~3.3 d), tick=0, machine not stepping; no surface read, no "
    "substrate conclusions."
)
json.dump(d, open(TICKET, "w"), indent=1)

foot = (
    "\n\n[2026-09-14 01:4x CDT — DEFECT-22 capture-series leg #29: seventh consecutive "
    "worker-scope green (cron af3e62239ce2)]\n"
    "Row sweep: 0 open rows (scan script TOTAL=72 OPEN=0; the standing prompt's RULINGS line "
    "remains stale - DEFECT-17 7a4208a, DEFECT-18 11fe1ac, both landed and on disk). Leg #29 "
    "seed 2026091408 head 7802dfe under MemoryMax=4G scope d22-leg29: rc=0, 323 passed / 1 "
    "skipped / 9 deselected, 65.97s, segv=no, oom_kill_delta=0, mem_peak 1.61 GB (sidecar "
    "state=DONE; journal: scope deactivated, 1min15s CPU). Instrument gated first "
    "(gate_arc_lega_capture rc=1 solely on L5 sibling-lane dirt, zero selector overlap, "
    "verified at #27). Series: n=29 / 0 disturbed outside 194844c - still two one-offs, NOT a "
    "rate. Jericho's pending pick unchanged: renew supply / accept the bound and release the "
    "level trigger / re-point the cron. Teleop: no surface read - snapshot age ~3.3 days, "
    "tick=0, machine not stepping.\n"
)
open(ROADMAP, "a").write(foot)
print("ledger + roadmap footnote written")
