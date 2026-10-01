#!/usr/bin/env python3
"""Standalone smoke for tools/glyph_vfs.py (item-25) — run BEFORE engine wiring."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.glyph_vfs import GlyphVfs  # noqa: E402

tmp = tempfile.mkdtemp(prefix="smoke25_")
png = os.path.join(tmp, "disk.png")
v = GlyphVfs.format(png)
print("format OK, png size:", os.path.getsize(png))

rc = v.vfs_write("hello.txt", b"hi from vfs")
print("write rc:", rc, "dirty:", v.dirty())

data = v.vfs_read("hello.txt", 64)
print("staged read:", data)

rc = v.sync()
print("sync rc:", rc, "dirty now:", v.dirty())

# Reboot leg: a FRESH instance from the same PNG must see synced content.
v2 = GlyphVfs(png)
data2 = v2.vfs_read("hello.txt", 64)
print("fresh-boot read:", data2)
print("fresh-boot list:", v2.vfs_list("/", 256))

# Containment / refusal contract.
print("escape (expect -1):", v2.vfs_write("../evil.txt", b"x"))
print("list missing dir (expect None):", v2.vfs_list("nope", 64))

# Read-through: image-side file visible to a fresh instance pre-sync.
v3 = GlyphVfs(png)
print("image-side read (expect b'hi from vfs'):", v3.vfs_read("hello.txt", 64))

# Sync no-op when clean.
print("clean sync rc (expect 0):", v3.sync())
print("SMOKE DONE")
