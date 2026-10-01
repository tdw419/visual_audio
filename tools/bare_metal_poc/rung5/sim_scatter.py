#!/usr/bin/env python3
"""Simulate stage1's bank-outer scatter in Python over the rung-5 medium.

Same arithmetic as rung5/stage1.asm lines 86-153 (DST_SEG=0x1000,
CHUNK_SECTORS=8). Panics if the de-interleaved image != stage2.bin.
Run AFTER encoding; prints DEINTERLEAVE-SIM-OK on success.
"""
import sys

import numpy as np

MEDIUM = sys.argv[1] if len(sys.argv) > 1 else "rung5_medium.raw"
PAYLOAD_LEN = int(sys.argv[2]) if len(sys.argv) > 2 else 65536
CHUNK_SECTORS = 8
PLANE_LEN = PAYLOAD_LEN // 4
BANKS = PAYLOAD_LEN // 65536
CHUNKS_PER_BANK = 16384 // (CHUNK_SECTORS * 512)

med = np.fromfile(MEDIUM, dtype=np.uint8, count=512 + 4 * PLANE_LEN)
dst = bytearray(PAYLOAD_LEN)

for b in range(BANKS):
    for p in range(4):
        lba = 1 + p * (PLANE_LEN // 512) + 32 * b
        j_local = 0
        for c in range(CHUNKS_PER_BANK):
            # read chunk: medium bytes for sectors [lba, lba+CHUNK_SECTORS)
            off = lba * 512
            chunk = med[off: off + CHUNK_SECTORS * 512]
            for k in range(CHUNK_SECTORS * 512):
                # stage1.asm's DI is set once per (bank, plane) and steps 4
                # per byte across the bank's chunks: j_local spans the whole
                # bank (0..16383); medium byte = 512 + p*PLANE + 16384*b +
                # j_local, which stays inside plane p's region.
                jg = 16384 * b + j_local
                if jg >= 16384 * (b + 1):
                    continue  # overrun would leave this bank (cannot happen:
                              # j_local counts exactly 16384 per bank)
                i = p + 4 * jg               # payload index
                dst[i] = chunk[k]
                j_local += 1
            lba += CHUNK_SECTORS

s2 = open("stage2.bin", "rb").read()
if bytes(dst) != s2:
    for i, (a, b2) in enumerate(zip(dst, s2)):
        if a != b2:
            raise SystemExit(f"DEINTERLEAVE-SIM-FAIL first diff at payload "
                             f"byte {i}: got {a:02x} want {b2:02x}")
    raise SystemExit("DEINTERLEAVE-SIM-FAIL length mismatch")
print("DEINTERLEAVE-SIM-OK: stage1's chunk loop reproduces stage2.bin "
      f"exactly at PAYLOAD_LEN={PAYLOAD_LEN}")
