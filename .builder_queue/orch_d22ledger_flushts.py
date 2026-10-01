"""Remove ts:None from backfilled objects ON DISK, then recompute series_state."""
import json
import sys

sys.path.insert(0, ".builder_queue")
from d22_ledger import recompute_ledger

LEDGER = ".builder_queue/DEFECT-22_arc_legA_instability.json"
d = json.load(open(LEDGER))
removed = 0
for k, v in d.items():
    if isinstance(v, dict) and "backfilled_from" in v and "ts" in v and v["ts"] is None:
        del v["ts"]
        removed += 1
with open(LEDGER, "w") as f:
    json.dump(d, f, indent=2)
print("ts:None removed from", removed, "backfilled objects")

state = recompute_ledger(LEDGER)
print("final series_state:", json.dumps(state))
