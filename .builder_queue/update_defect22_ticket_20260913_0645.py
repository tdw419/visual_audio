#!/usr/bin/env python3
"""Record the gate's RED-leg revision pin on the DEFECT-22 ticket (tick 2026-09-13 ~06:4x)."""
import json

P = ".builder_queue/DEFECT-22_arc_legA_instability.json"
d = json.load(open(P))

d["instrument_fix_2026_09_13_0635"] += (
    " GATE CAVEAT (self-caught one commit after it landed): the gate's RED leg originally recovered the"
    " pre-fix script with `git show HEAD:tools/arc_lega.sh`, which stops working the moment the fix is in"
    " HEAD — measured at e230a7c, the gate exited 2 with 'SETUP FAIL: recovered script does not carry the"
    " seed-only TAG line; gate premise stale'. The pre-fix script is now pinned to revision 6868694 (the"
    " commit that introduced arc_lega.sh), with an added premise check that the pinned script has no"
    " `_rerun` guard; rc=0 re-measured at e230a7c."
)

json.dump(d, open(P, "w"), indent=2)
print("updated", P, "| keys:", len(d))
