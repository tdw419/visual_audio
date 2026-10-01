#!/usr/bin/env python3
"""Summarize a suite_iso_harness JSON sweep (builder cron, DEFECT-22)."""
import json
import sys
from collections import Counter

path = sys.argv[1]
recs = json.load(open(path))
print("files:", len(recs))
print("verdicts:", dict(Counter(r["verdict"] for r in recs)))
for r in recs:
    if r["verdict"] != "PASS":
        print("NONPASS", r["verdict"], r["path"], r["duration_s"], r["rc"],
              r["last_line"][:140])
print("--- slowest 8 ---")
for r in sorted(recs, key=lambda x: -x["duration_s"])[:8]:
    print(f"{r['duration_s']:7.2f}s {r['verdict']:<7} {r['path']} "
          f"pass={r['counts']['passed']} fail={r['counts']['failed']} "
          f"coll={r['counts']['collected']}")
print("total collected:", sum(r["counts"]["collected"] for r in recs))
