#!/usr/bin/env python3
"""Append the leg-1b landing record to the SUITE-FIX-1 roadmap row (line 355)."""
import re

PATH = "systems/GLYPH_SELF_HOSTING_ROADMAP.md"
with open(PATH) as f:
    lines = f.readlines()

assert lines[354].startswith("| SUITE-FIX-1"), "row moved; re-check line number"

addendum = (
    " **leg 1b (wordbook) landed 2026-09-13 22:3x** (builder cron `af3e62239ce2`, orchestrator-implemented — "
    "2 live agy PIDs from a sibling session were already in this cwd, so no fresh delegate was spawned; commit `cc3e753`): "
    "`RULING_standing_authorization.md:25` (Option (a)) unblocked it — `tests/test_glyph_wordbook_lookup.py` "
    "**0/2 FileNotFoundError → 2 passed (rc 0, 0.14s)**, force-added past the (now root-anchored) `test_*.py` ignore. "
    "Mechanism: expected colour queried LIVE from tracked `db/wordbase.db` (50448→#9050FD, 124061→#FF0000), scratch "
    "in-array bake using `tools/build_wordbook.py`'s layout contract (pixel (id % 4096, id // 4096)), no committed PNG "
    "binary, no frozen hash constants; DB-absent/colour-missing → skip-with-reason (environment class, per the same "
    "ruling line 26). Non-vacuity probe `WB_PROBE_WRONG_BAKE=1` (bake holds 0182FE, DB is truth) → **2 failed rc 1**; "
    "PROBE DEFECT recorded: probe attempt 1 neutered `_db_color` itself so expected==baked and stayed GREEN — caught "
    "and re-aimed at the bake/expect boundary. NOT proven: WGSL twin leg (none exists for this module), the full "
    "126k-row bake, VCC hash pinning (retired by the ruling). **Row stays open** for nothing mechanical — all named "
    "files/legs are now closed; the remaining sweep-level FAILs (test_mt2_large_scale, test_pixel_embeddings, "
    "test_pixel_os_listener_uart, test_synthesis_equivalence) are the sibling lane's in-flight dirty files per "
    "RECEIPT_SUITE_XV6_1 §4. **SUITE-FIX-1 can be marked ✅ next tick after a fresh file-by-file verdict sweep.\""
)
lines[354] = lines[354].rstrip("\n") + addendum + "\n"
with open(PATH, "w") as f:
    f.writelines(lines)
print("appended; row length now", len(lines[354]))
