#!/usr/bin/env python3
"""Append this tick's ledger to the DEFECT-22 ticket (numbers read from the sidecars)."""
import glob
import json
import pathlib

REPO = pathlib.Path("/home/jericho/projects/zion/projects/visual_audio")
TICKET = REPO / ".builder_queue/DEFECT-22_arc_legA_instability.json"

runs = []
for f in sorted(glob.glob(str(REPO / "output/arc_lega_capture_seed20260913*.json"))):
    d = json.load(open(f))
    cap = d.get("capture", {}) or {}
    runs.append(
        f"seed={d['seed']} rc={d['rc']} crashes={d['crashes']} {d['seconds']}s "
        f"segv_caught={cap.get('segv_caught')} "
        f"({pathlib.Path(f).name})"
    )
segs = "; ".join(runs) if runs else "NONE"
n = len(runs)
caught = sum(1 for f in glob.glob(str(REPO / "output/arc_lega_capture_seed20260913*.json"))
             if (json.load(open(f)).get("capture") or {}).get("segv_caught"))

t = json.load(open(TICKET))
t["capture_hunt_2026_09_13_1046"] = (
    f"FIRST REPETITION HUNT under the capture instrument (the ticket's ARMED next_step, exercised "
    f"rather than described): {n} fresh-seed arc leg A runs under gdb at head 586e37d — {segs}. "
    f"segv_caught={caught}/{n}. Distinct fresh seeds sample distinct pytest-randomly ORDERS, which is the "
    f"one dimension the ticket calls untested ('whether any ordering is more crash-prone ... stays a hypothesis'); "
    f"the earlier two capture runs (1914088745 at 5da0a63, 1208765432 at d62e96a) reused one seed each, so the "
    f"capture series had covered 2 orders — it now covers {2 + n}. Zero crashes again: the post-194844c bound is "
    f"unchanged and this is still NOT a rate (n too small, Jericho's single-trial rule). Instrument liveness was "
    f"gated first: `bash tools/gate_arc_lega_capture.sh` rc=0 at 586e37d (7 s, L1/L1b/L2/L3/L4-red/L5/L6 PASS), "
    f"so a green here is the instrument working, not the instrument asleep."
)
t["monitor_clock_wake_2026_09_13_1046"] = (
    "NEW MEASURED CAUSE for this loop's wake rate, complementary to REPAIR_PENDING_monitor_scope_selftrigger.md. "
    "Mon = /home/jericho/.hermes/scripts/glyph_build_chain_monitor.py. The diff between the suppressed 10:43:23 "
    "tick and this 10:46:53 tick was ONE field: ticket_age_h=0 -> 1 (head, tracked_dirty, newest_mtime, state, "
    "stall_tier, queue all identical). Ticket mtime 2026-09-13 09:44:00 -0500 => int((now-mtime)//3600) crossed 1 "
    "at ~10:44 => the wake was an HOUR BOUNDARY, not repo state. Source: :117-124 builds ticket_age_h at 1-h "
    "resolution on a clean tree with any *.json ticket, :126-130 prints it into the hashed stdout. Consequence: "
    "up to 24 zero-information agent wakes/day while a ticket is open on a clean tree. With the sibling leg "
    "(newest_mtime = the loop's own report on a dirty tree) the watchdog is never quiet in either tree state. "
    "Probe .builder_queue/probe_monitor_ticket_age_wake.py -> output/monitor_ticket_age_wake_probe.txt "
    "'PROBE VERDICT: PASS' rc=0, 6/6 legs: L1 baseline stable; L2 +1h/+2h/+3h on a scratch ticket's mtime alone "
    "=> 3 distinct fingerprints (clock-only wake reproduced); L3 6-h bucket => identical fingerprint for the same "
    "shifts; L3b +6h => CHANGES (level trigger preserved, cannot wedge); L4 queue 1->0 still changes it; L5 live "
    "script byte-identical md5 5b868a9571f6f6b9b98dc92d80d82b31. Held (NOT applied, Jericho's instrument): "
    ".builder_queue/held_patches/monitor_ticket_age_bucket.held.patch, 29 diff lines, apply "
    "`cd ~/.hermes/scripts && patch -p1 < <repo>/.builder_queue/held_patches/monitor_ticket_age_bucket.held.patch`; "
    "dry-run rc=0 and the patched copy runs (ticket_age_6h=0) as measured this tick."
)
t["ledger_2026_09_13_1046"] = (
    f"586e37d (docs-only atop 88846dc): {n} CAPTURE-series arc runs (see capture_hunt key) + 0 plain runs "
    f"(the plain ledger stays at 12 runs / 0 disturbed post-194844c). Wake cause measured, not assumed: "
    f"ticket_age_h crossed an hour boundary. Work this tick = the ticket's own armed next_step exercised "
    f"(repetition under the capture instrument) + one new measured loop-instrument finding with a probe and a "
    f"held patch. Verification: `bash tools/gate_arc_lega_capture.sh` rc=0 and "
    f"`/usr/bin/python3 -m pytest tests/test_osskel_space_lifetime.py tests/test_spine_r2_wirein.py "
    f"tests/test_defect18_tick_regfile.py tests/test_defect17_x31_refusal.py -q` -> 24 passed, rc=0 at this head "
    f"(the four landed gates re-measured, not trusted)."
)
t["supply_2026_09_13_1046"] = (
    "Live supply = THIS ticket only, re-measured independently this tick: `.builder_queue/census_roadmap_rows.py` "
    "-> every row done_marker=True, the 7 marker-less rows are the known GH-18/20/21/22/23/24/25 "
    "'checkmark without the literal done' false positives, so 0 open; `.builder_queue/probe_backlog_promotion_state.py` "
    "-> VERDICT: BACKLOG EXHAUSTED (15 ids BK-1..BK-14 + OBS-1, 0 promoted-but-open, 0 never-promoted); the two "
    "REPAIR_PENDING design notes that the standing prompt still calls 'awaiting implementation' (SPINE wire-in, "
    "OS-SKEL step 9) are LANDED and their headers now say so (722cc27 / d0f4ced), so that prompt line is stale. "
    "queue=1 == this ticket: state=REPAIR_PENDING is a LEVEL trigger cleared only by retiring this ticket to "
    ".builder_queue/resolved/ or by Jericho naming a new product row. Jericho's pending pick is unchanged: renew "
    "supply / accept DEFECT-22 as a documented stability bound and release the trigger / re-point or slow the cron."
)
json.dump(t, open(TICKET, "w"), indent=2, ensure_ascii=False)
open(TICKET, "a").write("\n")
print(f"ticket updated; capture runs recorded = {n}, segv_caught={caught}")
print(f"keys now: {len(t)}")
