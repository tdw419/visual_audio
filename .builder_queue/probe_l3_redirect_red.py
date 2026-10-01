#!/usr/bin/env python3
"""RED probe — L3 sub-step 1 (`>` truncate redirection on `echo`).

Measures the tree BEFORE implementation (expected at HEAD a47043dd):
1. `echo hi > out.txt` is not routed as redirection: the echo verb only
   knows `>>`, so the single `>` falls through to the glyph echo body and
   prints the literal " hi > out" while NO file is created.
2. Truncation semantics therefore cannot exist (second redirect keeps
   appending or never writes).
Keep-legs pin existing behavior (plain echo still echoes; `>>` append
still accumulates — L2 sub-step 4's landed contract must not drift).
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

# Leg 1: echo hi > out.txt creates the file, returns "", content " hi"
r1 = sh.turn("echo hi > out.txt")
c1 = sh.turn("cat out.txt")
if r1 == "" and c1 == " hi":
    print("GREEN leg 1: echo > redirect wrote ' hi'")
else:
    print(f"RED leg 1: turn={r1!r} cat={c1!r} (want turn='' cat=' hi')")
    fails += 1

# Leg 2: `>` TRUNCATES (vs `>>` which appends)
sh.turn("echo keepme > trunc.txt")
sh.turn("echo gone > trunc.txt")
c2 = sh.turn("cat trunc.txt")
if c2 == " gone":
    print("GREEN leg 2: > truncates")
else:
    print(f"RED leg 2: cat={c2!r} (want ' gone')")
    fails += 1

# Leg 3: empty dest refuses with ERR text, no file named '>' junk
r3 = sh.turn("echo oops >")
if r3.startswith("ERR:"):
    print("GREEN leg 3: empty dest refused")
else:
    print(f"RED leg 3: turn={r3!r} (want ERR:...)")
    fails += 1

# Leg 4: escape containment — `>` cannot reach outside the session root
parent = Path(sh.session.root).parent
r4 = sh.turn("echo pwned > ../escape_probe_l3")
if r4.startswith("ERR:") and not (parent / "escape_probe_l3").exists():
    print("GREEN leg 4: escape refused")
else:
    print(f"RED leg 4: turn={r4!r} escaped={(parent / 'escape_probe_l3').exists()}")
    fails += 1

# Keep-legs: landed contracts must hold both sides
keep = 0
if sh.turn("echo plain") == " plain":
    keep += 1
else:
    print("FAIL keep-leg: plain echo drifted")
    fails += 1
sh.turn("echo one >> app.txt")
sh.turn("echo two >> app.txt")
if sh.turn("cat app.txt") == " one two":
    keep += 1
else:
    print("FAIL keep-leg: >> append drifted")
    fails += 1
print(f"keep-legs green: {keep}/2")

print(f"RED_PROBE: {fails} failing legs")
sys.exit(1 if fails else 0)
