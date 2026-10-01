#!/usr/bin/env python3
"""Append one ledger key to the DEFECT-22 ticket: the memory hog named this tick.

Adjacent measurement, not a crash finding. Receipt: systems/RECEIPT_SUITE_ISO2_HOG_NAMED.md.
"""
import json
import pathlib

p = pathlib.Path(__file__).resolve().parent / "DEFECT-22_arc_legA_instability.json"
d = json.loads(p.read_text())
d["memory_hog_named_2026_09_13_1245"] = (
    "Adjacent measurement, not a crash finding (probe .builder_queue/probe_peak_rss_sweep.py, receipt "
    "systems/RECEIPT_SUITE_ISO2_HOG_NAMED.md): a per-file peak-RSS sweep of tools/ + systems/ (113 files, serial, "
    "os.wait4 attribution) names the 11:28 OOM's class - tools/test_alpine_virtio_fix.py and tools/test_virtio.py "
    "each peak at 3,916,4xx kB = 3824.6 MB, 93.4% of the 4 GiB worker cap, and at -w 1 the sweep COMPLETED under "
    "that cap. Isolated in a fresh process: those files are SpatialRV64ICore(64 MiB) + step(); ctor 326 MB, "
    "load_program 365 MB, then the FIRST 1,000 steps -> 3745 MB and flat to 100k steps (one-time allocation inside "
    "step(), not a per-step leak; ~51x the guest RAM in host RSS). HYPOTHESIS (labeled, not claimed) for this "
    "ticket's own 3.93 GB leg-A peak: same class - 51 files under tests/ construct SpatialRV64ICore; the "
    "measurement that would settle it (per-test RSS attribution inside a leg-A run) was NOT run. No arc run this "
    "tick (plain ledger unchanged: 13 runs / 0 disturbed post-194844c)."
)
p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
print("keys", len(d), "bytes", p.stat().st_size)
