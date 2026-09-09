#!/usr/bin/env python3
"""
Minimal V4 payload builder for kernel + initramfs only (no rootfs).
Creates a simple V4BOOT00 structure with just the essential boot components.
"""

import sys
import struct
from pathlib import Path

PROJECT_ROOT = Path("/home/jericho/projects/zion/projects/visual_audio")

def build_minimal_v4_payload(
    kernel_path: Path,
    initramfs_path: Path,
    output_path: Path
):
    """
    Build a minimal V4BOOT00 payload containing only kernel and initramfs.

    Format:
    [0..8]   Magic "V4BOOT00"
    [8..16]  Payload count (2: kernel + initramfs)
    [16..N]  Payload entries (16 bytes each)
             - offset (8 bytes)
             - size (8 bytes)
    [M..]    Kernel data
    [K..]    Initramfs data
    """

    print(f"Building minimal V4 payload...")
    print(f"  Kernel: {kernel_path}")
    print(f"  Initramfs: {initramfs_path}")
    print(f"  Output: {output_path}")

    # Read inputs
    kernel_data = kernel_path.read_bytes()
    initramfs_data = initramfs_path.read_bytes()

    print(f"  Kernel size: {len(kernel_data)} bytes")
    print(f"  Initramfs size: {len(initramfs_data)} bytes")

    # Build header
    magic = b'V4BOOT00'
    payload_count = 2

    # Align payloads to 4096 bytes
    def align(size, alignment=4096):
        return ((size + alignment - 1) // alignment) * alignment

    # Calculate offsets
    # Header: magic (8) + count (8) + entries (16 * 2 = 32) = 48 bytes
    header_size = 48
    kernel_offset = align(header_size)
    kernel_size_aligned = align(len(kernel_data))
    initramfs_offset = kernel_offset + kernel_size_aligned
    initramfs_size_aligned = align(len(initramfs_data))

    # Build payload entries
    entries = []
    entries.append(struct.pack('<QQ', kernel_offset, len(kernel_data)))
    entries.append(struct.pack('<QQ', initramfs_offset, len(initramfs_data)))

    # Calculate total size
    total_size = initramfs_offset + initramfs_size_aligned

    print(f"  Kernel offset: {kernel_offset}")
    print(f"  Initramfs offset: {initramfs_offset}")
    print(f"  Total size: {total_size} bytes ({total_size / 1024 / 1024:.2f} MB)")

    # Write output
    with open(output_path, 'wb') as f:
        # Write magic
        f.write(magic)

        # Write payload count
        f.write(struct.pack('<Q', payload_count))

        # Write payload entries
        for entry in entries:
            f.write(entry)

        # Pad to kernel offset
        current_pos = f.tell()
        if current_pos < kernel_offset:
            f.write(b'\x00' * (kernel_offset - current_pos))

        # Write kernel
        f.write(kernel_data)

        # Pad to initramfs offset
        current_pos = f.tell()
        if current_pos < initramfs_offset:
            f.write(b'\x00' * (initramfs_offset - current_pos))

        # Write initramfs
        f.write(initramfs_data)

        # Pad to total size
        current_pos = f.tell()
        if current_pos < total_size:
            f.write(b'\x00' * (total_size - current_pos))

    print(f"✓ V4 payload written successfully: {output_path}")

if __name__ == '__main__':
    kernel = PROJECT_ROOT / "ubuntu_vmlinuz"
    initramfs = PROJECT_ROOT / "boot_images/tiny_x86_initrd_v2.gz"
    output = Path("/tmp/ubuntu_v4_minimal_payload.img")

    if not kernel.exists():
        print(f"ERROR: Kernel not found: {kernel}")
        sys.exit(1)

    if not initramfs.exists():
        print(f"ERROR: Initramfs not found: {initramfs}")
        sys.exit(1)

    build_minimal_v4_payload(kernel, initramfs, output)
    print(f"\nNext steps:")
    print(f"1. Copy this payload to the V4 disk partition 2:")
    print(f"   dd if={output} of=/tmp/ubuntu_v4_efi.img bs=1 seek=68157440 conv=notrunc")
    print(f"2. Boot with QEMU:")