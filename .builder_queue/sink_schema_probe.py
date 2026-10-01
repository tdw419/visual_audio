#!/usr/bin/env python3
"""Print the key set of the first record in a JSONL sink (schema probe)."""
import json
import sys

with open(sys.argv[1]) as fh:
    rec = json.loads(fh.readline())
print("keys:", sorted(rec.keys()))
print("sample:", json.dumps({k: rec[k] for k in list(rec)[:6]}, indent=1)[:400])
