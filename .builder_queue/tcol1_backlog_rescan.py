#!/usr/bin/env python3
"""Backlog rescan for the 2026-09-13 TEST-COL-1 tick: any BK row still unpromoted?"""
import re
from pathlib import Path

p = Path("systems/GLYPH_BACKLOG.md")
print("exists:", p.exists())
if p.exists():
    rows = [(i, l) for i, l in enumerate(p.read_text().splitlines(), 1) if re.match(r"^\| *BK-\d+", l)]
    print("BK rows:", len(rows))
    for i, l in rows:
        rid = l.split("|")[1].strip()
        # last non-empty cell
        cells = [c.strip() for c in l.strip().strip("|").split("|") if c.strip()]
        last = cells[-1] if cells else ""
        print(f"  L{i} {rid} done={bool(re.search(r'✅|DONE', last))}")
