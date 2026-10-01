#!/usr/bin/env python3
"""L1 pre-landing measurement: long-payload echo behavior (ring-cap probe)."""
import sys, tempfile
from pathlib import Path
sys.path[:0] = [".", "tools", "experiments"]
from glyph_interactive_shell import build_dispatch_shell, repl, INPUT_DATA_CAP

print("INPUT_DATA_CAP =", INPUT_DATA_CAP)
d = Path(tempfile.mkdtemp())
image = build_dispatch_shell(str(d / "w.dat"), str(d / "a.wav"))
line = "e " + "x" * 200
out = repl(lines=[line], image=image, fs_pix_enabled=True)
got = out[0] if out else ""
print("sent len:", len(line), "echoed len:", len(got))
print("echo exact:", got == line)
