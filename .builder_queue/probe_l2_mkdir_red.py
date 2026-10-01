#!/usr/bin/env python3
"""RED probe — L2-FILES sub-step 3 (mkdir/rmdir under allow-scoped root).

Measures the tree BEFORE implementation: `mkdir`/`rmdir` are not routed by
the shell's verb table, so both spellings fall through to ERR:UNKNOWN_CMD.
Keep-legs pin the grammar class that must not move (echo stays glyph-body,
bogus verb stays ERR). RED criterion: mkdir+rmdir legs 4/4 ERR; GREEN
criterion (post-landing): 4/4 structured results + keep-legs unchanged.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools"), str(REPO / "experiments")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from experiments.glyph_l1_shell import GlyphL1Shell  # noqa: E402

sh = GlyphL1Shell()

mkdir_legs = [
    "mkdir d1",
    "mkdir a/b",
]
rmdir_legs = [
    "rmdir d1",
]
keep_legs = [
    ("e hello", " hello"),
    ("z bogus", "ERR:UNKNOWN_CMD"),
]

fails = 0
for leg in mkdir_legs + rmdir_legs:
    out = sh.turn(leg)
    ok = out.startswith("ERR:")  # RED state: any ERR (incl. UNKNOWN_CMD) = not implemented
    print(f"{'RED' if ok else 'GREEN?'} mkdir/rmdir leg {leg!r} -> {out!r}")
    fails += 1 if ok else 0

# escape containment must refuse either way (this one already REFUSES on the
# pre-landing tree via resolve(); it is a keep-leg, not a RED leg)
esc = sh.turn("mkdir ../escape")
print(f"keep escape-refusal leg: {esc!r} (expect ERR...)")
if not esc.startswith("ERR"):
    fails += 1

for leg, want in keep_legs:
    out = sh.turn(leg)
    ok = out == want
    print(f"{'ok' if ok else 'FAIL'} keep-leg {leg!r} -> {out!r}")
    fails += 0 if ok else 1

print(f"RED_PROBE: {fails} failing legs (RED-first expects mkdir/rmdir legs in ERR state)")
sys.exit(0 if fails else 1)
