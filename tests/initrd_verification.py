#!/usr/bin/env python3
"""
Minimal initrd write/readback verification test - no boot required.
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))

from spatial_rv64i_cpu import SpatialRV64ICore
import struct
import re
import gzip

# Read the Alpine boot image
with open('/home/jericho/projects/zion/projects/visual_audio/boot_images/alpine_riscv64.lnx.bin', 'rb') as f:
    alpine_data = f.read()

print("Reading Alpine boot image...")
print(f"Total file size: {len(alpine_data):,} bytes ({len(alpine_data)/1024/1024:.2f} MB)")

# Parse LNX header
kernel_size = struct.unpack('<I', alpine_data[8:12])[0]
initrd_size = struct.unpack('<I', alpine_data[12:16])[0]
kernel_offset = struct.unpack('<I', alpine_data[16:20])[0]

print(f"Kernel offset: 0x{kernel_offset:x}, size: {kernel_size:,} bytes")
print(f"Initrd size: {initrd_size:,} bytes")

# Extract kernel
kernel_pe = alpine_data[kernel_offset:kernel_offset + kernel_size]

# Find initrd via magic scan
initrd_data = None
for m in re.finditer(b'\x1f\x8b\x08|\x1f\x8b\x00|070701', alpine_data[kernel_offset + kernel_size:]):
    off = kernel_offset + kernel_size + m.start()
    if off + initrd_size <= len(alpine_data):
        initrd_data = alpine_data[off:off + initrd_size]
        initrd_file_off = off
        break

if initrd_data is None:
    initrd_data = alpine_data[kernel_offset + kernel_size:kernel_offset + kernel_size + initrd_size]
    initrd_file_off = kernel_offset + kernel_size

print(f"Initrd file offset: 0x{initrd_file_off:x}")
print(f"Extracted initrd: {len(initrd_data):,} bytes")

# Verify host-side initrd decompresses
print("\n[1] Verifying host-side initrd...")
try:
    host_decompressed = gzip.decompress(initrd_data)
    print(f"  ✓ Host initrd decompresses: {len(host_decompressed):,} bytes")
except Exception as e:
    print(f"  ✗ Host initrd decompression FAILED: {e}")
    sys.exit(1)

# Constants from standalone_alpine_boot.py
RAM_BASE = 0x80000000
KERNEL_OFFSET = 0x200000
RAM_SIZE = 64 * 1024 * 1024  # 64MB

# Initialize emulator core
print("\n[2] Initializing GPU emulator...")
core = SpatialRV64ICore(RAM_SIZE)

e_lfanew = struct.unpack('<I', kernel_pe[0x3C:0x40])[0]
if kernel_pe[e_lfanew:e_lfanew+4] == b'PE\x00\x00':
    opt = e_lfanew + 24
    if struct.unpack('<H', kernel_pe[opt:opt+2])[0] == 0x20b:  # PE32+
        kernel_mem_size = struct.unpack('<I', kernel_pe[opt+56:opt+60])[0]
    else:  # PE32
        kernel_mem_size = struct.unpack('<I', kernel_pe[opt+56:opt+60])[0]
else:
    kernel_mem_size = kernel_size

kernel_load_addr = RAM_BASE + KERNEL_OFFSET
initrd_load_addr = max(kernel_load_addr + ((kernel_mem_size + 4095) & ~4095),
                       RAM_BASE + 0x2800000)  # 40MB fixed offset (clear of OpenSBI FDT 0x82200000)
initrd_offset = initrd_load_addr - RAM_BASE

print(f"  initrd_load_addr: 0x{initrd_load_addr:016x}")
print(f"  initrd_offset: 0x{initrd_offset:x}")

# Write initrd to emulator
print("\n[3] Writing initrd to GPU memory...")
print(f"  Writing {len(initrd_data):,} bytes at offset 0x{initrd_offset:x}...")
core.write_mem_bytes(initrd_offset, initrd_data)

# Read it back from GPU memory
print("\n[4] Reading initrd back from GPU memory...")
chunk_size = 65536  # 64KB chunks
initrd_readback = bytearray()

for i in range(0, initrd_size, chunk_size):
    read_size = min(chunk_size, initrd_size - i)
    # Round up to 4-byte alignment for wgpu
    read_size = (read_size + 3) & ~3
    chunk = core.queue.read_buffer(
        core.memory.buffer,
        buffer_offset=initrd_offset + i,
        size=read_size
    )
    # Trim to actual size if we rounded up
    chunk = chunk[:min(chunk_size, initrd_size - i)]
    initrd_readback.extend(chunk)
    if (i // chunk_size) % 10 == 0:
        print(f"  Read {len(initrd_readback):,} / {initrd_size:,} bytes", end='\r')

print(f"\n  Read {len(initrd_readback):,} bytes total")

# Save readback
with open('/tmp/initrd_emulator_readback.bin', 'wb') as f:
    f.write(initrd_readback)

# Byte-by-byte comparison
print("\n[5] Byte-by-byte comparison...")
if len(initrd_data) != len(initrd_readback):
    print(f"  ✗ LENGTH MISMATCH!")
    print(f"    Host: {len(initrd_data):,} bytes")
    print(f"    Emulator: {len(initrd_readback):,} bytes")
else:
    print(f"  Lengths match: {len(initrd_data):,} bytes")

    # Count differences
    diff_count = 0
    first_diff = None
    last_diff = None
    diff_offsets = []

    for i in range(len(initrd_data)):
        if initrd_data[i] != initrd_readback[i]:
            diff_count += 1
            if first_diff is None:
                first_diff = i
            last_diff = i
            if len(diff_offsets) < 20:  # Track first 20
                diff_offsets.append(i)

    if diff_count == 0:
        print(f"  ✓ PERFECT MATCH - No corruption detected!")
    else:
        print(f"  ✗ CORRUPTION DETECTED: {diff_count} differing bytes")
        print(f"    First difference at offset: 0x{first_diff:x} ({first_diff:,})")
        print(f"    Last difference at offset: 0x{last_diff:x} ({last_diff:,})")

        # Show context around first few differences
        print(f"\n  First few differences:")
        for off in diff_offsets[:5]:
            print(f"    Offset 0x{off:06x}: host=0x{initrd_data[off]:02x} emu=0x{initrd_readback[off]:02x}")

# Try to decompress readback
print("\n[6] Decompressing emulator readback...")
try:
    emu_decompressed = gzip.decompress(initrd_readback)
    print(f"  ✓ Emulator readback decompresses: {len(emu_decompressed):,} bytes")

    if len(host_decompressed) == len(emu_decompressed):
        print(f"  ✓ Decompressed sizes match")
    else:
        print(f"  ✗ Decompressed sizes differ:")
        print(f"    Host: {len(host_decompressed):,} bytes")
        print(f"    Emulator: {len(emu_decompressed):,} bytes")

except gzip.BadGzipFile as e:
    print(f"  ✗ FAILED: BadGzipFile - {e}")
except OSError as e:
    print(f"  ✗ FAILED: OSError - {e}")
except Exception as e:
    print(f"  ✗ FAILED: {type(e).__name__} - {e}")

# Final conclusion
print("\n" + "="*70)
print("CONCLUSION")
print("="*70)

if diff_count == 0:
    print("✓ write_mem_bytes() is CORRECT - no corruption detected.")
    print("  The corruption must be in the GUEST KERNEL's memory reads")
    print("  through MMU/TLB/Hilbert mapping during boot.")
elif 'emu_decompressed' not in locals():
    print("✗ Corruption breaks gzip - GPU memory is corrupted during write.")
    print("  BUG in write_mem_bytes() or Hilbert mapping!")
else:
    print("⚠ Emulator memory has corruption but still decompresses.")
    print("  The corruption might be subtle/trailing bytes.")
    print("  Could still break initramfs unpacking.")