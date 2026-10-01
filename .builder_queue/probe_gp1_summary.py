#!/usr/bin/env python3
"""Per-capture top-syscall summary for the GP-1 receipt."""
import json
from collections import Counter

counts = {}
for cap in ["cap1", "cap2", "cap3", "cap4", "cap5"]:
    d = json.load(open(f"corpus_build/{cap}/trace.json"))
    c = Counter(s["name"] for s in d["syscalls"])
    counts[cap] = c
    print(f"{cap}: total={d['counts']['total']} conv={d['counts']['converted']} "
          f"unfin={d['counts']['skipped_unfinished']} top5={c.most_common(5)}")

batch = Counter()
for c in counts.values():
    batch.update(c)
print("BATCH top10:", batch.most_common(10))
print("BATCH total syscalls:", sum(batch.values()))
