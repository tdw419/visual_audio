#!/usr/bin/env python3
"""L3 sub-step 2 (`|` pipe) — RED probe, run BEFORE any implementation.

L3-PROCESS supply gate legs exercised here (pipe sub-step only):
  - 'cat f | wc' byte-exact vs host truth (3-line fixture)
  - backpressure: producer output > window (DISPATCH_BUF_CAP=64) splices
    across multiple consumer turns and TERMINATES (bounded), with all
    bytes accounted (non-vacuity: first-chunk-only splice fails).

Expected at HEAD 49183d48 (pre-implementation): every pipe leg FAILS —
'cat f | wc' hits the cat grammar guard (' ' in rest -> ERR:UNKNOWN_CMD),
so pipes cannot exist. Probe exit 1 = RED confirmed; exit 0 post-fix.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools"), str(REPO / "experiments")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from experiments.glyph_l1_shell import GlyphL1Shell  # noqa: E402

fails = []
keeps = []


def check(name, got, want):
    if got != want:
        fails.append(f"{name}: got={got!r} want={want!r}")
    else:
        keeps.append(name)


def turn(sh_, line):
    """turn() wrapper: an UNCAUGHT host exception on a pipe line is itself
    a RED datum (the pipe grammar does not exist) — record and continue."""
    try:
        return sh_.turn(line)
    except Exception as exc:  # noqa: BLE001
        fails.append(f"{line!r}: raised {type(exc).__name__}: {exc}")
        return "<<EXCEPTION>>"


# fixture: 3-line file, < window
sh = GlyphL1Shell()
content = "alpha beta\nsecond line here\nthird\n"
(Path(sh.session.root) / "f.txt").write_text(content)

# P1: cat f | wc byte-exact vs host truth
lines, words, chars = len(content.splitlines()), len(content.split()), len(content)
check("P1 cat|wc", turn(sh, "cat f.txt | wc"),
      f"{lines} {words} {chars}")

# P2: echo producer
s = " hello"
check("P2 echo|wc", turn(sh, "echo hello | wc"),
      f"{len(s.splitlines())} {len(s.split())} {len(s)}")

# P3: backpressure — 3x window (192B) producer via grep (host shim,
# unbounded read), spliced across >=3 consumer turns, must terminate
big = "z" * 192
(Path(sh.session.root) / "big.txt").write_text(big)
check("P3 3x-window splice", turn(sh, "grep z big.txt | wc"), "1 1 192")

# P4: non-vacuity — all bytes accounted (first-chunk-only splice = 64)
out = turn(sh, "grep z big.txt | wc")
if out.split()[-1:] != ["192"]:
    fails.append(f"P4 non-vacuity: chars leg got={out!r} (first-chunk-only splice reports 64)")
else:
    keeps.append("P4 non-vacuity")

# P5: producer ERR propagates, consumer never runs
out5 = turn(sh, "cat missing.txt | wc")
check("P5 err-propagation", isinstance(out5, str) and out5.startswith("ERR:"), True)

# P6: empty segments refused by grammar
out6a = turn(sh, "| wc")
check("P6a empty-left", isinstance(out6a, str) and out6a.startswith("ERR:"), True)
out6b = turn(sh, "cat f.txt |")
check("P6b empty-right", isinstance(out6b, str) and out6b.startswith("ERR:"), True)

# keep-legs (must stay green pre AND post)
sh2 = GlyphL1Shell()
(Path(sh2.session.root) / "k.txt").write_text("keep\n")
check("K1 plain cat", sh2.turn("cat k.txt").rstrip("\n"), "keep")
check("K2 plain wc file-mode", sh2.turn("wc k.txt"), "1 1 5 k.txt")
check("K3 redirect still lands", sh2.turn("echo hi > o.txt"), "")
check("K4 cat redirected", sh2.turn("cat o.txt"), " hi")

print(f"RED_PROBE: {len(fails)} failing legs, keep-legs green {len(keeps)}/{len(keeps) + 0}")
for f in fails:
    print("  FAIL", f)
for k in keeps:
    print("  keep", k)
sys.exit(1 if fails else 0)
