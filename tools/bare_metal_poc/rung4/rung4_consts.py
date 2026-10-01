#!/usr/bin/env python3
"""Generate stage1_const.inc from the padded stage2.bin (build-time twin
pattern carried over from rung 2). CHUNK must equal CHUNK_SECTORS in
run_gate4.sh.

Scaled builds: PAYLOAD_KB carries the payload scale into stage1.asm's
32-bit loop counts (crc32_calc + r4_sum). PAYLOAD_KB == 64 is special:
the guest encodes that count as CX=0 (65536), so 64 KB stage1.asm
emits `xor ecx,ecx`; scales above 64 emit the explicit 32-bit count
`mov ecx, 1024*(PAYLOAD_KB/64)`. The %ifdef selection lives in
stage1.asm; this tool just emits PAYLOAD_KB and asserts the scale is a
power-of-2 multiple of 64 KB so the count math is exact.
"""
import zlib

s2 = open("stage2.bin", "rb").read()
plane = len(s2) // 4
CHUNK = 8   # keep in sync with CHUNK_SECTORS in run_gate4.sh
assert plane % (CHUNK * 512) == 0, f"plane {plane} not a multiple of chunk {CHUNK*512}"
kb = len(s2) // 1024
assert len(s2) == kb * 1024, "payload must be a whole number of KB"
assert kb >= 64 and (kb % 64) == 0, (
    f"PAYLOAD_KB={kb}: scale must be a multiple of 64 KB "
    "(stage1.asm's cx=0 encoding covers exactly 64 KB)")
consts = (f"PLANE_LEN       equ {plane}\n"
          f"PAYLOAD_LEN     equ {len(s2)}\n"
          f"PAYLOAD_KB      equ {kb}\n"
          f"PAYLOAD_BANKS   equ {kb // 64}\n"
          f"PAYLOAD_SECTORS equ {(len(s2) + 511) // 512}\n"
          f"CHUNK_SECTORS   equ {CHUNK}\n"
          f"CHUNKS_PER_PLANE equ {plane // (CHUNK * 512)}\n"
          f"CHUNKS_PER_BANK equ {16384 // (CHUNK * 512)}\n"
          f"EXPECTED_CRC    equ 0x{zlib.crc32(s2) & 0xFFFFFFFF:08X}\n"
          f"EXPECTED_SUM    equ 0x{sum(s2) % 65536:04X}\n")
open("stage1_const.inc", "w").write(consts)
print(f"stage2={len(s2)}B plane={plane}B sectors={(len(s2)+511)//512} "
      f"chunks/plane={plane // (CHUNK*512)} KB={kb} "
      f"CRC={zlib.crc32(s2) & 0xFFFFFFFF:08X} SUM={sum(s2)%65536:04X}")
