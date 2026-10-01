"""Inspect edge cases before D22-LEDGER-1 backfill: leg 71 (no GREEN marker), dup leg 24, missing-leg entries."""
import json
import re

d = json.load(open(".builder_queue/DEFECT-22_arc_legA_instability.json"))

print("=== entries without GREEN: or RED markers ===")
for k, v in d.items():
    if isinstance(v, str) and k.startswith("ledger_"):
        m = re.search(r"leg #(\d+)", v)
        if m and "GREEN:" not in v and not re.search(r"\bRED\b", v):
            print(f"--- {k} (leg {m.group(1)}):")
            print(v[:400])

print()
print("=== leg 24 dup ===")
for k, v in d.items():
    if isinstance(v, str) and k.startswith("ledger_") and re.search(r"leg #24\b", v):
        print(f"--- {k}:")
        print(v[:300])

print()
print("=== two sample missing-leg entries ===")
shown = 0
for k, v in d.items():
    if isinstance(v, str) and k.startswith("ledger_") and "leg #" not in v and shown < 2:
        print(f"--- {k}:")
        print(v[:400])
        shown += 1
