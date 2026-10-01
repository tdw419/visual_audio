#!/usr/bin/env python3
"""Append the 2026-09-13 12:0x attribution measurements to the DEFECT-22 ticket.

Builder cron af3e62239ce2. Read-modify-write, same shape as the other update_defect22_ticket_*.py
scripts, so a concurrent writer's keys survive.
"""
import json
import pathlib

T = pathlib.Path(".builder_queue/DEFECT-22_arc_legA_instability.json")
d = json.loads(T.read_text())

d["attribution_2026_09_13_1205"] = (
    "TWO MEASUREMENTS that remove the last tree-level explanation and name an environment. "
    "(A) NO CODE DIFFERENCE IN THE CRASH PATH: the crashing module and everything it imports are byte-identical "
    "at the crash head and at HEAD. `git diff --stat 194844c HEAD -- tools/glyph_isa_v2.py tools/glyph_gpt "
    "tools/rv64i_to_glyph.py tests/test_gh22_device_driver_abi.py pytest.ini conftest.py` prints NOTHING (0 lines), "
    "and `git rev-parse 194844c:tests/test_gh22_device_driver_abi.py HEAD:tests/test_gh22_device_driver_abi.py` "
    "returns the same blob 750f867e0b04209bd1536bf67700af1b4c391035 twice. The 20 non-doc files that DO differ "
    "194844c..HEAD are: new test modules (osskel proctab/space_lifetime/spawn, spine_r2_wirein, suite_iso_harness, "
    "the faulthandler fixture), tests/test_gh12_autoatlas.py (the ollama-gated admission leg -- that is run 1's red, "
    "already split out and closed at 07:00 by RULING_gh12_gate_determinism.md), and instrument tools (arc_lega*.sh, "
    "the capture/naming gates, check_brief.py, geos_aspace/emit/proctab/retain/osk_verify, apport_core_unpack). "
    "CONSEQUENCE: 'later commits fixed the crash' is not supported, AND 'the 194844c tree caused it' has no "
    "code-level candidate -- so the 2-of-5 concentration at 194844c is a property of WHEN those runs happened, "
    "not of what they ran. "
    "(B) THE OOM WINDOW: `journalctl -k --since '2026-09-13 05:00' --until '2026-09-13 05:35'` holds 43 oom/kill "
    "lines and TWO memcg OOM events -- 05:11:50 in scope hermes-worker-proc_723a5350c03f.scope (killed pytest, "
    "total-vm 12,251,072 kB / anon-rss 4,173,724 kB, plus 3 bash/timeout) and 05:32:44 in scope "
    "hermes-worker-proc_ff4c23113043.scope (33 kill lines: 12x python3 at ~340 MB anon-rss each, plus agy at "
    "157,664 kB). The DEFECT-22 core on disk is stamped 2026-09-13 05:18:10 -- six minutes after the first OOM "
    "event and fourteen before the second. The two disturbed runs therefore sit inside an active memory-pressure "
    "window on a box whose worker cgroups were being OOM-killed that morning. "
    "HONEST BOUNDARY: this is a correlation (n=2 disturbances in one window, NOT a rate) and no telemetry field "
    "causes or explains the SIGSEGV; it does not prove memory pressure produced it. But it is the first evidence "
    "that has a mechanism and a timestamp, and it makes the instrument gap concrete: the arc sidecar records only "
    "loadavg_before, so a 139 cannot today be told apart from a 139 that happened under an OOM storm."
)
d["instrument_gap_2026_09_13_1205"] = (
    "Opened as a unit: `.builder_queue/brief_defect22_env_telemetry.md` (passes `tools/check_brief.py`, "
    "PASS 0 invalid) -- the arc scripts' sidecars gain env_before/env_after + oom_kill_delta + "
    "journal_oom_kill_delta from a new collector `tools/arc_env_telemetry.sh`, with a PRESSURE=yes marker when the "
    "kernel killed anything during the run; gate `bash tools/gate_arc_lega_telemetry.sh` (L1 compared-against-source, "
    "L1b non-vacuity, L1c mem_peak liveness, L2 dry-run sidecar, L3 journal seam both directions, L4 no regression). "
    "RED-first captured at `output/d22_env_telemetry_gate_RED_absent.txt` (gate absent, rc=127) before implementation."
)
d["ledger_2026_09_13_1205"] = (
    "HEAD 5b423d0: 0 arc runs this tick (deliberate -- post-194844c the plain series stands at 12 runs / 0 "
    "disturbed, so a 13th plain green is noise; and with the crash path byte-identical at 194844c and HEAD, a "
    "re-run 'at the crashing head' would be the SAME experiment as a run at HEAD, not a new one -- the loop's own "
    "0/12 result already covers it). Work was instead the two measurements above plus the telemetry unit they imply."
)
d["supply_2026_09_13_1205"] = (
    "Live supply = THIS ticket only, re-measured this tick: roadmap census `python3 .builder_queue/"
    "census_roadmap_rows.py` -> 48 id rows / 0 open (the marker-less rows are the known GH-18/20/21/22/23/24/25 "
    "'checkmark without the literal done' false positives); GLYPH_BACKLOG.md BK-1..BK-14 + OBS-1 all promoted and "
    "landed; both ruling-cleared hardening items are CLOSED (DEFECT-17 (d) at 7a4208a, DEFECT-18 (a) at 11fe1ac). "
    "queue=1 == this ticket, so state=REPAIR_PENDING remains a LEVEL trigger on a defect with a 0/12 reproduction "
    "rate post-194844c."
)

T.write_text(json.dumps(d, indent=2) + "\n")
print("ticket updated; keys:", len(d))
