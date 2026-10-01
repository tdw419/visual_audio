#!/usr/bin/env python3
"""Throwaway probe: inspect the first 40 canvas bytes of a wrapped disk."""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")
from PIL import Image
from tools.png_vfs import wrap

tmp = Path(tempfile.mkdtemp())
disk = tmp / "d.ext2"
with open(disk, "wb") as f:
    f.truncate(24574 * 512)
subprocess.run(
    ["mke2fs", "-q", "-F", "-t", "ext2", "-b", "1024", "-m", "0", "-N", "128",
     "-I", "128", str(disk)],
    check=True, capture_output=True,
)
png = wrap(disk.read_bytes(), tmp / "d.png")
img = Image.open(png).convert("RGB")
print("size", img.size)
px = img.load()
buf = bytearray()
for b in range(40):
    pix = b // 3
    x, y = pix % 8, pix // 8
    r, g, bl = px[x, y]
    buf += bytes((r, g, bl)[b % 3])
print(bytes(buf))
