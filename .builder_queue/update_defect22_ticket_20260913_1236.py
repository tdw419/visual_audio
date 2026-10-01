#!/usr/bin/env python3
"""Append this tick's ledger + supply-census keys to the DEFECT-22 ticket (cron af3e62239ce2).

Kept as a script (not an inline command) so the exact edit is reproducible evidence, matching
the pattern of the earlier update_defect22_ticket_*.py files in this directory.
"""
import json
import pathlib

TICKET = pathlib.Path(".builder_queue/DEFECT-22_arc_legA_instability.json")

data = json.loads(TICKET.read_text(encoding="utf-8"))

before = len(data)

data["ledger_2026_09_13_1236"] = (
    "No arc run this tick -- deliberate, and not a change in method: the tick's changed files are a NEW tool "
    "(tools/supply_census.py) and a NEW gate (tests/test_supply_census.py), with no engine/ABI/transpiler file "
    "touched, so an arc green would add nothing to a defect whose reproduction rate is 0/9 post-194844c. The "
    "unit worked instead was the lane's own supply sensor: SUPPLY-CENSUS-1 promoted (98e0365) and landed "
    "(a697a4e). Own census re-run at a697a4e: python3 tools/supply_census.py -> TOTAL=59 OPEN=0."
)

data["supply_census_2026_09_13_1236"] = (
    "The lane's supply argument no longer rests on a queue-side script: python3 tools/supply_census.py now "
    "produces it (5/5 gate tests/test_supply_census.py, receipt systems/RECEIPT_SUPPLY_CENSUS.md). Live supply "
    "is still THIS ticket only -- roadmap 0 open rows, GLYPH_BACKLOG table exhausted (BK-1..BK-14 + OBS-1), and "
    "the tool's own verdict at this head is TOTAL=59 OPEN=0. Jericho's pending pick is unchanged: renew lane "
    "supply / accept DEFECT-22 as a documented stability bound and release the level trigger / re-point or slow "
    "the cron."
)

TICKET.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"keys before={before} after={len(data)} path={TICKET}")
print(f"status unchanged: {data['status'][:80]}...")
