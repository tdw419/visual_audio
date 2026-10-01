import json

TICKET = ".builder_queue/DEFECT-22_arc_legA_instability.json"
ROADMAP = "systems/GLYPH_SELF_HOSTING_ROADMAP.md"

d = json.load(open(TICKET))
d["ledger_2026_09_14_0150"] = (
    "Capture-series leg #30 RUN, seed 2026091409, head 2ef0a85, worker-scope launch "
    "systemd-run --user --scope -p MemoryMax=4G --unit=d22-leg30 (sidecar cgroup "
    "d22-leg30.scope, mem_limit 4294967296, state=inactive/Deactivated successfully). "
    "GREEN: rc=0, 323 passed / 1 skipped / 9 deselected in 66.24s, segv_caught=false "
    "(si_addr none, pc_symbol none, gdb exitcode 0; all 9 marker hits in the gdb log are "
    "the capture block itself, spot-checked), crashes=0, faulthandler_crashes=0, "
    "oom_kill_delta=0, journal_oom_kill_delta=0, mem_peak=1.61 GB - eighth consecutive "
    "worker-scope green (#23 2.19 GB, #24 1.72 GB, #25 1.73 GB, #26 1.59 GB, #27 1.73 GB, "
    "#28 1.72 GB, #29 1.61 GB, #30 1.61 GB), all far under the 4 GiB cap. Artifacts: "
    "output/arc_lega_capture_seed2026091409_2ef0a85.{txt,json,gdb.txt}. Instrument gated "
    "first this tick: bash tools/gate_arc_lega_capture.sh -> L1/L1b/L2/L3/L4/L6 PASS incl. "
    "L6a/b/c (1 stale fixture report swept, /var/crash left 0, post-run sweep before=0 "
    "after=0); rc=1 SOLELY on L5 tracked-dirty hygiene - the same 9 sibling-lane dirty "
    "files (verified at #27 to have zero overlap with leg A's 52-file selector). Series: "
    "n=30 / 0 disturbed outside 194844c (not a rate). Supply re-measured this tick: "
    "python3 tools/supply_census.py -> TOTAL=72 OPEN=0. Teleop: no substrate read this "
    "tick (A/report work only)."
)
json.dump(d, open(TICKET, "w"), indent=1)

foot = (
    "\n\n[2026-09-14 01:5x CDT — DEFECT-22 capture-series leg #30: eighth consecutive "
    "worker-scope green (cron af3e62239ce2)]\n"
    "Row sweep: 0 open rows (supply_census TOTAL=72 OPEN=0). Leg #30 seed 2026091409 head "
    "2ef0a85 under MemoryMax=4G scope d22-leg30: rc=0, 323 passed / 1 skipped / 9 "
    "deselected, 66.24s, segv=no, oom_kill_delta=0, mem_peak 1.61 GB (journal: scope "
    "deactivated, 1min15.4s CPU). Instrument gated first (gate_arc_lega_capture rc=1 "
    "solely on L5 sibling-lane dirt, zero selector overlap, verified at #27). Series: "
    "n=30 / 0 disturbed outside 194844c - still two one-offs, NOT a rate. Jericho's "
    "pending pick unchanged: renew supply / accept the bound and release the level "
    "trigger / re-point the cron. Teleop: no surface read this tick (A/report work "
    "only).\n"
)
open(ROADMAP, "a").write(foot)
print("ledger + roadmap footnote written")
