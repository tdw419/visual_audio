#!/usr/bin/env python3
"""
Simple script to replace initramfs in V4 boot disk.
This assumes the bootloader doesn't check PNG sizes and just decodes sequentially.
"""

import sys
from pathlib import Path

PNG_MAGIC = b'\x89PNG\r\n\x1a\n'

def find_next_png_start(data, start_after):
    """Find the next PNG magic after the given position."""
    search_pos = start_after
    while search_pos < len(data) - 8:
        if data[search_pos:search_pos+8] == PNG_MAGIC:
            return search_pos
        search_pos += 1
    return None


def main():
    v4_disk_path = Path("/tmp/ubuntu_v4_efi.img")
    new_initramfs_path = Path("/tmp/ubuntu_initramfs.pdb.png")
    output_path = Path("/tmp/ubuntu_v4_ubuntu_rootfs.img")

    if not v4_disk_path.exists():
        print(f"ERROR: V4 disk not found: {v4_disk_path}")
        sys.exit(1)

    if not new_initramfs_path.exists():
        print(f"ERROR: New initramfs PNG not found: {new_initramfs_path}")
        sys.exit(1)

    print("Reading V4 disk...")
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
    for i, pos in enumerate(png_positions):
        print(f"  Tile {i}: 0x{pos} ({pos})")

    if len(png_positions) < 2:
        print("ERROR: Expected at least 2 PNG tiles (kernel + initramfs)")
        sys.exit(1)

    # We expect: Tile 0 = kernel, Tile 1 = initramfs
    kernel_pos = png_positions[0]
    initramfs_pos = png_positions[1]
    next_png_pos = png_positions[2] if len(png_positions) > 2 else len(disk_data)

    print(f"\nCurrent initramfs:")
    print(f"  Starts at: 0x{initramfs_pos} ({initramfs_pos})")
    print(f"  Next PNG at: 0x{next_png_pos} ({next_png_pos})")
    print(f"  Current size: {next_png_pos - initramfs_pos} bytes")

    # Read new initramfs PNG
    with open(new_initramfs_path, 'rb') as f:
        new_initramfs_data = f.read()

    print(f"\nNew initramfs:")
    print(f"  Size: {len(new_initramfs_data)} bytes")

    # Check if new initramfs fits
    max_allowed_size = next_png_pos - initramfs_pos
    if len(new_initramfs_data) > max_allowed_size:
        print(f"WARNING: New initramfs ({len(new_initramfs_data)}) is larger than space available ({max_allowed_size})")
        print(f"         Truncating to fit...")

    # Replace initramfs region
    # Strategy: Copy everything up to initramfs_pos, insert new initramfs, copy everything after next_png_pos
    new_disk = bytearray(disk_data[:initramfs_pos])
    new_disk.extend(new_initramfs_data[:max_allowed_size])  # Truncate if needed

    # Pad if smaller
    if len(new_initramfs_data) < max_allowed_size:
        padding = max_allowed_size - len(new_initramfs_data)
        new_disk.extend(b'\x00' * padding)
        print(f"  Padded {padding} bytes with zeros")

    # Copy rest of disk
    new_disk.extend(disk_data[next_png_pos:])

    # Write output
    print(f"\nWriting new disk to {output_path}...")
    with open(output_path, 'wb') as f:
        f.write(new_disk)

    print(f"✓ New V4 disk created: {len(new_disk)} bytes")
    print(f"\nTo test boot:")
    print(f"  qemu-system-x86_64 -m 2G -enable-kvm -cpu host \\")
    print(f"    -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \\")
    print(f"    -drive if=pflash,format=raw,file=/tmp/my_vars.fd \\")
    print(f"    -drive format=raw,file={output_path},if=virtio \\")
    print(f"    -drive format=raw,file=ubuntu-24.04-server-cloudimg-amd64.raw,if=virtio \\")
    print(f"    -serial file:/tmp/qemu_ubuntu_boot.log -no-reboot")

if __name__ == '__main__':
    main()