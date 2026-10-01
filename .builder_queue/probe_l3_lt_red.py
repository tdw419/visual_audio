#!/usr/bin/env python3
"""RED probe — L3 sub-step 3 (`<` input redirection).

Measured at HEAD 1107474b BEFORE implementation:
`wc < f.txt` / `grep pat < f.txt` / `head < f.txt` do NOT return ERR —
they raise FileNotFoundError out of turn(): the file-arg shims treat the
whole `< f.txt` string as a filename. Input redirection cannot exist yet.

Keep-legs pin landed behavior that must not drift:
- `wc f.txt` file-mode still returns the 4-column form (P8 keep).
- `cat f.txt | wc` pipe still splices (sub-step 2 contract).
- `echo hi > o.txt` truncate redirect still writes (sub-step 1 contract).
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
sh.turn("echo alpha beta > f.txt")

fails = 0

# Leg 1: `wc < f.txt` — stdin form, 3 columns, NO trailing filename
try:
    r1 = sh.turn("wc < f.txt")
    if r1 == "1 2 11":
        print("GREEN leg 1: wc < reads stdin (no filename column)")
    else:
        print(f"RED leg 1: wc<={r1!r} (want '1 2 11')")
        fails += 1
except Exception as exc:
    print(f"RED leg 1: raised {type(exc).__name__}: {exc}")
    fails += 1

# Leg 2: `grep pat < f.txt` — stdin form returns matching lines
try:
    r2 = sh.turn("grep alpha < f.txt")
    if r2 == " alpha beta":
        print("GREEN leg 2: grep < reads stdin")
    else:
        print(f"RED leg 2: grep<={r2!r} (want ' alpha beta')")
        fails += 1
except Exception as exc:
    print(f"RED leg 2: raised {type(exc).__name__}: {exc}")
    fails += 1

# Leg 3: `head < f.txt` — stdin form returns first line
try:
    r3 = sh.turn("head < f.txt")
    if r3 == " alpha beta":
        print("GREEN leg 3: head < reads stdin")
    else:
        print(f"RED leg 3: head<={r3!r} (want ' alpha beta')")
        fails += 1
except Exception as exc:
    print(f"RED leg 3: raised {type(exc).__name__}: {exc}")
    fails += 1

# Leg 4: empty source refuses with ERR text, no exception
try:
    r4 = sh.turn("wc <")
    if r4.startswith("ERR:"):
        print("GREEN leg 4: empty source refused")
    else:
        print(f"RED leg 4: wc<= {r4!r} (want ERR:...)")
        fails += 1
except Exception as exc:
    print(f"RED leg 4: raised {type(exc).__name__}: {exc}")
    fails += 1

# Leg 5: missing source refuses ERR:NOENT (host-side, before any GPU turn)
try:
    r5 = sh.turn("wc < missing.txt")
    if r5.startswith("ERR:NOENT"):
        print("GREEN leg 5: missing source refused ERR:NOENT")
    else:
        print(f"RED leg 5: got {r5!r} (want ERR:NOENT:...)")
        fails += 1
except Exception as exc:
    print(f"RED leg 5: raised {type(exc).__name__}: {exc}")
    fails += 1

# Leg 6: escape containment — `<` cannot read outside the session root
try:
    r6 = sh.turn("wc < ../f.txt")
    if r6.startswith("ERR:"):
        print("GREEN leg 6: escape refused")
    else:
        print(f"RED leg 6: got {r6!r} (want ERR:...)")
        fails += 1
except Exception as exc:
    print(f"RED leg 6: raised {type(exc).__name__}: {exc}")
    fails += 1

# Keep-legs: landed contracts must hold both sides
keep = 0
if sh.turn("wc f.txt") == "1 2 11 f.txt":
    keep += 1
else:
    print("FAIL keep-leg: file-mode wc drifted")
    fails += 1
if sh.turn("cat f.txt | wc") == "1 2 11":
    keep += 1
else:
    print("FAIL keep-leg: pipe splice drifted")
    fails += 1
if sh.turn("echo hi > o.txt") == "" and sh.turn("cat o.txt") == " hi":
    keep += 1
else:
    print("FAIL keep-leg: > truncate redirect drifted")
    fails += 1
print(f"keep-legs green: {keep}/3")

print(f"RED_PROBE: {fails} failing legs")
sys.exit(1 if fails else 0)
