#!/usr/bin/env python3
"""
Replace initramfs in V4 boot disk IN PLACE (preserving ESP partition).
This opens the disk in r+ mode and only modifies the initramfs region.
"""

import sys
from pathlib import Path

PNG_MAGIC = b'\x89PNG\r\n\x1a\n'

def main():
    v4_disk_path = Path("/tmp/ubuntu_v4_efi.img")
    new_initramfs_path = Path("/tmp/ubuntu_initramfs.pdb.png")

    if not v4_disk_path.exists():
        print(f"ERROR: V4 disk not found: {v4_disk_path}")
        sys.exit(1)

    if not new_initramfs_path.exists():
        print(f"ERROR: New initramfs PNG not found: {new_initramfs_path}")
        sys.exit(1)

    print(f"Opening {v4_disk_path} for in-place modification...")

    # Read the disk to find PNG positions
    with open(v4_disk_path, 'rb') as f:
        disk_data = f.read()

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

    print(f"Found {len(png_positions)} PNG magic markers")

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
    print(f"  Current size: {next_png_pos - initramfs_pos} bytes")

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

    # Open the disk for in-place modification
    print(f"\nModifying disk in place at {v4_disk_path}...")
    with open(v4_disk_path, 'r+b') as f:
        # Seek to initramfs position
        f.seek(initramfs_pos)

        # Write new initramfs
        f.write(new_initramfs_data)

        # Pad with zeros if smaller
        if len(new_initramfs_data) < max_allowed_size:
            padding = max_allowed_size - len(new_initramfs_data)
            f.write(b'\x00' * padding)
            print(f"  Padded {padding} bytes with zeros")

    print(f"✓ Disk modified in place!")
    print(f"\nTo test boot:")
    print(f"  qemu-system-x86_64 -m 2G -enable-kvm -cpu host \\")
    print(f"    -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \\")
    print(f"    -drive if=pflash,format=raw,file=/tmp/my_vars.fd \\")
    print(f"    -drive format=raw,file={v4_disk_path},if=virtio \\")
    print(f"    -drive format=raw,file=ubuntu-24.04-server-cloudimg-amd64.raw,if=virtio \\")
    print(f"    -serial file:/tmp/qemu_ubuntu_boot.log -no-reboot")

if __name__ == '__main__':
    main()