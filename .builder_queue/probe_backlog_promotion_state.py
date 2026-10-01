#!/usr/bin/env python3
"""Mechanical check: is every GLYPH_BACKLOG.md row present (and closed) in GLYPH_SELF_HOSTING_ROADMAP.md?

The backlog table has NO status column (ID | Item | Gate spec | Prereq | Source), so
"exhausted" can only mean "every id was promoted into the roadmap and closed there".
This checks that by id, and reads the roadmap's status cell only.
"""
import re
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]
BACKLOG = REPO / "systems/GLYPH_BACKLOG.md"
ROADMAP = REPO / "systems/GLYPH_SELF_HOSTING_ROADMAP.md"

DONE_TOKENS = ("\u2705", "DONE", "done")
OPEN_TOKENS = ("QUEUED", "queued", "\u23f3", "DRAFT", "BLOCKED", "defect", "\u26a0")

backlog_rows = {}
for line in BACKLOG.read_text().splitlines():
    m = re.match(r"^\|\s*([A-Z]+-\d+[a-z0-9]*)\s*\|", line)
    if m:
        backlog_rows[m.group(1)] = line

# roadmap: map id -> status cell (first cell that starts with a state-ish token,
# else the last cell; report it raw so a human can judge)
roadmap_cells = {}
for line in ROADMAP.read_text().splitlines():
    m = re.match(r"^\|\s*([A-Z]+-\d+[a-z0-9]*)\s*\|", line)
    if not m:
        continue
    rid = m.group(1)
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    roadmap_cells.setdefault(rid, cells)

unpromoted, promoted_open, promoted_done = [], [], []
for bid in sorted(backlog_rows, key=lambda s: (s.split("-")[0], int(re.search(r"\d+", s).group()))):
    if bid not in roadmap_cells:
        unpromoted.append(bid)
        continue
    cells = roadmap_cells[bid]
    state = ""
    for c in cells[2:]:
        if re.match(r"^(\u2705|\u23f3|\U0001f7e1|\u26a0|\u274c|DONE|DRAFT|QUEUED|BLOCKED)", c):
            state = c
            break
    if not state:
        state = cells[-1]
    if any(t in state for t in DONE_TOKENS):
        promoted_done.append(bid)
    else:
        promoted_open.append((bid, state[:90]))

print(f"backlog id rows            : {len(backlog_rows)}")
print(f"  promoted & closed        : {len(promoted_done)}  {promoted_done}")
print(f"  promoted but NOT closed  : {len(promoted_open)}  {promoted_open}")
print(f"  NEVER promoted (eligible): {len(unpromoted)}  {unpromoted}")
print("VERDICT:", "BACKLOG EXHAUSTED" if not unpromoted and not promoted_open else "SUPPLY EXISTS")
