#!/usr/bin/env python3
"""RUNG5 consts: emit the nasm defines for stage2.asm at a given scale.

Reads rung5_layout.inc (from rung5_layout.py) + the second image
(argv[2], default img2.bin), whose CRC the guest must reproduce, and
prints a single -D flag string. Keep IMG2_LEN in sync with
rung5_codec.py.

BM651 addition: EXPECTED_EXEC_NID, a 16-bit fold of the SAME CRC the
CRC gate checks, handed to the image and required back. One source of
truth for both defines, so a variant image and a mismatching NID
expectation cannot be paired by accident.
"""
import sys
import zlib

layout = dict()
for line in open("rung5_layout.inc"):
    name, _, val = line.partition(" equ ")
    layout[name.strip()] = int(val, 0)

IMG2 = sys.argv[2] if len(sys.argv) > 2 else "img2.bin"
img2 = open(IMG2, "rb").read()
assert len(img2) == layout["IMG2_LEN"], "img2.bin length != layout IMG2_LEN"

crc = zlib.crc32(img2) & 0xFFFFFFFF
nid = ((crc & 0xFFFF) ^ (crc >> 16)) & 0xFFFF
flags = (f"-DRUNG4_SCALE={int(sys.argv[1])} "
         f"-DPAYLOAD_SECTORS={layout['PAYLOAD_SECTORS']} "
         f"-DIMG2_LEN={layout['IMG2_LEN']} "
         f"-DIMG2_SECTORS={layout['IMG2_SECTORS']} "
         f"-DIMG2_BASE_LBA={layout['IMG2_BASE_LBA']} "
         f"-DIMG2_SEG={layout['IMG2_SEG']} "
         f"-DWR_LBA={layout['WR_LBA']} "
         f"-DWR_SECTORS={layout['WR_SECTORS']} "
         f"-DEXPECTED_IMG2_CRC=0x{crc:08X} "
         f"-DEXPECTED_EXEC_NID=0x{nid:04X} "
         f"-DDST_SEG=0x1000")
print(flags)
