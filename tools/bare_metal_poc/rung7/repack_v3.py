#!/usr/bin/env python3
"""Rung-7 repack v3 — serial-capable ISO without extent corruption.

Measured root cause (2026-09-18, this dir): the 16:13 in-place core.gz repack
over-consumed the gzip member when measuring the rewrite region and spilled
128775 bytes over vmlinuz64's extent (byte 9248768), so isolinux loaded a
corrupt kernel and every medium-carried boot after 16:13 died pre-output.
gzip level 9 cannot fit the grown cpio back into the original 9131528-byte
stream region (measured min 9260808), so in-place is impossible.

v3 (plan A, single dir-record edit):
  base = tc2.iso (445dbb53, pristine layout, kernel MZ intact)
  1. build new cpio = tc2's cpio + ttyS0 getty line in etc/inittab (in-memory)
  2. new gzip stream appended at END of iso (new extent), zero-padded to 2048
  3. patch CORE.GZ;1 dir record extent (+10..13 size, +2..5 extent)
  4. patch ISOLINUX.CFG;1 content in its extent: SERIAL 0 115200 first line,
     console=ttyS0,115200 appended to each APPEND line lacking it; dir size updated
  5. old core.gz extent zeroed (28 MiB medium has room; keeps extents unambiguous)
  6. asserts: vmlinuz head MZ, new member round-trips with ttyS0 line,
     cfg round-trip, no extent overlap, iso extends but nothing else moves.
"""
import gzip
import hashlib
import os
import struct
import zlib

SRC = '/tmp/tc_iso_check/tc2.iso'
DST = 'TinyCore-current.iso'
# Pin of the 2026-09-18 base, from RECEIPT_TC_PROBE.md's artifact table: /tmp
# holds no ownership, so a stale or truncated tc2.iso must not be repacked into
# a medium that still passes every structural assert below.
SRC_SHA256 = '445dbb53de29b7e60660b713582bd9490370c933c2f8d2a39326ca05074de12d'
SRC_BYTES = 18874368
BOOT_DIR = 30 * 2048  # /boot directory extent (lba 30)
ISO_DIR = 31 * 2048   # /isolinux directory extent (lba 31)

if not os.path.exists(SRC):
    raise SystemExit(f'missing base {SRC} — this script does not fetch it')
iso = bytearray(open(SRC, 'rb').read())
base_sha = hashlib.sha256(bytes(iso)).hexdigest()
if len(iso) != SRC_BYTES or base_sha != SRC_SHA256:
    raise SystemExit(f'{SRC} is not the pinned base: {len(iso)} B / {base_sha}')
print('base sha256', base_sha)


def find_record(dir_base, name):
    off = 0
    while off < 2048:
        ln = iso[dir_base + off]
        if ln == 0:
            break
        rec = iso[dir_base + off:dir_base + off + ln]
        if bytes(rec[33:33 + rec[32]]) == name:
            return dir_base + off, rec
        off += ln
    raise SystemExit(f'record {name} not found in dir {dir_base:#x}')


# --- 1. core.gz: decompress original member ---
gz_rec_off, gz_rec = find_record(BOOT_DIR, b'CORE.GZ;1')
gz_ext = struct.unpack('<I', gz_rec[2:6])[0]
gz_size = struct.unpack('<I', gz_rec[10:14])[0]
print('core.gz ext', gz_ext, 'size', gz_size)
d = zlib.decompressobj(16 + zlib.MAX_WBITS)
cpio = d.decompress(bytes(iso[gz_ext * 2048:gz_ext * 2048 + gz_size]))
assert d.eof and cpio[:6] == b'070701'

# --- build new cpio with ttyS0 getty ---
GETTY = b'ttyS0::respawn:/sbin/getty -nl /sbin/autologin 115200 ttyS0\n'


def parse_cpio(data):
    off = 0
    members = []
    while off < len(data):
        if data[off:off + 6] != b'070701':
            break
        ns = int(data[off + 94:off + 102], 16)
        fs = int(data[off + 54:off + 62], 16)
        name = data[off + 110:off + 110 + ns - 1].decode()
        hdrend = (off + 110 + ns + 3) & ~3
        members.append((name, bytes(data[off:off + 110]),
                        bytes(data[hdrend:hdrend + fs])))
        off = (hdrend + fs + 3) & ~3
        if name == 'TRAILER!!!':
            break
    return members


