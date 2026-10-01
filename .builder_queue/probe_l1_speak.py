#!/usr/bin/env python3
"""Landing-diagnosis probe: letter-form speak on the landed build."""
import sys, tempfile
from pathlib import Path
sys.path[:0] = [".", "tools", "experiments"]
from glyph_interactive_shell import build_dispatch_shell, repl

d = Path(tempfile.mkdtemp())
img = build_dispatch_shell(str(d / "w.dat"), str(d / "a.wav"))
out = repl(lines=["s hi there"], image=img, fs_pix_enabled=True)
print("landed speak:", out, "audio exists:", (d / "a.wav").exists())
