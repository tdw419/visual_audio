#!/usr/bin/env python3
"""Debug the sync() debugfs write path (item-25)."""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.glyph_vfs import GlyphVfs  # noqa: E402

tmp = tempfile.mkdtemp(prefix="dbg25_")
v = GlyphVfs.format(os.path.join(tmp, "d.png"))
v.vfs_write("hello.txt", b"hi from vfs")
v._ensure_staging()
print("disk_path:", v._disk_path)

r = subprocess.run(["debugfs", "-w", "-R", 'rm "/hello.txt"', v._disk_path],
                   capture_output=True)
print("rm rc", r.returncode, "|", r.stdout.decode()[:150], "|", r.stderr.decode()[:200])

r = subprocess.run(
    ["debugfs", "-w", "-R",
     'put "%s" "/hello.txt"' % os.path.join(v._staging, "hello.txt"),
     v._disk_path],
    capture_output=True)
print("put rc", r.returncode, "|", r.stdout.decode()[:200], "|", r.stderr.decode()[:300])

r = subprocess.run(["e2fsck", "-fn", v._disk_path], capture_output=True)
print("fsck rc", r.returncode)
print(r.stdout.decode()[:400])
