#!/usr/bin/env python3
"""
Manually trace what write_phys_word should do.
"""

import struct

# From the trace:
# s2 = 0x0000000000000001
# store_val = vec2<u32>(x=0x00000001, y=0x00000000)
# pa = 0x8000d1b0
# pa_base = PHYS_BASE = 0x80000000 (since pa.x >= PHYS_BASE)
# pa_offset = 0x8000d1b0 - 0x80000000 = 0xd1b0 = 53680
# word_addr = 53680 / 4 = 13420

val = 0x00000001
pa_x = 0x8000d1b0
PHYS_BASE = 0x80000000

pa_base = PHYS_BASE if pa_x >= PHYS_BASE else 0
pa_offset = pa_x - pa_base
word_addr = pa_offset // 4

print(f"val = 0x{val:08x}")
print(f"pa.x = 0x{pa_x:08x}")
print(f"pa_base = 0x{pa_base:08x}")
print(f"pa_offset = {pa_offset} (0x{pa_offset:04x})")
print(f"word_addr = {word_addr}")

# Simulate write_phys_word
px = struct.pack('4B', 0, 0, 0, 0)  # Start with zeros (RGBA)

# The WGSL code:
# px.r = new_word & 0xFFu;
# px.g = (new_word >> 8u) & 0xFFu;
# px.b = (new_word >> 16u) & 0xFFu;
# px.a = (new_word >> 24u) & 0xFFu;

r = val & 0xFF
g = (val >> 8) & 0xFF
b = (val >> 16) & 0xFF
a = (val >> 24) & 0xFF

print(f"\nAfter packing val=0x{val:08x} into RGBA:")
print(f"  r = 0x{r:02x}")
print(f"  g = 0x{g:02x}")
print(f"  b = 0x{b:02x}")
print(f"  a = 0x{a:02x}")

# This creates the pixel [r, g, b, a] = [0x01, 0x00, 0x00, 0x00]

# When we read back this pixel:
pixel_bytes = bytes([r, g, b, a])
print(f"\nPixel bytes (RGBA): {pixel_bytes.hex()}")

# And we read at byte_offset = 0 (address is word-aligned)
byte_offset = pa_x & 3
print(f"byte_offset = {byte_offset}")
print(f"Read byte at offset {byte_offset}: 0x{pixel_bytes[byte_offset]:02x}")