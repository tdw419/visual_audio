#!/usr/bin/env python3
"""Rung-7 repack v2: serial-capable ISO WITHOUT corrupting vmlinuz64.

Root cause of the 16:13+ dead legs (measured 2026-09-18): patch_serial_console.py
computed the rewrite region with a decompress loop that over-consumed the gzip
member (eof checked after advancing pos), yielding region_len = 9437184 instead
of the true member+pad end at 9248768. The re-compressed stream (9260807 B,
bigger because inittab grew and TinyCore's original stream is not zlib level 9)
spilled 128775 bytes over vmlinuz64's extent at byte 9248768, so isolinux loaded
a corrupt kernel and every subsequent medium-carried leg died pre-output.

v2 approach (tc2.iso = initramfs-patched, layout intact):
  1. Take tc2.iso as base (it already carries the ttyS0 getty; the gzip member
     is the ORIGINAL 9131528 B, ending 9248264, pad to 9248768 — clean).
  2. Patch isolinux.cfg ON MEDIA: add `SERIAL 0 115200` as the first line and
     ensure APPEND carries console=ttyS0. TinyCore's own cfg already has
     `APPEND ... console=ttyS0` (measured). isolinux.cfg is 1445 B at its own
     extent — rewrite IN PLACE only (no length change): reuse the pad inside
     its 2048-B extent for the added line? cfg is a file of exact size; kernel
     reads it as bytes to EOF, so growing it needs extent+size updates.
     -> simpler: rebuild cfg content to <= 1445+pad and patch dir size.
  3. Assert: no extent overlap; vmlinuz head still MZ; core.gz member intact.

Writes TinyCore-current.iso (the medium source), preserving length unless step 2
needs none (it doesn't — extent has room).

NOTE (gate boundary): this in-place cfg patch does NOT relocate vmlinuz; the
initramfs stream stays byte-identical to tc2's, so no repack of core.gz happens
at all. The corrupt 0a3494de iso is superseded by this one.
"""
import hashlib
import os
import struct
import zlib

SRC = '/tmp/tc_iso_check/tc2.iso'
DST = 'TinyCore-current.iso'
# The base this probe was measured against, recorded in RECEIPT_TC_PROBE.md's
# artifact table: /tmp holds no ownership, so a stale or substituted tc2.iso
# would otherwise be repacked into a medium that looks like a pass.
SRC_SHA256 = '445dbb53de29b7e60660b713582bd9490370c933c2f8d2a39326ca05074de12d'
SRC_BYTES = 18874368

if not os.path.exists(SRC):
    raise SystemExit(f'missing base {SRC} — this script does not fetch it')
iso = bytearray(open(SRC, 'rb').read())
orig_sha = hashlib.sha256(iso).hexdigest()
if len(iso) != SRC_BYTES or orig_sha != SRC_SHA256:
    raise SystemExit(f'{SRC} is not the pinned base: {len(iso)} B / {orig_sha}')
print('base iso:', SRC, 'sha256', orig_sha)

# --- locate isolinux.cfg via /isolinux dir (lba 31) ---
D = 31 * 2048
off = 0
cfg = None
while off < 2048:
    ln = iso[D + off]
    if ln == 0:
        break
    rec = iso[D + off:D + off + ln]
    name = bytes(rec[33:33 + rec[32]])
    ext = struct.unpack('<I', rec[2:6])[0]
    size = struct.unpack('<I', rec[10:14])[0]
    if name == b'ISOLINUX.CFG;1':
        cfg = (ext, size)
    off += ln
assert cfg, 'ISOLINUX.CFG not found'
ext, size = cfg
print('isolinux.cfg ext', ext, 'size', size)

cfg_data = bytes(iso[ext * 2048:ext * 2048 + size])
assert cfg_data.count(b'\n') and b'APPEND' in cfg_data

# --- build new cfg: SERIAL first, console=ttyS0 on APPEND lines ---
new_cfg = bytearray()
for line in cfg_data.split(b'\n'):
    if line.startswith(b'APPEND') and b'console=ttyS0' not in line:
        line = line.rstrip() + b' console=ttyS0,115200'
    new_cfg += line + b'\n'
# SERIAL must precede any MENU/kernel directives; prepend at very top.
new_cfg = b'SERIAL 0 115200\n' + bytes(new_cfg)
assert len(new_cfg) <= 2048, f'cfg too big for one extent: {len(new_cfg)}'
assert len(new_cfg) >= size  # we only grow
new_cfg += b'\n' * (2048 - len(new_cfg))  # pad inside extent (unchanged extent)

iso[ext * 2048:ext * 2048 + 2048] = new_cfg
# dir record size update (offset +10, 4B LE) — the cfg record lives in the dir
size_off = None
off = 0
while off < 2048:
    ln = iso[D + off]
    if ln == 0:
        break
    rec = iso[D + off:D + off + ln]
    if bytes(rec[33:33 + rec[32]]) == b'ISOLINUX.CFG;1':
        size_off = D + off + 10
        break
    off += ln
assert size_off is not None
iso[size_off:size_off + 4] = struct.pack('<I', len(new_cfg.rstrip(b'\n')))
# keep record consistent: we set size to the un-padded content length

# --- invariants ---
assert len(iso) == len(open(SRC, 'rb').read()), 'iso length changed'
vml = bytes(iso[9248768:9248770])
assert vml == b'MZ', f'vmlinuz head corrupted: {vml!r}'
d = zlib.decompressobj(16 + zlib.MAX_WBITS)
out = d.decompress(bytes(iso[116736:116736 + 9131528]))
assert out[:6] == b'070701' and d.eof, 'core.gz member broken'
assert b'ttyS0::respawn' in out, 'ttyS0 getty missing from initramfs'
# cfg round-trip
assert iso[ext * 2048:ext * 2048 + 16].startswith(b'SERIAL 0 115200')

open(DST, 'wb').write(bytes(iso))
print('wrote', DST, hashlib.sha256(bytes(iso)).hexdigest(), 'len', len(iso))
