#!/usr/bin/env python3
"""Roadmap supply audit — per-item, per-status-cell (builder cron probe).

Why this exists: the standing supply check used `^\\| *[A-Z]+-\\d+ *\\|`, which
silently misses suffixed ids (GH-8c, GH-26.4a/b/c, GH-26.5 = 5 rows on the
self-hosting roadmap). It also decided "done" from a whole-line checkmark, so a
stray ✅ in a description cell could mask a still-open status cell.

This probe parses every table row whose first cell is a bare id token, takes the
STATUS cell (first cell beginning with a state token) and decides open/closed
from that cell alone.

Usage:
  /usr/bin/python3 .builder_queue/probe_roadmap_state_audit.py [roadmap.md ...]
  (default: systems/GLYPH_SELF_HOSTING_ROADMAP.md systems/GLYPH_OSS_ROADMAP.md)

Measured 2026-09-12 at d480345:
  self-hosting: 51 id rows, 0 open  (strict regex counted only 46 rows)
  OSS lane:     13 id rows, 8 open  (GL-2 DRAFT/no token; GL-6..GL-12 QUEUED)
"""
import re
import sys

STRICT = re.compile(r"^\| *[A-Z]+-\d+ *\|")
TOKEN = re.compile(r"^(✅|⏳|⚠️|❌|BLOCKED\S*|DRAFT\b|QUEUED\b)")
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")

paths = sys.argv[1:] or [
    "systems/GLYPH_SELF_HOSTING_ROADMAP.md",
    "systems/GLYPH_OSS_ROADMAP.md",
]

for path in paths:
    total = strict_ids = 0
    open_rows, missed = [], []
    for i, line in enumerate(open(path, encoding="utf-8"), 1):
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not cells or not ID.fullmatch(cells[0]):
            continue
        total += 1
        if STRICT.match(line):
            strict_ids += 1
        else:
            missed.append((i, cells[0]))
        status = next((c for c in cells[1:] if TOKEN.match(c)), None)
        if status is None:
            open_rows.append((i, cells[0], "NO STATUS TOKEN"))
        elif "✅" not in status:
            open_rows.append((i, cells[0], status[:90]))

    print(f"[{path}] id rows={total} (strict regex={strict_ids}) open={len(open_rows)}")
    for i, rid, why in open_rows:
        print(f"  OPEN  line {i}: {rid} -> {why}")
    if missed:
        print(f"  strict regex missed {len(missed)}: " + ", ".join(r for _, r in missed))
