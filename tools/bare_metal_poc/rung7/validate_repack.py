#!/usr/bin/env python3
"""Rung-7 diagnostic: validate the in-ISO core.gz repack (DIAGNOSIS item 3 suspect).

Checks: iso sha256, core.gz stream found+decompresses to a cpio with TRAILER,
inittab content printed, ttyS0 getty presence reported. Read-only on the ISO.
"""
import hashlib
import zlib

iso = open('TinyCore-current.iso', 'rb').read()
print('iso sha256:', hashlib.sha256(iso).hexdigest())

i = 0
out = None
while True:
    i = iso.find(b'\x1f\x8b', i)
    if i == -1:
        break
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        out = d.decompress(iso[i:i + 40_000_000])
    except Exception:
        i += 2
        continue
    if out[:6] == b'070701':
        print('core.gz at', i, 'decompressed', len(out))
        break
    i += 2

assert out is not None, 'core.gz stream not found'
off = 0
trailer = False
while off < len(out):
    if out[off:off + 6] != b'070701':
        print('cpio parse stopped at', off, out[off:off+16])
        break
    ns = int(out[off + 94:off + 102], 16)
    fs = int(out[off + 54:off + 62], 16)
    name = out[off + 110:off + 110 + ns - 1].decode()
    hdrend = (off + 110 + ns + 3) & ~3
    if name == 'etc/inittab':
        print('--- inittab ---')
        print(out[hdrend:hdrend + fs].decode())
    off = (hdrend + fs + 3) & ~3
    if name == 'TRAILER!!!':
        trailer = True
        break
print('cpio TRAILER reached:', trailer)
