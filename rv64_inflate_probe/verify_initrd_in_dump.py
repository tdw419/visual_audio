#!/usr/bin/env python3
"""
Minimal test: check if initrd matches source in fullboot_dump.bin.
This is the definitive test of what the GPU core actually has at boot time.
"""

from pathlib import Path

# Paths
dump_path = Path('/home/jericho/projects/zion/projects/visual_audio/rv64_inflate_probe/fullboot_dump.bin')
source_path = Path('/home/jericho/projects/zion/projects/visual_audio/rv64_inflate_probe/initrd.gz.bin')

dump = dump_path.read_bytes()
source = source_path.read_bytes()

INITRD_OFFSET = 0x2800000  # physical 0x82800000 - RAM_BASE 0x80000000

# Extract initrd region from dump
region = dump[INITRD_OFFSET:INITRD_OFFSET + len(source)]

print(f"Dump size: {len(dump):,} bytes (64MB)")
print(f"Source initrd size: {len(source):,} bytes")
print(f"Initrd region from dump size: {len(region):,} bytes")
print(f"Initrd physical address: 0x{INITRD_OFFSET + 0x80000000:x}")

# Compare
if source == region:
    print("\n✓ INITRD MATCHES SOURCE!")
    print("  The bytes in GPU memory at boot time are CORRECT.")
    print("  The bug must be in the kernel's MMU/TLB translation.")
    exit(0)
else:
    print("\n✗ INITRD DOES NOT MATCH SOURCE!")
    diffs = sum(1 for i in range(len(source)) if source[i] != region[i])
    pct = 100.0 * diffs / len(source)
    print(f"  Differing bytes: {diffs:,} / {len(source):,} ({pct:.2f}%)")

    # Show first bytes
    print(f"\nSource first 16 bytes:  {' '.join(f'{b:02x}' for b in source[:16])}")
    print(f"Dump   first 16 bytes:  {' '.join(f'{b:02x}' for b in region[:16])}")

    # Count 0xcc bytes
    cc_count = sum(1 for b in region if b == 0xcc)
    print(f"\n0xcc bytes in dump region: {cc_count:,} ({100.0*cc_count/len(region):.1f}%)")

    if cc_count > len(region) * 0.5:
        print("\n=> INITRD IS FULL OF 0xcc FILL PATTERN")
        print("   This means write_mem_bytes() FAILED to write the initrd correctly!")
        print("   Check the chunked write path (>64KB) for bugs.")
        exit(1)
    else:
        print("\n=> PARTIAL CORRUPTION (not simple fill)")
        print("   Something else overwrote the initrd during boot.")
        exit(1)