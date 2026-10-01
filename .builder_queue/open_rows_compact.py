#!/usr/bin/env python3
"""Compact open-row scan for systems/GLYPH_SELF_HOSTING_ROADMAP.md.

Prints one line per row whose status cell does NOT contain a done mark,
so the orchestrator can pick the next target without ingesting the file.
Usage: python3 .builder_queue/open_rows_compact.py [path]
"""
import re
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "systems/GLYPH_SELF_HOSTING_ROADMAP.md"
rowid = re.compile(r"^(GH|BK|GL|WF|DEFECT|OS-SKEL|ENG|RES)-?\d")
n = 0
for i, line in enumerate(open(path), 1):
    if not line.startswith("|"):
        continue
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    if len(cells) < 4:
        continue
    rid = cells[0]
    if not rowid.match(rid):
        continue
    n += 1
    blob = " ".join(cells[1:])
    state = next((c for c in reversed(cells) if c), "(no state cell)")
    last_done = state.rfind("\u2705")
    last_queued = state.rfind("\u23f3")
    done = last_done != -1 and last_done > last_queued
    marker = "DONE" if done else "OPEN"
    tail = state[-120:].replace("\n", " ")
    print(f"L{i:>4} {marker} {rid:<12} :: {tail}")
print(f"-- {n} rows scanned --")
