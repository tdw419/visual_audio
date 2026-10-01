#!/usr/bin/env python3
"""Add the clean-tree landing verification key to the DEFECT-22 ticket."""
import json
import pathlib

P = pathlib.Path("/home/jericho/projects/zion/projects/visual_audio/.builder_queue/DEFECT-22_arc_legA_instability.json")
d = json.loads(P.read_text(encoding="utf-8"))

d["landing_verified_2026_09_13_1345"] = (
    "846b784 (DEFECT-22d, the L6 environment note) RE-RUN on a CLEAN tree by the orchestrator, not trusted: "
    "bash tools/gate_L6_env_skip.sh -> rc=0 (output/d22d_gate_L6_env_skip_green.txt), legs printed literally - "
    "H1 pinned pre-fix gate rc=1 (failing: L6 FAIL ) vs working tree rc=0 (failing: none) under the same "
    "non-crashing stub; H2 neutered sweep rc=1 (failing: L6b-alt FAIL ); H3 real fixture rc=0 with "
    "'L6b RED observed'; H4 gate_arc_lega_capture.sh rc=0 (failing: none) plus naming/telemetry/record_survival "
    "rc=0; /var/crash holds 0 reports and git status --short -uno is empty before and after. Supply re-measured "
    "independently this tick: python3 tools/supply_census.py -> TOTAL=59 OPEN=0. Canonical arc NOT re-run for this "
    "change (the edited file is a gate imported by no test; H3/H4 drive it end to end) - the tick's one arc run was "
    "a capture-series run launched BEFORE the edit (see ledger_2026_09_13_1330)."
)

P.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("keys:", len(d))
