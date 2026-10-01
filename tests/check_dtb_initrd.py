#!/usr/bin/env python3
"""
Check what DTB initrd properties are generated.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))

from create_dtb import build_device_tree
import struct

# Constants from standalone_alpine_boot.py
RAM_BASE = 0x80000000
KERNEL_OFFSET = 0x200000
RAM_SIZE = 64 * 1024 * 1024

# Load alpine image
with open('/home/jericho/projects/zion/projects/visual_audio/boot_images/alpine_riscv64.lnx.bin', 'rb') as f:
    alpine_data = f.read()

kernel_size = struct.unpack('<I', alpine_data[8:12])[0]
initrd_size = struct.unpack('<I', alpine_data[12:16])[0]
kernel_offset = struct.unpack('<I', alpine_data[16:20])[0]
kernel_pe = alpine_data[kernel_offset:kernel_offset + kernel_size]

# Find initrd
import re
initrd_data = None
for m in re.finditer(b'\x1f\x8b\x08|\x1f\x8b\x00|070701', alpine_data[kernel_offset + kernel_size:]):
    off = kernel_offset + kernel_size + m.start()
    if off + initrd_size <= len(alpine_data):
        initrd_data = alpine_data[off:off + initrd_size]
        break

# Calculate addresses
e_lfanew = struct.unpack('<I', kernel_pe[0x3C:0x40])[0]
if kernel_pe[e_lfanew:e_lfanew+4] == b'PE\x00\x00':
    opt = e_lfanew + 24
    if struct.unpack('<H', kernel_pe[opt:opt+2])[0] == 0x20b:
        kernel_mem_size = struct.unpack('<I', kernel_pe[opt+56:opt+60])[0]
    else:
        kernel_mem_size = struct.unpack('<I', kernel_pe[opt+56:opt+60])[0]
else:
    kernel_mem_size = kernel_size

kernel_load_addr = RAM_BASE + KERNEL_OFFSET
initrd_load_addr = max(kernel_load_addr + ((kernel_mem_size + 4095) & ~4095),
                       RAM_BASE + 0x2800000)  # 40MB fixed offset (clear of OpenSBI FDT 0x82200000)

print("Boot image info:")
print(f"  kernel_size: {kernel_size:,} bytes")
print(f"  initrd_size: {initrd_size:,} bytes")
print(f"  kernel_mem_size (PE SizeOfImage): {kernel_mem_size:,} bytes")

print("\nCalculated load addresses:")
print(f"  kernel_load_addr: 0x{kernel_load_addr:016x}")
print(f"  initrd_load_addr: 0x{initrd_load_addr:016x}")
print(f"  initrd_end: 0x{initrd_load_addr + initrd_size:016x}")

# Generate DTB
dtb = build_device_tree(
    ram_base=RAM_BASE,
    ram_size=RAM_SIZE,
    uart_base=0x10000000,
    isa='rv64imafdc',
    timebase=10_000_000,
    bootargs='earlycon=uart8250,mmio,0x10000000 console=ttyS0',
    kernel_addr=kernel_load_addr,
    initrd_addr=initrd_load_addr,
    initrd_size=initrd_size,
)

print(f"\nDTB size: {len(dtb):,} bytes")

# Extract initrd properties from DTB
import fdt

# Parse the DTB
dtb_obj = fdt.parse_dtb(dtb)

# Find /chosen node
chosen = dtb_obj.get_node('/chosen')

print("\n/chosen node properties:")
for name, value in chosen:
    print(f"  {name}: {value}")

# Check initrd properties
initrd_start_prop = chosen.get_property('linux,initrd-start')
initrd_end_prop = chosen.get_property('linux,initrd-end')

if initrd_start_prop:
    print(f"\nlinux,initrd-start: {hex(initrd_start_prop.value)}")
else:
    print("\nWARNING: linux,initrd-start not found!")

if initrd_end_prop:
    print(f"linux,initrd-end: {hex(initrd_end_prop.value)}")
else:
    print("WARNING: linux,initrd-end not found!")

if initrd_start_prop and initrd_end_prop:
    dtb_initrd_size = initrd_end_prop.value - initrd_start_prop.value
    print(f"\nDTB initrd size: {dtb_initrd_size:,} bytes (0x{dtb_initrd_size:x})")
    print(f"Expected initrd size: {initrd_size:,} bytes (0x{initrd_size:x})")
    print(f"Match: {'✓' if dtb_initrd_size == initrd_size else '✗'}")