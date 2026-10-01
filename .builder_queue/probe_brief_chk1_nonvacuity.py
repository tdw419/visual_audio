#!/usr/bin/env python3
"""BRIEF-CHK-1 — non-vacuity: the new self-test legs must be able to go RED.

Takes a COPY of the fixed tools/check_brief.py, neuters exactly the new predicate
(`_scope_section` -> always True, i.e. the over-widened matcher L6 exists to catch),
runs its --self-test, and asserts the gate goes RED on L6 while the rest stays green.
The repo file is never touched; the copy lives in output/ so the L7 fixture path
(`Path(__file__).parents[1]/tests/...`) still resolves to the repo root.
"""
from __future__ import annotations

import subprocess
from hashlib import md5
from pathlib import Path

REPO = Path("/home/jericho/projects/zion/projects/visual_audio")
SRC = REPO / "tools/check_brief.py"
NEUTERED = REPO / "output/check_brief_NEUTERED_scope_always_true.py"

src = SRC.read_text()
before = md5(SRC.read_bytes()).hexdigest()

inject = (
    "\n# --- PROBE INJECTION (output/check_brief_NEUTERED_scope_always_true.py only) ---\n"
    "_scope_section = lambda text: True  # over-widened matcher: accepts the exclusions-only brief\n"
    "\n\ndef main("
)
assert src.count("\n\ndef main(") == 1, "anchor for the injection is not unique"
NEUTERED.write_text(src.replace("\n\ndef main(", inject, 1))

print(f"repo file md5 before probe : {before}")
proc = subprocess.run(["/usr/bin/python3", str(NEUTERED), "--self-test"],
                      cwd=REPO, capture_output=True, text=True)
print("--- neutered --self-test ---")
print(proc.stdout.strip())
print(f"rc={proc.returncode}")

after = md5(SRC.read_bytes()).hexdigest()
print(f"repo file md5 after probe  : {after}")

red = proc.returncode != 0
l6_fail = "L6 non-vacuity: exclusions-only brief missing scope rejection" in proc.stdout
l5_ok = "L5 recall: scope heading brief accepted" in proc.stdout
clean = before == after

for name, ok in [
    ("the injected widening makes the gate go RED (rc != 0)", red),
    ("the RED leg is L6 (the leg exists to catch exactly this)", l6_fail),
    ("L5 still passes under the injection (only the guard leg fires)", l5_ok),
    ("repo file untouched by the probe (md5 identical)", clean),
]:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
print(f"PROBE {'PASS' if all([red, l6_fail, l5_ok, clean]) else 'FAIL'}")
