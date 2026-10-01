"""Fix leg 24 (rebuild from the real leg entry, not the 0055 no-run annotation), flush, recompute."""
import json
import re
import sys

sys.path.insert(0, ".builder_queue")
from d22_ledger import recompute_ledger

LEDGER = ".builder_queue/DEFECT-22_arc_legA_instability.json"
d = json.load(open(LEDGER))

src = d["ledger_2026_09_14_0100"]
assert "GREEN:" in src, "expected real leg-24 entry with GREEN marker"
seed_m = re.search(r"seed (\d+)", src)
head_m = re.search(r"head ([0-9a-f]{7,40})", src)
mem_m = re.search(r"mem_peak=([\d,]+)", src)
crash_m = re.search(r"faulthandler_crashes=(\d+)", src)
oom_m = re.search(r"oom_kill_delta=(\d+)", src)
d["ledger_leg24"] = {
    "leg": 24,
    "seed": int(seed_m.group(1)) if seed_m else None,
    "head": head_m.group(1) if head_m else None,
    "crashes": int(crash_m.group(1)) if crash_m else 0,
    "oom_kill_delta": int(oom_m.group(1)) if oom_m else 0,
    "mem_peak": int(mem_m.group(1).replace(",", "")) if mem_m else None,
    "verdict": "green",
    "backfilled_from": "ledger_2026_09_14_0100",
}
with open(LEDGER, "w") as f:
    json.dump(d, f, indent=2)

state = recompute_ledger(LEDGER)
print("final series_state:", json.dumps(state))
d2 = json.load(open(LEDGER))
from collections import Counter
objs = [v for v in d2.values() if isinstance(v, dict) and "verdict" in v]
print("result objects:", len(objs), dict(Counter(o["verdict"] for o in objs)))
print("updated parseable:", bool(state["updated"]))
