#!/usr/bin/env python3
"""append_item21_queue_af3e.py — mark item-21 landed in QUEUE_STATE.json."""
import json

p = ".builder_queue/QUEUE_STATE.json"
d = json.load(open(p))
for q in d["queue"]:
    if q["id"] == "item-21":
        q["status"] = "landed"
d["updated"] = "2026-09-25T21:10:00-05:00"
d["updated_by"] = "builder af3e62239ce2 (item-21 fixture synthesis landed, a25ddbac)"
json.dump(d, open(p, "w"), indent=2)
print("queue now:", [(q["id"], q["status"]) for q in d["queue"]])
