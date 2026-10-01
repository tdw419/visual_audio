#!/usr/bin/env python3
"""Diff two suite_iso_harness sink JSONLs by file: verdict, collected, pass/fail."""
import json
import sys
from pathlib import Path

old_p, new_p = sys.argv[1], sys.argv[2]


def load(path):
    recs = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        key = r.get("path") or r.get("file")
        recs[key] = r
    return recs


old, new = load(old_p), load(new_p)
print(f"old records={len(old)} new records={len(new)}")
only_old = sorted(set(old) - set(new))
only_new = sorted(set(new) - set(old))
if only_old:
    print("files only in OLD:", *only_old, sep="\n  ")
if only_new:
    print("files only in NEW:", *only_new, sep="\n  ")

for key in sorted(set(old) & set(new)):
    o, n = old[key], new[key]
    ov, nv = o.get("verdict"), n.get("verdict")
    oc, nc = o.get("counts", {}), n.get("counts", {})
    if ov != nv or oc != nc:
        print(f"DELTA {key}: verdict {ov}->{nv} counts {oc}->{nc}")
