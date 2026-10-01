#!/usr/bin/env python3
"""BM903 step 3, L6 fixture: corrupt ONE byte of the pixel medium and predict,
on the host, the exact CRC the guest gate is going to compute.

The point is the cross-check: the refusal line the guest prints
(`GATE2 CRC=<computed> EXP=<expected>`) must carry a computed value that this
script derived independently from the corrupted file, using the medium's own
plane layout -- not a value someone typed into the gate script.

  usage: bm903_px_corrupt.py [src] [dst] [payload-byte-index]
"""
import re
import sys
import zlib
from pathlib import Path

RUNG9 = Path('/home/jericho/projects/zion/projects/visual_audio/tools/bare_metal_poc/rung9')
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else RUNG9 / 'bm903_medium_px.raw'
DST = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('/tmp/bm903_medium_px_corrupt.raw')
IDX = int(sys.argv[3]) if len(sys.argv) > 3 else 4_000_000   # inside the pm kernel

inc = (RUNG9 / 'bm903_px_layout.inc').read_text()
d = {m.group(1): int(m.group(2), 0)
     for m in re.finditer(r'^%define (\w+) (-?0x[0-9A-Fa-f]+|\d+)$', inc, re.M)}
base, plane_sectors = d['PX_BASE_LBA'], d['PX_PLANE_SECTORS']
plane_bytes = plane_sectors * 512
payload_len = d['PX_PAYLOAD_BYTES']
expected = d['EXPECTED_CRC']

med = bytearray(SRC.read_bytes())
assert len(med) == (base + 4 * plane_sectors) * 512, 'medium size != layout'
assert IDX < payload_len, 'chosen byte is outside the payload'

# PXC1: payload byte i lives at medium byte base*512 + (i%4)*plane + i//4.
plane, in_plane = IDX % 4, IDX // 4
off = base * 512 + plane * plane_bytes + in_plane
sub = ('header band' if IDX < d['SUB0_NGROUPS'] * d['PX_GROUP_BYTES'] else
       'pm kernel' if IDX < (d['SUB0_NGROUPS'] + d['SUB1_NGROUPS']) * d['PX_GROUP_BYTES']
       else 'initrd')
before = med[off]
med[off] ^= 0x01
DST.write_bytes(bytes(med))
assert med[off] != before


def decode(medium: bytes) -> bytes:
    """PXC1 decode, in the direction the guest walks."""
    out = bytearray(payload_len)
    for p in range(4):
        start = base * 512 + p * plane_bytes
        out[p::4] = medium[start:start + plane_bytes]
    return bytes(out)


# Validate THIS host decode against the baked constant before trusting it to
# predict anything: the clean medium must decode to the clean CRC.
clean = zlib.crc32(decode(SRC.read_bytes())) & 0xFFFFFFFF
assert clean == expected, \
    f'host decode gives {clean:08X}, the gate expects {expected:08X} — the ' \
    f'cross-check would be meaningless'
predicted = zlib.crc32(decode(bytes(med))) & 0xFFFFFFFF

print(f'corrupt: payload byte {IDX} (inside the {sub}) at medium offset {off:#x}, '
      f'{before:#04x} -> {med[off]:#04x}  (1 byte of {len(med)} changed)')
print(f'host decode cross-check: clean medium -> {clean:08X} == EXPECTED; '
      f'corrupt medium -> {predicted:08X}')
assert predicted != expected, 'a corruption the gate cannot see -- fixture is void'
DST.with_suffix('.crc').write_text(f'{predicted:08X} {expected:08X} {IDX} {off:#x}\n')
print(f'wrote {DST} ({len(med)} B) and {DST.with_suffix(".crc")}')
