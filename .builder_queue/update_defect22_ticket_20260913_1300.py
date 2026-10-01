#!/usr/bin/env python3
"""Append one ledger key to the DEFECT-22 ticket: leg A's per-file peak RSS measured.

Adjacent measurement, not a crash finding. Receipt: systems/RECEIPT_DEFECT22_LEGA_PER_FILE_RSS.md.
"""
import json
import pathlib

p = pathlib.Path(__file__).resolve().parent / "DEFECT-22_arc_legA_instability.json"
d = json.loads(p.read_text())
d["lega_per_file_rss_2026_09_13_1255"] = (
    "Adjacent measurement, not a crash finding (probe .builder_queue/probe_peak_rss_sweep.py unchanged, md5 "
    "27bec991fc689383330500617a0160d5; receipt systems/RECEIPT_DEFECT22_LEGA_PER_FILE_RSS.md). Settles the prior "
    "tick's labeled hypothesis for leg A. Population = leg A's own pinned 52-file list (arc_lega.sh:52-53 shape), "
    "serial, -t 30, --python /usr/bin/python3 (the arc's own PY, not the venv), 205 s, artifact "
    "output/probe_peak_rss_lega_20260913.jsonl (md5 007daffe49200f5421c784d3aa17029b, 52 START/52 END paired). "
    "RESULT: 51 PASS / 1 TIMEOUT (test_gh20_fs_v2.py, -t 30 budget, not a product verdict); max 2654.3 MB "
    "(tests/test_gh26_emit_admit.py) and 2652.9 MB (tests/test_gh18_syscall_abi.py); median 718.6 MB; min 114.1 MB; "
    "2 files >= 1 GiB; 40/52 >= 512 MiB; 42/52 >= 256 MiB. HYPOTHESIS REFUTED for leg A: grep -l SpatialRV64ICore "
    "over the 52 files = 0 matches, so the tools/ hog class (SpatialRV64ICore(64 MiB) + first step() -> ~3.4 GB) is "
    "NOT what makes leg A heavy. Measured import floor instead: 'import torch' = 514 MB in a fresh process, and the "
    "heavy-group test modules peak at 523-525 MB on bare import vs 43-49 MB for light ones; the ~890 MB cluster is "
    "torch + ~370 MB test body, the two 2.6 GB files are torch + ~2.1 GB test body whose allocation is NOT "
    "identified (next probe, named not run: per-test-id attribution inside those two files). COMPARISON: the leg-A "
    "capture artifact output/arc_lega_capture_seed2026091304_9bd8dd2.json (head 9bd8dd2, seed 2026091304) records "
    "env_before.mem_peak_bytes 17,350,656 -> env_after 3,929,948,160 = 3.66 GiB = 91.5% of the 4 GiB scope cap, "
    "oom_kill_delta 0; the in-run peak exceeds the largest isolated per-file peak by ~1.28 GB (single-process leg A; "
    "causes not measured). Consequence as arithmetic only: the arc's own leg A runs at ~91.5% of the memcg cap that "
    "OOM-killed workers twice on 2026-09-13 morning. NO policy decided (no cap, exclusion or default changed), no arc "
    "run this tick so the stability ledger is unchanged, and the memory-pressure link to this ticket's two 05:1x/05:3x "
    "disturbances remains correlation (n=2), no rate, no causal claim. No teleop read."
)
p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
print("keys", len(d), "bytes", p.stat().st_size)
