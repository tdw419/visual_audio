#!/usr/bin/env python3
"""Debug _image_list parse (item-25)."""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.glyph_vfs import GlyphVfs  # noqa: E402

tmp = tempfile.mkdtemp()
v = GlyphVfs.format(os.path.join(tmp, "d.png"))
v.vfs_write("hello.txt", b"hi from vfs")
v._ensure_staging()
r = subprocess.run(["debugfs", "-R", 'ls -l "/"', v._disk_path],
                   capture_output=True)
out = r.stdout.decode(errors="replace")
print("RAW LINES:")
for line in out.splitlines():
    parts = line.split()
    print(len(parts), repr(line[:80]))
    if parts:
        print("  last part:", repr(parts[-1]))
