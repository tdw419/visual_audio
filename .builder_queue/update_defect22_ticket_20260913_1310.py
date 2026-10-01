#!/usr/bin/env python3
"""Append this tick's keys to the DEFECT-22 ticket (2026-09-13 13:1x, cron af3e62239ce2)."""
import json
import pathlib

ROOT = pathlib.Path("/home/jericho/projects/zion/projects/visual_audio")
TICKET = ROOT / ".builder_queue" / "DEFECT-22_arc_legA_instability.json"

d = json.loads(TICKET.read_text())

d["pressure_class_2026_09_13_1310"] = (
    "MECHANISM ELIMINATED (bounded experiment, .builder_queue/probe_defect22_pressure_class.sh, raw stdout "
    "output/d22_pressure_class_probe.txt): a cgroup memory cap is enforced by the kernel OOM killer, and arm A "
    "measured it — MemoryMax=2200M OOMPolicy=continue -> systemd-run rc=137 (SIGKILL), mem_peak == mem_limit == "
    "2306867200, oom_kill_delta=1, journal_oom_kill_delta=1, PRESSURE=yes, rc_is_sigsegv=False. So the worker "
    "cap's enforcement path produces 137, never the 139 this ticket observed: the 05:1x pressure correlation "
    "cannot be 'the cap killed it'. Pressure-induced allocator pathology short of the cap is NOT excluded. "
    "SIDE EFFECT: that same arm was the FIRST real kernel OOM exercising the telemetry's non-zero path "
    "(oom_kill_delta/journal_oom_kill_delta/PRESSURE=yes had been stub-only); negative control = "
    "output/arc_lega_seed2026091305_9bd8dd2.json (rc=0, both deltas 0, no marker) so the predicate discriminates."
)

d["record_loss_fixed_2026_09_13_1310"] = (
    "ARM B OF THE SAME PROBE FOUND AN INSTRUMENT HOLE: MemoryMax=2200M OOMPolicy=kill -> SIDECAR=ABSENT (only a "
    "769-byte partial .txt), because the kernel kills the whole scope and the sidecar was written by a shell "
    "inside it, after pytest returned. The Hermes worker scope IS that configuration "
    "(tools/process_registry.py:273-308, 4 GiB) and leg A peaks at 2.97-3.93 GB of it, so a cap OOM would have "
    "erased the loop's primary verification verdict exactly when the ticket's own suspected condition occurs "
    "(the SUITE-ISO-2 loss class, never checked for the arc). FIXED THIS TICK: tools/arc_lega.sh writes a "
    "start record (state=RUNNING + seed + head + started_utc) before pytest starts, overwritten by the full "
    "record (state=DONE) on normal exit; gate tools/gate_arc_lega_record_survival.sh rc=0 with L1 RED observed "
    "against the pinned pre-fix runner (070e004, sidecar_count=0 under the killing scope) and L2 GREEN "
    "(killed run leaves state=RUNNING seed=2026091307); real uncapped run after the fix SEED=2026091308 -> rc=0 "
    "325 passed/1 skipped/1 deselected 125.37 s. Record: .builder_queue/resolved/DEFECT-22b_arc_record_loss_"
    "under_scope_oom.json (retired to resolved/ so the monitor's level trigger is not inflated). NOT fixed: "
    "tools/arc_lega_capture.sh writes its sidecar the same way (named follow-on)."
)

d["ledger_2026_09_13_1310"] = (
    "070e004 + this tick: 1 plain arc run (the post-fix real run, SEED=2026091308) -> rc=0 / 325 passed / "
    "1 skipped / 1 deselected / 125.37 s / crashes=0 / state=DONE / oom_kill_delta=0. Plain post-194844c series: "
    "14 runs / 0 disturbed. Capture series unchanged at 6 runs. Whole series n=20 / 2 disturbed, both at "
    "194844c — still two one-offs, NOT a rate. The deliberate-kill runs (probe arms A/B, gate L1/L2) wrote to "
    "/tmp only and are NOT in the arc ledger."
)

d["supply_2026_09_13_1310"] = (
    "Live supply = THIS ticket only, re-measured this tick: python3 tools/supply_census.py -> TOTAL=59 OPEN=0; "
    "GLYPH_BACKLOG.md re-read in full (BK-1..BK-14 + OBS-1, all promoted and landed). The standing prompt's "
    "'RULINGS awaiting implementation' line (DEFECT-18 option (a), DEFECT-17 option (d)) is STALE — both landed: "
    "rows 339/340 carry ✅ done, with 7a4208a + 11fe1ac and their gates on disk. The prompt's 'RULINGS' line "
    "should be dropped. Jericho's pending pick is unchanged: renew supply / accept DEFECT-22 as a documented "
    "stability bound and release the level trigger / re-point or slow the cron."
)

TICKET.write_text(json.dumps(d, indent=2) + "\n")
print(f"updated {TICKET} ({TICKET.stat().st_size} B, {len(d)} keys)")
