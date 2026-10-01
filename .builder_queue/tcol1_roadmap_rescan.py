#!/usr/bin/env python3
"""TEST-COL-1 tick (2026-09-13): correct roadmap rescan.

The previous scan used `^\\| GH-` which silently skips every non-GH row id
(GL6-BUILD, GL7-BUILD, OS-SKEL-*, SUBSTOR-*, TEST-COL-*, GH-26.x...). Parse the
table properly: a row is OPEN unless its LAST cell carries a done marker.
"""
import re
import sys
from pathlib import Path

ROADMAP = Path("systems/GLYPH_SELF_HOSTING_ROADMAP.md")
rows = []
for i, line in enumerate(ROADMAP.read_text().splitlines(), 1):
    if not line.startswith("|"):
        continue
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    if len(cells) < 4:
        continue
    rid = cells[0]
    if not re.match(r"^[A-Za-z][A-Za-z0-9.\-]*$", rid) or rid in {"#", "Host component"}:
        continue
    status = cells[-1]
    done = bool(re.search(r"✅|DONE\b", status))
    rows.append((i, rid, done, status[:110]))

print(f"parsed {len(rows)} rows")
open_rows = [r for r in rows if not r[2]]
print(f"rows whose LAST cell lacks a done marker: {len(open_rows)}")
for i, rid, done, status in open_rows:
    print(f"  L{i}: {rid} :: {status}")
print("--- last 6 rows (any state) ---")
for i, rid, done, status in rows[-6:]:
    print(f"  L{i}: {rid} done={done} :: {status[:80]}")
