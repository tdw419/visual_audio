#!/usr/bin/env python3
"""RED probe — L2-FILES sub-step 4 (>> append mode + rm -f quiet semantics).

Measures the tree BEFORE implementation:
1. `write >> file text` or `echo text >> file` are not routed as append ops;
   currently `write >>` writes to a literal file named `>>`, and `echo >>`
   prints literal `>>` to stdout.
2. `rm -f nonexistent` returns ERR:NOENT:-f ... instead of quiet empty string.
Keep-legs pin existing behavior (plain write truncates, bare rm refuses NOENT).
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

fails = 0

# Leg 1: write then append
sh.turn("write app.txt first")
r1 = sh.turn("cat app.txt")
sh.turn("write >> app.txt second")
r2 = sh.turn("cat app.txt")
# On pre-implementation tree, r2 will still be " first" because write >> wrote to file ">>"
if r2 == " first second":
    print("GREEN leg 1: append accumulated")
else:
    print(f"RED leg 1: expected ' first second', got {r2!r}")
    fails += 1

# Leg 2: echo >> file
sh.turn("echo third >> app.txt")
r3 = sh.turn("cat app.txt")
if r3 == " first second third":
    print("GREEN leg 2: echo >> accumulated")
else:
    print(f"RED leg 2: expected ' first second third', got {r3!r}")
    fails += 1

# Leg 3: rm -f quiet
rm_f = sh.turn("rm -f nonexistent_file_probe")
if rm_f == "":
    print("GREEN leg 3: rm -f quiet")
else:
    print(f"RED leg 3: expected '', got {rm_f!r}")
    fails += 1

# Keep-leg: bare rm nonexistent still refuses
rm_bare = sh.turn("rm nonexistent_file_probe")
if rm_bare == "ERR:NOENT:nonexistent_file_probe":
    print("ok keep-leg rm bare refuses")
else:
    print(f"FAIL keep-leg: expected ERR:NOENT:..., got {rm_bare!r}")
    fails += 1

print(f"RED_PROBE: {fails} failing legs")
sys.exit(0 if fails else 1)
