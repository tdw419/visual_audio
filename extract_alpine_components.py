#!/usr/bin/env python3
"""
Extract kernel and initrd from Alpine's combined .lnx.bin image.
This is the same format our emulator loader uses (LNX header).
"""

import sys
import struct
from pathlib import Path

ALPINE_KERNEL = '/home/jericho/projects/zion/apps/linux/alpine/alpine-riscv64.lnx.bin'

alpine_path = Path(ALPINE_KERNEL)
if not alpine_path.exists():
    print(f"ERROR: Alpine kernel not found at {ALPINE_KERNEL}")
    sys.exit(1)

alpine_data = alpine_path.read_bytes()

# Parse LNX header (same as our emulator loader)
kernel_offset = struct.unpack('<I', alpine_data[4:8])[0]
kernel_size = struct.unpack('<I', alpine_data[8:12])[0]
initrd_size = struct.unpack('<I', alpine_data[12:16])[0]

print(f"LNX header:")
print(f"  Kernel offset: 0x{kernel_offset:x} ({kernel_offset:,} bytes)")
print(f"  Kernel size: 0x{kernel_size:x} ({kernel_size:,} bytes)")
print(f"  Initrd size: 0x{initrd_size:x} ({initrd_size:,} bytes)")

# Extract raw kernel and initrd
kernel_pe = alpine_data[kernel_offset:kernel_offset + kernel_size]
initrd_data = alpine_data[kernel_offset + kernel_size:kernel_offset + kernel_size + initrd_size]

print(f"\nExtracted:")
print(f"  Kernel (PE32+): {len(kernel_pe):,} bytes")
print(f"  Initrd: {len(initrd_data):,} bytes")

# Write to /tmp for QEMU
kernel_out = '/tmp/alpine_vmlinuz_extracted'
initrd_out = '/tmp/alpine_initrd_extracted'

Path(kernel_out).write_bytes(kernel_pe)
Path(initrd_out).write_bytes(initrd_data)

print(f"\nWritten to:")
print(f"  {kernel_out}")
print(f"  {initrd_out}")

# Check kernel format
import subprocess
result = subprocess.run(['file', kernel_out], capture_output=True, text=True)
print(f"\nKernel format: {result.stdout.strip()}")