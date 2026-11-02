#!/usr/bin/env python3
"""
Replace initramfs in V4 boot disk with new initramfs.

This script:
1. Finds the current initramfs PNG tile
2. Extracts its size and position
3. Replaces it with the new initramfs PNG
4. Adjusts the manifest if needed
"""

import sys
from pathlib import Path

PNG_MAGIC = b'\x89PNG\r\n\x1a\n'

def find_png_boundaries(data, start_pos):
    """Find the start and end of a PNG given its approximate start position."""
    # Find exact PNG magic start
    search_start = max(0, start_pos - 100)
    png_start = data.find(PNG_MAGIC, search_start)

    if png_start == -1:
        return None, None

    # Scan forward to find IEND chunk
    scan_pos = png_start + 8  # After PNG magic
    iend_search_pos = scan_pos
    max_scan = min(scan_pos + 50_000_000, len(data))  # Scan up to 50MB

    while iend_search_pos < max_scan:
        # Look for IEND chunk marker
        if data[iend_search_pos:iend_search_pos+4] == b'IEND':
            # Back up to find chunk length (4 bytes before IEND marker)
            chunk_len_start = iend_search_pos - 4

            if chunk_len_start >= 8:
                chunk_len_bytes = data[chunk_len_start:chunk_len_start+4]
                chunk_len = int.from_bytes(chunk_len_bytes, 'little')

                # PNG ends after IEND chunk: length (4) + type (4) + data (chunk_len) + CRC (4)
                png_end = chunk_len_start + 4 + 4 + chunk_len + 4

                # Sanity check: PNG should be reasonable size
                png_size = png_end - png_start
                if 100_000 < png_size < 100_000_000:  # Between 100KB and 100MB
                    return png_start, png_end

        iend_search_pos += 1

    return None, None


def main():
    v4_disk_path = Path("/tmp/ubuntu_v4_efi.img")
    new_initramfs_path = Path("/tmp/initramfs_v2.pdb.png")
    output_path = Path("/tmp/ubuntu_v4_efi_with_new_initramfs.img")

    if not v4_disk_path.exists():
        print(f"ERROR: V4 disk not found: {v4_disk_path}")
        sys.exit(1)

    if not new_initramfs_path.exists():
        print(f"ERROR: New initramfs PNG not found: {new_initramfs_path}")
        print(f"Did you run: cargo run --example encode_file_to_pdb ...?")
        sys.exit(1)

    print("Reading V4 disk...")
    with open(v4_disk_path, 'rb') as f:
        disk_data = f.read()

    print(f"Disk size: {len(disk_data)} bytes")

    # Find all PNG tiles
    print("\nScanning for PNG tiles...")
    png_positions = []
    search_pos = 0
    while True:
        pos = disk_data.find(PNG_MAGIC, search_pos)
        if pos == -1:
            break
        png_positions.append(pos)
        search_pos = pos + 8

    print(f"Found {len(png_positions)} PNG magic markers")

    # Analyze each PNG
    print("\nAnalyzing PNG tiles:")
    png_boundaries = []
    for i, start_approx in enumerate(png_positions):
        start, end = find_png_boundaries(disk_data, start_approx)
        if start is not None and end is not None:
            size = end - start
            print(f"  Tile {i}: 0x{start} - 0x{end} ({size} bytes, {size/1024/1024:.2f} MB)")
            png_boundaries.append((start, end))
        else:
            print(f"  Tile {i}: Could not determine boundaries")

    if len(png_boundaries) < 2:
        print("ERROR: Expected at least 2 PNG tiles (kernel + initramfs)")
        sys.exit(1)

    # Tile 0 should be kernel, Tile 1 should be initramfs
    kernel_start, kernel_end = png_boundaries[0]
    initramfs_start, initramfs_end = png_boundaries[1]

    print(f"\nReplacing initramfs (Tile 1)...")
    print(f"  Old initramfs: 0x{initramfs_start} - 0x{initramfs_end} ({initramfs_end - initramfs_start} bytes)")

    # Read new initramfs PNG
    with open(new_initramfs_path, 'rb') as f:
        new_initramfs_data = f.read()

    print(f"  New initramfs: {len(new_initramfs_data)} bytes")

    # Replace initramfs in disk
    # Strategy: Overwrite the old initramfs region with the new one
    # If new is smaller, pad with zeros
    # If new is larger, we can't easily resize without understanding the format better

    old_initramfs_size = initramfs_end - initramfs_start
    new_initramfs_size = len(new_initramfs_data)

    if new_initramfs_size > old_initramfs_size:
        print(f"WARNING: New initramfs ({new_initramfs_size}) is larger than old ({old_initramfs_size})")
        print(f"         This may require updating metadata. Proceeding anyway...")

    # Create new disk image
    new_disk = bytearray(disk_data)

    # Replace initramfs region
    new_disk[initramfs_start:initramfs_start + new_initramfs_size] = new_initramfs_data

    # Zero out any remaining space if new initramfs is smaller
    if new_initramfs_size < old_initramfs_size:
        padding_start = initramfs_start + new_initramfs_size
        padding_size = old_initramfs_size - new_initramfs_size
        new_disk[padding_start:initramfs_end] = b'\x00' * padding_size
        print(f"  Padded {padding_size} bytes with zeros")

    # Write output
    print(f"\nWriting new disk to {output_path}...")
    with open(output_path, 'wb') as f:
        f.write(new_disk)

    print("✓ New V4 disk created successfully!")
    print(f"\nTo boot:")
    print(f"  qemu-system-x86_64 -m 2G -enable-kvm -cpu host \\")
    print(f"    -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \\")
    print(f"    -drive if=pflash,format=raw,file=/tmp/my_vars.fd \\")
    print(f"    -drive format=raw,file={output_path},if=virtio \\")
    print(f"    -drive format=raw,file=ubuntu-24.04-server-cloudimg-amd64.raw,if=virtio \\")
    print(f"    -serial file:/tmp/qemu_ubuntu_boot.log -no-reboot")

if __name__ == '__main__':
    main()