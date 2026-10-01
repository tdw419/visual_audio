#!/usr/bin/env python3
"""Add the instrument smoke-test ledger to the DEFECT-22 ticket (tick 2026-09-13 ~06:4x).

The smoke test is NOT a new probe: it verifies the fixed instrument end to end (real pytest
path, real artifact naming). Recorded separately from the stability ledger so the run tally
cannot be inflated by it.
"""
import json

P = ".builder_queue/DEFECT-22_arc_legA_instability.json"
d = json.load(open(P))

d["ledger_2026_09_13_0640"] = (
    "SMOKE TEST of the fixed instrument (not a defect probe): `SEED=424242 bash tools/arc_lega.sh` "
    "at 3b96989 -> rc=0, 324 passed / 1 skipped in 135.73 s, crashes=0, artifacts "
    "output/arc_lega_seed424242_3b96989.{txt,json} — the name carries the head, which is the fix "
    "working end to end. It also closes the one gap the gate's stub legs leave: the real pytest "
    "invocation under the new naming. Its verdict is green, so it adds nothing to the defect "
    "knowledge (now 10 runs / 0 disturbed post-194844c; whole series n=15 / 2 disturbed, both at "
    "194844c — still two one-offs, no rate claimed, and this run is not evidence of a rate)."
)

d["instrument_fix_2026_09_13_0635"] += (
    " End-to-end confirmation after the commit: SEED=424242 bash tools/arc_lega.sh at 3b96989 -> "
    "rc=0 / 324 passed / 1 skipped / 0 crashes, artifacts output/arc_lega_seed424242_3b96989.{txt,json}."
)

json.dump(d, open(P, "w"), indent=2)
print("updated", P, "| keys:", len(d))
