#!/usr/bin/env python3
"""Rung-7 serial-console patch: add a ttyS0 getty to TinyCore's initramfs.

1. Locate /boot/core.gz inside the ISO (gzip cpio stream at gz_start).
2. Decompress, parse the cpio, REPLACE the etc/inittab member with a copy
   that adds, after the tty1 respawn line:
       ttyS0::respawn:/sbin/getty -nl /sbin/autologin 115200 ttyS0
3. Re-gzip at level 9, splice back into the ISO at the same offset, and
   zero-pad to the original stream's 2048-rounded extent so the ISO length
   and every byte offset after the extent are unchanged. The ISO directory
   record (file size) is NOT touched — kernel initramfs loaders tolerate
   zero padding after the gzip member, and the file's extents are identical.
4. Assert: iso length unchanged; the new gzip stream fits the extent;
   round-trip: decompress the spliced ISO and confirm the ttyS0 line.
"""
import gzip
import hashlib
import zlib


def gzip_compress9(data):
    return gzip.compress(data, compresslevel=9)

iso_p = 'TinyCore-current.iso'
iso = bytearray(open(iso_p, 'rb').read())
orig_len = len(iso)
orig_sha = hashlib.sha256(iso).hexdigest()

# --- locate core.gz ---
gz_start = None
cpio = None
i = 0
while True:
    i = iso.find(b'\x1f\x8b', i)
    if i == -1:
        break
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        out = d.decompress(bytes(iso[i:i + 40_000_000]))
    except Exception:
        i += 2
        continue
    if out[:6] == b'070701':
        gz_start = i
        cpio = out
        break
    i += 2
assert gz_start is not None, 'core.gz not found'

# exact consumed gzip length (stream end = where unused data begins)
dobj = zlib.decompressobj(16 + zlib.MAX_WBITS)
pos = gz_start
while not dobj.eof:
    chunk = bytes(iso[pos:pos + (1 << 20)])
    if not chunk:
        break
    dobj.decompress(chunk)
    pos += len(chunk)
gz_len = pos - gz_start
extent_end = ((gz_start + gz_len + 2047) // 2048) * 2048
region_len = extent_end - gz_start  # total bytes we may rewrite

GETTY = b'ttyS0::respawn:/sbin/getty -nl /sbin/autologin 115200 ttyS0\n'


def parse_cpio(data):
    off = 0
    members = []
    while off < len(data):
        if data[off:off + 6] != b'070701':
            break
        namesize = int(data[off + 94:off + 102], 16)
        filesize = int(data[off + 54:off + 62], 16)
        name = data[off + 110:off + 110 + namesize - 1].decode()
        hdrend = (off + 110 + namesize + 3) & ~3
        fdata = bytes(data[hdrend:hdrend + filesize])
        members.append((name, bytes(data[off:off + 110]), fdata))
        off = (hdrend + filesize + 3) & ~3
        if name == 'TRAILER!!!':
            break
    return members


def build_member(name, hdr, body):
    newhdr = hdr[:54] + b'%08X' % len(body) + hdr[62:]
    assert len(newhdr) == 110
    blob = newhdr + name.encode() + b'\x00'
    blob += b'\x00' * ((-len(blob)) % 4)
    blob += body
    blob += b'\x00' * ((-len(body)) % 4)
    return blob


members = parse_cpio(cpio)
names = [n for n, _, _ in members]
assert 'etc/inittab' in names, 'etc/inittab not in initramfs'

out_cpio = bytearray()
for name, hdr, body in members:
    if name == 'etc/inittab':
        tab = body.decode()
        anchor = 'tty1::respawn:/sbin/getty -nl /sbin/autologin 38400 tty1\n'
        assert anchor in tab, 'tty1 anchor line not found'
        assert b'ttyS0' not in body, 'ttyS0 getty already present'
        new_tab = tab.replace(anchor, anchor + GETTY.decode())
        out_cpio += build_member(name, hdr, new_tab.encode())
    else:
        out_cpio += build_member(name, hdr, body)

new_gz = gzip_compress9(bytes(out_cpio))
print(f'orig gz stream={gz_len} B; extent={region_len} B; '
      f'new gz={len(new_gz)} B')
assert len(new_gz) <= region_len, \
    f'rebuilt initramfs exceeds extent: {len(new_gz)} > {region_len}'

region = new_gz + b'\x00' * (region_len - len(new_gz))
iso[gz_start:gz_start + region_len] = region
assert len(iso) == orig_len, 'iso length changed!'

# --- round-trip: decompress the spliced iso, confirm the line ---
d = zlib.decompressobj(16 + zlib.MAX_WBITS)
rt = d.decompress(bytes(iso[gz_start:gz_start + region_len]))
assert GETTY in rt, 'round-trip: ttyS0 getty line not in rebuilt initramfs'

new_sha = hashlib.sha256(iso).hexdigest()
open(iso_p, 'wb').write(iso)
print('iso length unchanged:', len(iso) == orig_len)
print('new iso sha256:', new_sha)
print('orig iso sha256:', orig_sha)
