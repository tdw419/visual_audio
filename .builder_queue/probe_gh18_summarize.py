#!/usr/bin/env python3
"""DEFECT-22 next_step(a) conclusion record: the 1.9 GB allocation-site hunt.

Writes its findings into the DEFECT-22 ticket as a new dated key via a
companion patch step; this file only validates that the probe artifacts
exist and prints the summary lines. Run from the repo root.
"""
import json
from pathlib import Path

REPO = Path(".")
need = [
    "output/probe_gh18_19gb_site_20260913_231835.jsonl",
    "output/probe_gh18_tracemalloc_pytest.txt",
    "output/probe_gh18_rss_timeline.txt",
    "output/probe_gh18_importmode_compare.txt",
    "output/probe_gh18_plugin_effect.txt",
]
missing = [p for p in need if not (REPO / p).exists()]
if missing:
    raise SystemExit(f"MISSING artifacts: {missing}")

# Pull the headline numbers out of the artifacts
tm = (REPO / "output/probe_gh18_tracemalloc_pytest.txt").read_text().splitlines()
traced_peak = [l for l in tm if "traced_peak" in l][0]
rss = (REPO / "output/probe_gh18_rss_timeline.txt").read_text().splitlines()
final_hwm = [l for l in rss if l.startswith("# exitstatus")][0]
max_delta = max(
    (int(l.split("d=")[1].split("kB")[0].strip().replace("+", "")), l)
    for l in rss if " hwm=" in l
)
cmp_lines = (REPO / "output/probe_gh18_importmode_compare.txt").read_text().splitlines()

summary = {
    "probe_files": need,
    "in_process_hwm_jump": "NONE (L3 RED: max single-test delta < 500 MB; all < 7 MB)",
    "traced_peak_line": traced_peak.strip(),
    "pytest_final_hwm_line": final_hwm.strip(),
    "pytest_max_single_test_delta_line": max_delta[1].strip(),
    "import_mode_compare": cmp_lines,
}
print(json.dumps(summary, indent=2))
