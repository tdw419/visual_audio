#!/usr/bin/env python3
"""
Test if large chunked writes (>64KB) work correctly on the GPU core.
This mimics what happens when writing the initrd (5.2MB).
"""

import sys
sys.path.insert(0, '../tools')

import numpy as np
from pathlib import Path

from spatial_rv64i_cpu import SpatialRV64ICPU

# Create core with 64MB RAM (same as Alpine boot)
RAM_SIZE = 64 * 1024 * 1024
core = SpatialRV64ICPU(ram_size=RAM_SIZE)

# Create test data: 256KB of known pattern
test_size = 256 * 1024
test_data = bytes([(i & 0xFF) for i in range(test_size)])

print(f"Test data size: {len(test_data):,} bytes")
print(f"Test takes chunked path? {len(test_data) // 4 >= 16384}")

# Write at initrd offset (0x2000000)
INITRD_OFFSET = 0x2000000
core.write_mem_bytes(INITRD_OFFSET, test_data)

# Read back linear shadow for comparison
shadow_region = core._linear_shadow[INITRD_OFFSET // 4 : (INITRD_OFFSET // 4) + len(test_data) // 4]
readback = shadow_region.tobytes()

# Compare
if test_data == readback:
    print("✓ Write and readback MATCH!")
else:
    print("✗ Write and readback MISMATCH!")
    diffs = sum(1 for i in range(min(len(test_data), len(readback))) if test_data[i] != readback[i])
    print(f"  Diffs: {diffs:,} / {len(test_data):,}")

    # Check first 64 bytes
    print(f"\nFirst 64 bytes written:   {' '.join(f'{b:02x}' for b in test_data[:64])}")
    print(f"First 64 bytes read back: {' '.join(f'{b:02x}' for b in readback[:64])}")

    # Check alignment of first diff
    for i in range(min(len(test_data), len(readback))):
        if test_data[i] != readback[i]:
            print(f"\nFirst diff at offset 0x{i:x}: wrote 0x{test_data[i]:02x}, read 0x{readback[i]:02x}")
            break

    sys.exit(1)

# Test the ACTUAL initrd write path
print("\n" + "="*60)
print("Testing ACTUAL initrd write (5.2MB)")
print("="*60)

initrd = Path('/home/jericho/projects/zion/projects/visual_audio/rv64_inflate_probe/initrd.gz.bin').read_bytes()
print(f"Initrd size: {len(initrd):,} bytes")

core2 = SpatialRV64ICPU(ram_size=RAM_SIZE)
core2.write_mem_bytes(INITRD_OFFSET, initrd)

# Read back
shadow_region2 = core2._linear_shadow[INITRD_OFFSET // 4 : (INITRD_OFFSET // 4) + (len(initrd) + 3) // 4]
readback2 = shadow_region2.tobytes()[:len(initrd)]

if initrd == readback2:
    print("✓ Initrd write and readback MATCH!")
else:
    print("✗ Initrd write and readback MISMATCH!")
    diffs = sum(1 for i in range(min(len(initrd), len(readback2))) if initrd[i] != readback2[i])
    print(f"  Diffs: {diffs:,} / {len(initrd):,}")

    # Check first 16 bytes
    print(f"\nFirst 16 bytes written:   {' '.join(f'{b:02x}' for b in initrd[:16])}")
    print(f"First 16 bytes read back: {' '.join(f'{b:02x}' for b in readback2[:16])}")

    sys.exit(1)

print("\n✓ All tests passed!")