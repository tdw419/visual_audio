#!/usr/bin/env python3
"""RED probe — L3 sub-step 4 (`&&`/`;` sequencing and `$?` exit status).

Measured pre-implementation:
- `echo a && echo b` does not sequence — treated as literal echo payload or ERR.
- `cat missing && echo no` does not short-circuit — `&& echo no` is treated as a filename.
- `echo a; echo b` does not sequence.
- `$?` is not expanded to exit status.

Keep-legs pin landed contracts:
- `wc < f.txt` input redirect still works (sub-step 3).
- `cat f | wc` pipe still splices (sub-step 2).
- `echo hi > o.txt` truncate redirect still writes (sub-step 1).
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
sh.turn("echo alpha > f.txt")

fails = 0

# Leg 1: `echo first && echo second` sequences both and returns outputs
try:
    r1 = sh.turn("echo first && echo second")
    if r1.strip() == "first\n second" or r1.strip() == "first\nsecond":
        print(f"GREEN leg 1: && sequences: {r1!r}")
    else:
        print(f"RED leg 1: && did not sequence: {r1!r}")
        fails += 1
except Exception as exc:
    print(f"RED leg 1: raised {type(exc).__name__}: {exc}")
    fails += 1

# Leg 2: `cat missing && echo no` short-circuits on failure (cat missing returns ERR:NOENT)
try:
    r2 = sh.turn("cat missing_file.txt && echo no")
    if r2.startswith("ERR:NOENT") and "no" not in r2:
        print(f"GREEN leg 2: && short-circuits on failure: {r2!r}")
    else:
        print(f"RED leg 2: && failed to short-circuit: {r2!r}")
        fails += 1
except Exception as exc:
    print(f"RED leg 2: raised {type(exc).__name__}: {exc}")
    fails += 1

# Leg 3: `;` executes sequentially regardless of prior success
try:
    r3 = sh.turn("echo one; echo two")
    if r3.strip() == "one\n two" or r3.strip() == "one\ntwo":
        print(f"GREEN leg 3: ; sequences: {r3!r}")
    else:
        print(f"RED leg 3: ; failed to sequence: {r3!r}")
        fails += 1
except Exception as exc:
    print(f"RED leg 3: raised {type(exc).__name__}: {exc}")
    fails += 1

# Leg 4: `$?` reflects exit status of preceding command
try:
    sh.turn("echo test")
    r4_zero = sh.turn("echo $?")
    sh.turn("cat missing_file.txt")
    r4_nonzero = sh.turn("echo $?")
    if "0" in r4_zero and "1" in r4_nonzero:
        print(f"GREEN leg 4: $? reflects exit status (0 vs 1)")
    else:
        print(f"RED leg 4: $? did not reflect status (got {r4_zero!r} then {r4_nonzero!r})")
        fails += 1
except Exception as exc:
    print(f"RED leg 4: raised {type(exc).__name__}: {exc}")
    fails += 1

# Keep-legs: landed L3 sub-steps 1, 2, 3 must remain green
k_fails = 0
if sh.turn("cat f.txt | grep alpha") != " alpha":
    print("KEEP FAIL: pipe | broken")
    k_fails += 1
if sh.turn("wc < f.txt") != "1 1 6":
    print("KEEP FAIL: input redirect < broken")
    k_fails += 1
if sh.turn("echo new > f.txt") != "" or sh.turn("cat f.txt") != " new":
    print("KEEP FAIL: output redirect > broken")
    k_fails += 1

print(f"\nVerdict: {fails} failing legs, {k_fails} keep failures")
sys.exit(1 if fails > 0 or k_fails > 0 else 0)
