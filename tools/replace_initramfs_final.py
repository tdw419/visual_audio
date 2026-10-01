#!/usr/bin/env python3
"""
CORRECTED: Replace initramfs in V4 boot disk, preserving all data including headers.
"""

import sys
from pathlib import Path

PNG_MAGIC = b'\x89PNG\r\n\x1a\n'

def main():
    v4_disk_path = Path("/tmp/ubuntu_v4_efi_backup.img")
    new_initramfs_path = Path("/tmp/ubuntu_initramfs.pdb.png")
    output_path = Path("/tmp/ubuntu_v4_with_ubuntu_initramfs.img")

    if not v4_disk_path.exists():
        print(f"ERROR: V4 disk not found: {v4_disk_path}")
        sys.exit(1)

    if not new_initramfs_path.exists():
        print(f"ERROR: New initramfs PNG not found: {new_initramfs_path}")
        sys.exit(1)

    print(f"Reading {v4_disk_path}...")
    with open(v4_disk_path, 'rb') as f:
        disk_data = bytearray(f.read())

    print(f"Disk size: {len(disk_data)} bytes")

    # Find all PNG magic positions
    print("\nFinding PNG tiles...")
    png_positions = []
    search_pos = 0
    while True:
        pos = disk_data.find(PNG_MAGIC, search_pos)
        if pos == -1:
            break
        png_positions.append(pos)
        search_pos = pos + 8

    print(f"Found {len(png_positions)} PNG magic markers at:")
    for i, pos in enumerate(png_positions[:4]):
        print(f"  Tile {i}: 0x{pos} ({pos})")

    if len(png_positions) < 2:
        print("ERROR: Expected at least 2 PNG tiles (kernel + initramfs)")
        sys.exit(1)

    # We expect: Tile 0 = kernel, Tile 1 = initramfs
    kernel_pos = png_positions[0]
    initramfs_pos = png_positions[1]
    next_png_pos = png_positions[2] if len(png_positions) > 2 else len(disk_data)

    print(f"\nInitramfs to replace:")
    print(f"  Starts at: 0x{initramfs_pos} ({initramfs_pos})")
    print(f"  Next PNG at: 0x{next_png_pos} ({next_png_pos})")
    print(f"  Available space: {next_png_pos - initramfs_pos} bytes")

    # Read new initramfs PNG
    with open(new_initramfs_path, 'rb') as f:
        new_initramfs_data = f.read()

    print(f"\nNew initramfs:")
    print(f"  Size: {len(new_initramfs_data)} bytes")

    # Check if new initramfs fits
    max_allowed_size = next_png_pos - initramfs_pos
    if len(new_initramfs_data) > max_allowed_size:
        print(f"ERROR: New initramfs ({len(new_initramfs_data)}) is larger than space available ({max_allowed_size})")
        sys.exit(1)

    # Create new disk by copying everything, replacing initramfs region
    print(f"\nCreating new disk...")
    new_disk = bytearray(disk_data[:initramfs_pos])  # Copy up to initramfs
    new_disk.extend(new_initramfs_data)  # Insert new initramfs

    # Pad with zeros if smaller
    if len(new_initramfs_data) < max_allowed_size:
        padding = max_allowed_size - len(new_initramfs_data)
        new_disk.extend(b'\x00' * padding)
        print(f"  Padded {padding} bytes with zeros")

    # Copy rest of disk after next PNG
    new_disk.extend(disk_data[next_png_pos:])

    print(f"New disk size: {len(new_disk)} bytes")

    # Verify V4BOOT00 magic is preserved
    v4_pos = new_disk.find(b'V4BOOT00')
    print(f"V4BOOT00 found at: 0x{v4_pos} ({v4_pos})")
    if v4_pos == -1:
        print("WARNING: V4BOOT00 magic not found!")

    # Write output
    print(f"\nWriting to {output_path}...")
    with open(output_path, 'wb') as f:
        f.write(new_disk)

    print(f"✓ New V4 disk created!")

if __name__ == '__main__':
    main()