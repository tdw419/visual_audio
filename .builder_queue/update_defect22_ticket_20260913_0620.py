#!/usr/bin/env python3
"""Ticket update for DEFECT-22 after the 2026-09-13 06:2x tick (builder cron af3e62239ce2).

Adds the tick's MEASURED facts and restates the next step. Idempotent: re-running
overwrites the same two keys.
"""
import json
from pathlib import Path

T = Path(".builder_queue/DEFECT-22_arc_legA_instability.json")
d = json.loads(T.read_text())

d["status"] = (
    "OPEN — owner named by faulthandler (tests/test_gh22_device_driver_abi.py:174 "
    "test_gh22_driver_abi_image_bakes -> _bake -> build_default_atlas -> register -> "
    "run_generated -> glyph_isa_v2.step:561 _check_alignment), isolation-clean (52/52 "
    "per-file PASS); the crash is a VICTIM frame (`x % INSTR_WIDTH` cannot segfault), so "
    "it originates elsewhere; MEASURED 2026-09-13 06:2x: leg A runs under pytest-randomly "
    "4.0.1 with a RANDOM seed every run, so runs 1-5's file orders are unrecoverable and "
    "no arc run before this tick is replayable"
)

d["ledger_2026_09_13_0620"] = (
    "81f0a42: 1 run / 0 disturbed, seed PINNED and logged "
    "(SEED=1210907384 tools/arc_lega.sh -> 324 passed / 1 skipped / 138.04 s / rc=0 / "
    "0 crashes; output/arc_lega_seed1210907384.{txt,json}). Post-194844c: 7 runs / 0 "
    "disturbed. Whole series n=12 / 2 disturbed, both at 194844c. "
    "Concentrated-context probe (owner + 8 wgpu-touching leg-A files, 20 reps, ONE "
    "process): 920 passed / 0 crashes / 82.64 s, load 0.47 "
    "(output/defect22_gpu_context_reps.txt)."
)

d["measured_order_randomization"] = {
    "fact": "pytest-randomly 4.0.1 IS loaded for the arc interpreter",
    "instrument": "/usr/bin/python3 -m pytest <file> --co -q -p randomly --randomly-seed=N",
    "evidence": (
        "tests/test_gh6_syscalls.py: collection order differs between seed 111 and seed "
        "222 (order identical would mean the plugin was inactive); plugin path "
        "/home/jericho/.local/lib/python3.12/site-packages/pytest_randomly/__init__.py; "
        "no 'no:randomly' guard in pytest.ini/pyproject.toml/setup.cfg/conftest.py; the "
        "-v run logs carry 'Plugins: {... randomly: 4.0.1}' and 'Using --randomly-seed=NNN'"
    ),
    "consequences": [
        "every leg-A run chooses a different file order; two runs are not the same experiment",
        "the -q crash runs 1-5 logged no seed (header suppressed) => their orders are lost forever",
        "run 3's `-p no:randomly` (receipt line 27) is a CONFOUND, not a fix",
        "`.builder_queue/count_run2_progress.py`'s premise 'no pytest-randomly is installed, "
        "so order == collection order' is FALSE (docstring corrected this tick)",
        "a RED under randomized order is unreplayable; tools/arc_lega.sh now pins and records the seed",
    ],
    "not_measured": (
        "whether any ordering is more crash-prone: no seed is known for either disturbed run, "
        "so the order hypothesis stays a hypothesis"
    ),
}

d["next_step"] = (
    "REPLAYABLE FROM THIS TICK ON: run leg A with `SEED=<n> bash tools/arc_lega.sh` (pins "
    "pytest-randomly, logs the seed + a JSON sidecar, replayable). If a SIGSEGV recurs: (1) "
    "take the seed from the sidecar and re-run that seed once to test replayability, (2) run "
    "-v so the crash names its own test, (3) only then bisect from the faulthandler frame "
    "outward, owner file last. Does NOT need a rate: a pinned-order RED is the target. Do not "
    "re-run the isolation sweep (already 52/52) or the allocator instruments (already clean x2)."
)

d["blocked_work"] = (
    "none — 'arc leg A green at HEAD' stands for 10 of 12 runs (7/7 since 194844c), but any "
    "such receipt must carry the stability bound (2 of 12 disturbed on 2026-09-13) AND the "
    "order caveat: until this tick no run's file order was recorded, so the 7 green runs are "
    "7 different experiments, not 7 repetitions of one."
)

see = d.get("see", [])
r = "systems/RECEIPT_DEFECT22_ORDER_RANDOMIZATION_MEASURED.md"
if r not in see:
    see.append(r)
d["see"] = see

T.write_text(json.dumps(d, indent=2) + "\n")
print("ticket updated; keys:", len(d))
print("status[:90]:", d["status"][:90])
