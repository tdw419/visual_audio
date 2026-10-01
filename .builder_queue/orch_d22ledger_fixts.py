"""Fix backfill loose ends: drop ts:None keys, identify the unknown-verdict leg, recompute."""
import json
import sys

sys.path.insert(0, ".builder_queue")
from d22_ledger import recompute_ledger

LEDGER = ".builder_queue/DEFECT-22_arc_legA_instability.json"
d = json.load(open(LEDGER))

for k, v in list(d.items()):
    if isinstance(v, dict) and v.get("ts") is None and "backfilled_from" in v:
        del v["ts"]
    if isinstance(v, dict) and v.get("verdict") == "unknown":
        print("unknown verdict leg:", v["leg"], "from", v.get("backfilled_from"))

state = recompute_ledger(LEDGER)
print("recomputed:", json.dumps(state))
d2 = json.load(open(LEDGER))
print("updated now parseable:", bool(d2["series_state"]["updated"]))
