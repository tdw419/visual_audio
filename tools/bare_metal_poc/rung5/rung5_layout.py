#!/usr/bin/env python3
"""RUNG5 build-time constants + layout disjointness gate.

Derived from the padded stage2.bin (rung-4 twin) plus the rung-5 medium
layout: emits the -D defines nasm needs for stage2.asm, and -- the load-
bearing part -- ASSERTS the sector disjointness of
  [0, 1)                       stage1
  [1, 1+PAYLOAD_SECTORS)       stage2 planes
  [IMG2_BASE_LBA, +IMG2_SECTORS)   second image
  [WR_LBA, +WR_SECTORS)        BM-502 write target
The brief's trap 10 (a self-bricking write is the classic second-boot
failure) is refused at build time here, and re-asserted by the gate
against the codec's meta JSON (independent derivation).
"""
import sys
import zlib

SCALE = int(sys.argv[1])            # stage2 payload scale in bytes
IMG2_LEN = 2048
WR_SECTORS = 4                      # 2048 bytes: same size as img2 marker

s2_len = SCALE
plane2 = s2_len // 4
payload_sectors = (s2_len + 511) // 512
stage2_last = payload_sectors       # last stage2 LBA (exclusive)

# second image: sector-aligned right above the stage2 planes
img2_base = stage2_last + 1
img2_sectors = IMG2_LEN // 512
img2_last = img2_base + img2_sectors

# write target: next sector boundary above the second image
wr_lba = img2_last
wr_last = wr_lba + WR_SECTORS

# ---- build-time disjointness gate: every pair of regions must not touch
regions = {
    "stage1": (0, 1),
    "stage2": (1, stage2_last),
    "img2": (img2_base, img2_last),
    "write": (wr_lba, wr_last),
}
names = sorted(regions)
for i, a in enumerate(names):
    for b in names[i + 1:]:
        (a0, a1), (b0, b1) = regions[a], regions[b]
        if a0 < b1 and b0 < a1:
            raise SystemExit(f"FATAL: region {a} {regions[a]} overlaps "
                             f"{b} {regions[b]} (write-target disjointness gate)")

consts = (f"PAYLOAD_SECTORS equ {payload_sectors}\n"
          f"IMG2_LEN        equ {IMG2_LEN}\n"
          f"IMG2_SECTORS    equ {img2_sectors}\n"
          f"IMG2_BASE_LBA   equ {img2_base}\n"
          f"IMG2_SEG        equ 0x5000\n"
          f"WR_LBA          equ {wr_lba}\n"
          f"WR_SECTORS      equ {WR_SECTORS}\n")
open("rung5_layout.inc", "w").write(consts)
print(f"scale={s2_len} stage2_lbas=[1,{stage2_last}) "
      f"img2_lbas=[{img2_base},{img2_last}) write_lbas=[{wr_lba},{wr_last}) "
      f"DISJOINT=OK")
