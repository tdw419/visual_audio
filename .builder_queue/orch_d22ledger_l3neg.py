"""L3 non-vacuity probe: a neutered parser must accept the bad ts (proves L3 discriminates)."""
import os
import sys

sys.path.insert(0, ".builder_queue")
import d22_ledger  # noqa: E402
from datetime import datetime  # noqa: E402

d22_ledger.parse_timestamp = lambda s: datetime(2000, 1, 1)
with open("/tmp/d22neg_probe.json", "w") as f:
    f.write('{"series_state": {}}')
try:
    d22_ledger.append_leg(
        "/tmp/d22neg_probe.json", leg=1, seed=1, head="x", crashes=0,
        oom_kill_delta=0, mem_peak=1, verdict="green", ts="2026-09-14 13:3x",
    )
    print("NEGATIVE LEG CONFIRMED: neutered parser accepted the bad ts -> L3 discriminates")
except ValueError as e:
    print("unexpected still refused:", e)
finally:
    if os.path.exists("/tmp/d22neg_probe.json"):
        os.remove("/tmp/d22neg_probe.json")
