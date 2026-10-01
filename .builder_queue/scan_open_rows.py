#!/usr/bin/env python3
"""Scan GLYPH_SELF_HOSTING_ROADMAP.md for open (unresolved) rows.

Prints every roadmap row whose status cell's LAST transition marker is not a
done marker. A row like "⏳ queued ... → ✅ done ..." is RESOLVED (its last
marker is ✅); "⏳ ... → ✅ done ... → ⏳ re-opened" is OPEN. Uses last-marker
logic rather than a bare '✅ done' substring, which false-positived on rows
whose done note was formatted "✅ **done" (BK-13/GL6-BUILD/GL7-BUILD were all
listed as open by the pre-2026-09-18 committed version — measured this tick).

Run from anywhere; the roadmap path resolves from this file's location.
Exit 0 always; open rows (if any) are printed to stdout, one per line.
"""
import os

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
path = os.path.join(_REPO, "systems", "GLYPH_SELF_HOSTING_ROADMAP.md")
lines = open(path, encoding="utf-8").read().splitlines()
for i, l in enumerate(lines, 1):
    if not l.strip().startswith("|"):
        continue
    cells = [c.strip() for c in l.strip().strip("|").split("|")]
    if len(cells) < 2:
        continue
    status = cells[-1]
    # a row is open if its LAST transition marker is not a done marker
    last_done = status.rfind("✅")
    last_q = max(status.rfind("⏳"), status.rfind("⚠️"))
    if "✅" not in status and "⏳" not in status and "⚠️" not in status:
        continue
    if last_done > last_q:
        continue  # resolved
    print(i, "|", cells[0][:40], "|", status[:220])
