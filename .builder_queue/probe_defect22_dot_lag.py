#!/usr/bin/env python3
"""DEFECT-22 instrument check (builder cron af3e62239ce2, 2026-09-13).

Question: can a crash position be read off pytest's `-q` dot stream when stdout
is redirected to a file? DEFECT-22's ticket carried a "~44 % + 23 dots" position
inference that contradicts run 2's faulthandler traceback by 127 items, which
only makes sense if the captured dots LAG the real completions (block-buffered
stdout is lost when the process dies by signal).

Method: generate 200 trivial tests OUT OF TREE (/tmp), have test #150 kill the
process with SIGSEGV, run pytest exactly like the arc run (same interpreter,
`-q`, stdout+stderr to a file), then count the progress chars that actually
reached the file. If captured < 149, the dot stream is a lagging lower bound and
position inference from it is unsound.
"""
import os
import subprocess
import sys
from pathlib import Path

PROBE = Path("/tmp/defect22_probe")
PROBE.mkdir(parents=True, exist_ok=True)
N = 200
KILL_AT = 150

lines = [
    "import os, signal",
    "",
]
for i in range(1, N + 1):
    if i == KILL_AT:
        lines += [
            f"def test_{i:03d}_kills_here():",
            "    os.kill(os.getpid(), signal.SIGSEGV)",
            "",
        ]
    else:
        lines += [f"def test_{i:03d}_ok():", "    assert True", ""]
(PROBE / "test_dots.py").write_text("\n".join(lines))

out = PROBE / "out.txt"
with out.open("wb") as fh:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "test_dots.py", "-q"],
        cwd=PROBE, stdout=fh, stderr=subprocess.STDOUT,
    )

txt = out.read_text()
head = txt.split("Fatal Python error")[0]
dots = head.count(".")
print(f"probe: {N} tests, SIGSEGV raised inside test #{KILL_AT}")
print(f"pytest rc={proc.returncode} (139 = SIGSEGV)")
print(f"progress chars flushed to the file before the crash: {dots} dots")
print(f"=> captured {dots} of the {KILL_AT - 1} completions that actually preceded the crash")
if dots < KILL_AT - 1:
    print("=> VERDICT: the dot stream LAGS; position inference from it under-counts")
else:
    print("=> VERDICT: the dot stream is current; the earlier disagreement needs another cause")
print("file bytes:", len(txt))
