"""Expected on-medium marker after a rung-5 boot (BM-502 host verify).

The marker is stage2's own decoded payload [0,2048), but two words in it
are RUNTIME-UPDATED before the write: img2crcline (the computed img2
CRC32) and img2sumline (the word-walk sum). The gate compares the medium
against stage2.bin with those values patched in, at addresses taken from
the nasm listing (no hardcoded offsets).

Usage: python3 expected_marker.py <stage2.bin> <stage2.lst> <img2.bin>
Prints the expected 2048 bytes as lowercase hex.
"""
import re
import struct
import sys

payload_path, lst_path, img2_path = sys.argv[1:4]
payload = bytearray(open(payload_path, 'rb').read()[:2048])
img2 = open(img2_path, 'rb').read()

lst = open(lst_path, 'r', errors='replace').read()
addr = {}
for name in ('img2crcline', 'img2sumline'):
    m = re.search(r'^\s*\d+\s+([0-9A-Fa-f]{8})\s+\S+\s+%s\b' % name, lst, re.M)
    if not m:
        raise SystemExit(f"{name} address not found in {lst_path}")
    addr[name] = int(m.group(1), 16)

crc = zlib_crc = __import__('zlib').crc32(img2) & 0xFFFFFFFF
wsum = 0
bl = bh = 0
for i in range(0, len(img2), 2):
    bl += img2[i]
    bh = (bh + (bl >> 8)) & 0xFF
    bl &= 0xFF
    bl += img2[i + 1]
    bh = (bh + (bl >> 8)) & 0xFF
    bl &= 0xFF
wsum = (bh << 8) | bl

payload[addr['img2crcline']:addr['img2crcline'] + 4] = struct.pack('<I', crc)
payload[addr['img2sumline']:addr['img2sumline'] + 2] = struct.pack('<H', wsum)
print(payload.hex())
