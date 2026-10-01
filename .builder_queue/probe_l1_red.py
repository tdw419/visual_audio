#!/usr/bin/env python3
"""L1-PERSONALITY (SUPPLY_ROUND8.json, item 14) — RED probe, run BEFORE any
implementation lands.

Today's shell (build_dispatch_shell) dispatches on the FIRST BYTE only:
'e','s','w','r' + bare 'r'. The L1 contract adds word verbs. This probe
drives the LANDED shell with the L1 command surface and records which legs
are RED on today's tree. The gate (tests/test_l1_shell_personality.py) must
show the same legs RED at landing time, then GREEN after the L1 shell
personality lands.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools"), str(REPO / "experiments")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from glyph_interactive_shell import (  # noqa: E402
    DISPATCH_ERROR_MARKER,
    build_dispatch_shell,
    repl,
)

ERR = DISPATCH_ERROR_MARKER.decode("ascii")

d = Path(tempfile.mkdtemp(prefix="l1_red_"))
write_path = str(d / "w.dat")
audio_path = str(d / "a.wav")
image = build_dispatch_shell(write_path, audio_path)

results: list[tuple[str, str]] = []


def leg(name: str, lines: list[str]):
    out = repl(lines=lines, image=image, fs_pix_enabled=True)
    results.append((name, " | ".join(repr(o) for o in out)))


# --- the L1 word verbs (all must be ERR:UNKNOWN_CMD today) ------------------
leg("L1.word.echo     ['echo hello']", ["echo hello"])
leg("L1.word.speak    ['speak hi']", ["speak hi"])
leg("L1.word.write    ['write payload']", ["write payload"])
leg("L1.word.read     ['read']", ["read"])
leg("L1.word.ls       ['ls']", ["ls"])
leg("L1.word.cat      ['cat f.txt']", ["cat f.txt"])
leg("L1.word.wc       ['wc f.txt']", ["wc f.txt"])
leg("L1.word.time     ['time']", ["time"])
leg("L1.word.date     ['date']", ["date"])
leg("L1.word.pwd      ['pwd']", ["pwd"])
leg("L1.word.env      ['env']", ["env"])
leg("L1.word.which    ['which echo']", ["which echo"])
leg("L1.word.cp       ['cp a.txt b.txt']", ["cp a.txt b.txt"])
leg("L1.word.mv       ['mv a.txt b.txt']", ["mv a.txt b.txt"])
leg("L1.word.rm       ['rm a.txt']", ["rm a.txt"])
leg("L1.word.head     ['head f.txt']", ["head f.txt"])
leg("L1.word.tail     ['tail f.txt']", ["tail f.txt"])
leg("L1.word.grep     ['grep needle f.txt']", ["grep needle f.txt"])
leg("L1.word.cd       ['cd sub']", ["cd sub"])

# --- grammar invariants that must SURVIVE L1 --------------------------------
leg("KEEP.single_letter_echo  ['e hello']", ["e hello"])
leg("KEEP.unknown_z           ['z bogus']", ["z bogus"])
leg("KEEP.grammar.what_time   ['what time is it']", ["what time is it"])

print()
print("=== L1 RED probe (today's tree) ===")
green = red = 0
for name, out in results:
    if name.startswith("L1."):
        is_red = (out == repr(ERR)) or (out == f"'{ERR}'")
        status = "RED(todos ERR)" if out == repr(ERR) or ERR in out else f"?? {out}"
        if ERR in out:
            red += 1
            status = "RED (ERR:UNKNOWN_CMD — L1 gap)"
        else:
            green += 1
    else:
        status = "keep-leg"
    print(f"  {name:38s} -> {out}   {status}")
print(f"\nword-verb legs hitting ERR today: {red}/19 (all 19 must be ERR on the")
print("pre-landing tree — that IS the RED leg; the gate re-proves it post-landing)")
