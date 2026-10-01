#!/usr/bin/env python3
"""fix_bk40_tail.py — drop the duplicated trailing '|' on the BK-40 row."""
p = "/home/jericho/projects/zion/projects/visual_audio/systems/GLYPH_BACKLOG.md"
with open(p) as f:
    lines = f.read().split("\n")
assert lines[66].startswith("| BK-40 |")
lines[66] = lines[66].replace("suite.** | |", "suite.** |")
with open(p, "w") as f:
    f.write("\n".join(lines))
print("tail now:", lines[66][-60:])
