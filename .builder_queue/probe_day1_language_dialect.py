#!/usr/bin/env python3
"""Research probe: is the .glyph dialect documented well enough to write a
program from the docs alone (day-1 friction clause 'the compiler assumes
you already speak its language')?

Measures:
1. engine opcode table (glyph_isa_v2.py OPCODES) vs GLYPH_ISA_SPEC_v1.0.md
   section 3.2/3.3 coverage — per-opcode presence in the spec;
2. FIXED_COLORS (pinned engine palette) vs spec 3.3 palette table
   (presence + exact RGB agreement);
3. live error-quality probes through tools/glyph_run.py (real exits).
"""
import re
import sys

REPO = "/home/jericho/projects/zion/projects/visual_audio"
src = open(f"{REPO}/tools/glyph_isa_v2.py").read()
spec = open(f"{REPO}/docs/spec/GLYPH_ISA_SPEC_v1.0.md").read()

# 1. engine opcode set
m = re.search(r"OPCODES = \{(.*?)\n    \}", src, re.S)
ops = sorted(set(re.findall(r"'([A-Z_0-9]+)':", m.group(1))))
missing_in_spec = [o for o in ops if o not in spec]
print(f"engine opcode count: {len(ops)}")
print(f"engine opcodes absent from spec entirely: {missing_in_spec}")

# 2. pinned colors vs spec palette
m2 = re.search(r"FIXED_COLORS: Dict\[str, Tuple\[int, int, int\]\] = \{(.*?)\n    \}", src, re.S)
pinned = dict(
    (op, (int(r), int(g), int(b)))
    for op, r, g, b in re.findall(r"'([A-Z_0-9]+)':\s*\((\d+),\s*(\d+),\s*(\d+)\)", m2.group(1))
)
mismatch = []
for op, rgb in sorted(pinned.items()):
    mm = re.search(r"\|\s*" + op + r"\s*\|\s*(\d+),\s*(\d+),\s*(\d+)", spec)
    if not mm:
        mismatch.append((op, rgb, "ABSENT-FROM-SPEC-PALETTE"))
    elif (int(mm.group(1)), int(mm.group(2)), int(mm.group(3))) != rgb:
        mismatch.append((op, rgb, tuple(int(x) for x in mm.groups())))
print(f"engine FIXED_COLORS count: {len(pinned)}")
print(f"palette mismatches/absent: {mismatch}")

# spec's own claim
claim = re.search(r"all (\d+) opcodes", spec)
print(f"spec claims opcode count: {claim.group(1) if claim else 'n/a'}")

# 3. live error probes through glyph_run.py
import subprocess, tempfile, os
probes = {
    "x86-style mov": ":__entry\n    mov r5 5\n    HALT\n",
    "unknown op FOO": ":__entry\n    FOO r5 5\n",
    "wrong operand count": ":__entry\n    ADD r5\n",
    "nonexistent label": ":__entry\n    JMP :nowhere\n",
}
for name, text in probes.items():
    with tempfile.NamedTemporaryFile("w", suffix=".glyph", delete=False) as f:
        f.write(text)
        path = f.name
    r = subprocess.run(
        [f"{REPO}/.venv/bin/python", f"{REPO}/tools/glyph_run.py", path],
        capture_output=True, text=True, timeout=60)
    print(f"probe [{name}]: exit={r.returncode} stderr={r.stderr.strip()[:120]!r}")
    os.unlink(path)
