#!/usr/bin/env python3
"""Extract /etc/inittab from core.gz inside the ISO (read-only inspection).

core.gz is located by decompressing every gzip stream and checking for the
cpio magic; TinyCore's initramfs is a gzipped cpio archive.
"""
import zlib

iso = open('TinyCore-current.iso', 'rb').read()
data = None
i = 0
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
        print(f'core.gz at iso offset {i}, cpio {len(out)} bytes')
        data = out
        break
    i += 2

assert data is not None, 'core.gz not found'

off = 0
while off < len(data):
    if data[off:off + 6] != b'070701':
        break
    namesize = int(data[off + 94:off + 102], 16)
    filesize = int(data[off + 54:off + 62], 16)
    name = data[off + 110:off + 110 + namesize - 1].decode()
    hdrend = (off + 110 + namesize + 3) & ~3
    if name == 'etc/inittab':
        print('=== etc/inittab ===')
        print(data[hdrend:hdrend + filesize].decode())
    off = (hdrend + filesize + 3) & ~3
    if name == 'TRAILER!!!':
        break
