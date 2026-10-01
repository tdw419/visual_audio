#!/usr/bin/env python3
"""dbg: characterize the RED-only :pc_ entries (round-7 analysis)."""
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

repo = Path("/home/jericho/projects/zion/projects/visual_audio")
for p in (str(repo), str(repo / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

out = subprocess.run(
    [".venv/bin/python", ".builder_queue/probe_bk24_seed_diff.py"],
    cwd=repo, capture_output=True, text=True).stdout
red_only = []
both = []
for ln in out.splitlines():
    m = re.match(r"^(\*\*)?\s*:pc_([0-9a-f]+)\s+G=(\S+)\s+R=(\S+)", ln)
    if not m:
        continue
    star, rv, g, r = m.group(1), int(m.group(2), 16), m.group(3), m.group(4)
    if star:
        red_only.append(rv)
    else:
        both.append(rv)
vals = red_only
print("red-only count:", len(vals))
print("first:", hex(vals[0]), "last:", hex(vals[-1]))
print("contiguous 4-byte:", all(b - a == 4 for a, b in zip(vals, vals[1:])))
print("0x4fc word:", 0x4FC // 4, "cell:", 0x4FC // 4)
print("max shared:", hex(both[-1]))
# qsort spans: green 0x400..? red 0x4b0..? — the red-only entries start at
# 0x4fc which is past qsort@0x4b0. GREEN max shared entry vs RED-only start.
shared_max = max(both)
print("shared entries span: 0x00 ..", hex(shared_max))
