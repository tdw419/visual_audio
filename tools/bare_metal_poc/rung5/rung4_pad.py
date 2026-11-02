#!/usr/bin/env python3
"""RUNG4 pad tool: grow the assembled stage2.bin to RUNG4_SCALE bytes.

stage2.asm already carries the SAME patterned filler via %rep
(-DRUNG4_SCALE=<n> at assembly), so the assembled binary is normally
already exactly RUNG4_SCALE bytes and this tool is a byte-exact CHECK,
not a transformation: it verifies the length and re-emits the identical
bytes. It exists as the host-side authority for the filler bytes and to
make the filler a single point of definition in Python (rung4_pad.py's
PATTERN is what the %rep line in stage2.asm must equal; the gate's
non-vacuity leg asserts the two agree).
"""
import sys

SCALE = int(sys.argv[1])          # target payload size in bytes
SRC = sys.argv[2]                 # stage2.bin as assembled (with -DRUNG4_SCALE)
DST = sys.argv[3]                 # output (byte-identical copy when consistent)

PATTERN = bytes([0xA5, 0x5A, 0xC3, 0x3C, 0x0F, 0xF0, 0x33, 0xCC,
                 0x81, 0x7E, 0x18, 0xE7, 0x42, 0xBD, 0x69, 0x96])

code = open(SRC, "rb").read()
if len(code) > SCALE:
    raise SystemExit(f"FATAL: stage2.bin is {len(code)}B, exceeds SCALE={SCALE}B")
if SCALE % 16 or SCALE % 4:
    raise SystemExit(f"FATAL: RUNG4_SCALE={SCALE} not a multiple of 16")
pad = SCALE - len(code)
out = code + PATTERN * (pad // 16) + PATTERN[: pad % 16]
assert len(out) == SCALE
# the tail beyond the code must be pure PATTERN repetition
tail = out[len(code):]
if any(tail[i:i + 16] != PATTERN for i in range(0, len(tail) - 15, 16)):
    raise SystemExit("FATAL: filler generation is not the RUNG4 pattern")
open(DST, "wb").write(out)
print(f"stage2: code={len(code)}B + filler={pad}B = {len(out)}B ({len(out)//1024} KB)")
