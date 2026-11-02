#!/usr/bin/env python3
"""RUNG5 consts: emit the nasm defines for stage2.asm at a given scale.

Reads rung5_layout.inc (from rung5_layout.py) + img2.bin (the second
image, whose CRC the guest must reproduce) and prints a single
-D flag string. Keep IMG2_LEN in sync with rung5_codec.py.
"""
import sys
import zlib

layout = dict()
for line in open("rung5_layout.inc"):
    name, _, val = line.partition(" equ ")
    layout[name.strip()] = int(val, 0)

img2 = open("img2.bin", "rb").read()
assert len(img2) == layout["IMG2_LEN"], "img2.bin length != layout IMG2_LEN"

flags = (f"-DRUNG4_SCALE={int(sys.argv[1])} "
         f"-DPAYLOAD_SECTORS={layout['PAYLOAD_SECTORS']} "
         f"-DIMG2_LEN={layout['IMG2_LEN']} "
         f"-DIMG2_SECTORS={layout['IMG2_SECTORS']} "
         f"-DIMG2_BASE_LBA={layout['IMG2_BASE_LBA']} "
         f"-DIMG2_SEG={layout['IMG2_SEG']} "
         f"-DWR_LBA={layout['WR_LBA']} "
         f"-DWR_SECTORS={layout['WR_SECTORS']} "
         f"-DEXPECTED_IMG2_CRC=0x{zlib.crc32(img2) & 0xFFFFFFFF:08X} "
         f"-DDST_SEG=0x1000")
print(flags)