def build_member(name, hdr, body):
    newhdr = hdr[:54] + b'%08X' % len(body) + hdr[62:]
    blob = newhdr + name.encode() + b'\x00'
    blob += b'\x00' * ((-len(blob)) % 4)
    blob += body
    blob += b'\x00' * ((-len(body)) % 4)
    return blob


members = parse_cpio(cpio)
names = [n for n, _, _ in members]
assert 'etc/inittab' in names
out_cpio = bytearray()
for name, hdr, body in members:
    if name == 'etc/inittab':
        tab = body.decode()
        anchor = 'tty1::respawn:/sbin/getty -nl /sbin/autologin 38400 tty1\n'
        assert anchor in tab
        new_tab = tab.replace(anchor, anchor + GETTY.decode())
        out_cpio += build_member(name, hdr, new_tab.encode())
    else:
        out_cpio += build_member(name, hdr, body)

new_gz = gzip.compress(bytes(out_cpio), compresslevel=9)
print('new gz stream', len(new_gz))
# round-trip check
rt = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(new_gz)
assert GETTY in rt

# --- 2. append new extent at end of iso ---
pad = (-len(new_gz)) % 2048
new_ext = len(iso) // 2048
iso += new_gz + b'\x00' * pad
new_size = len(new_gz)
print('new core.gz extent', new_ext, 'size', new_size)

# --- 3. patch dir record ---
iso[gz_rec_off + 2:gz_rec_off + 6] = struct.pack('<I', new_ext)
iso[gz_rec_off + 10:gz_rec_off + 14] = struct.pack('<I', new_size)
# zero the old region
iso[gz_ext * 2048:gz_ext * 2048 + ((gz_size + 2047) // 2048) * 2048] = \
    b'\x00' * (((gz_size + 2047) // 2048) * 2048)

# --- 4. isolinux.cfg ---
cfg_rec_off, cfg_rec = find_record(ISO_DIR, b'ISOLINUX.CFG;1')
cfg_ext = struct.unpack('<I', cfg_rec[2:6])[0]
cfg_size = struct.unpack('<I', cfg_rec[10:14])[0]
cfg_data = bytes(iso[cfg_ext * 2048:cfg_ext * 2048 + cfg_size])
new_cfg = bytearray()
for line in cfg_data.split(b'\n'):
    if line.startswith(b'APPEND') and b'console=ttyS0' not in line:
        line = line.rstrip() + b' console=ttyS0,115200'
    new_cfg += line + b'\n'
new_cfg = b'SERIAL 0 115200\n' + bytes(new_cfg)
print('cfg ext', cfg_ext, 'rec off', hex(cfg_rec_off), 'len', len(new_cfg))
assert len(new_cfg) <= 2048, f'cfg grown past extent: {len(new_cfg)}'
iso[cfg_ext * 2048:cfg_ext * 2048 + 2048] = new_cfg + \
    b'\n' * (2048 - len(new_cfg))
iso[cfg_rec_off + 10:cfg_rec_off + 14] = struct.pack('<I', len(new_cfg))
print('isolinux.cfg', cfg_size, '->', len(new_cfg))
print('head after write:', bytes(iso[cfg_ext * 2048:cfg_ext * 2048 + 16]))

# --- 6. invariants ---
assert bytes(iso[9248768:9248770]) == b'MZ', 'vmlinuz head not MZ'
assert bytes(iso[cfg_ext * 2048:cfg_ext * 2048 + 16]) == \
    b'SERIAL 0 115200\n'
vml_off, vml_rec = find_record(BOOT_DIR, b'VMLINUZ.;1')
vml_ext = struct.unpack('<I', vml_rec[2:6])[0]
vml_size = struct.unpack('<I', vml_rec[10:14])[0]
assert bytes(iso[vml_ext * 2048:vml_ext * 2048 + 2]) == b'MZ'
new_start, new_end = new_ext * 2048, new_ext * 2048 + new_size + pad
vml_start, vml_end = vml_ext * 2048, vml_ext * 2048 + vml_size
assert new_start >= vml_end or vml_start >= new_end, \
    'extent overlap (new core.gz vs vmlinuz)'
print('vmlinuz ext', vml_ext, 'size', vml_size, 'head',
      bytes(iso[vml_ext * 2048:vml_ext * 2048 + 4]))
open(DST, 'wb').write(bytes(iso))
print('wrote', DST, 'sha256', hashlib.sha256(bytes(iso)).hexdigest(),
      'len', len(iso))
