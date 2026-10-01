"""Orchestrator check after backfill (D22-LEDGER-1)."""
import json

d = json.load(open(".builder_queue/DEFECT-22_arc_legA_instability.json"))
print("total keys:", len(d))
print("series_state:", json.dumps(d["series_state"]))
objs = [v for v in d.values() if isinstance(v, dict) and "verdict" in v]
print("result objects:", len(objs))
from collections import Counter
print("verdicts:", dict(Counter(o["verdict"] for o in objs)))
legs = sorted(o["leg"] for o in objs)
print("legs:", legs[0], "..", legs[-1], "count:", len(legs), "dupes:", [l for l in set(legs) if legs.count(l) > 1])
prose = [k for k, v in d.items() if isinstance(v, str) and k.startswith("ledger_")]
print("prose entries preserved:", len(prose))
