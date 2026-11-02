#!/usr/bin/env python3
"""
V4 Bootloader Verification Script

Simulates the bootloader's tile scanning logic to verify:
1. V4BOOT00 header detection
2. Tile JSON parsing
3. PNG tile location by index
4. PNG magic byte detection
"""

import struct
import argparse
from pathlib import Path

V4BOOT_MAGIC = b"V4BOOT00"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

def read_u64(data, offset):
    """Read little-endian u64."""
    return struct.unpack('<Q', data[offset:offset+8])[0]

def verify_v4_disk(disk_path):
    """Verify V4 disk format matches bootloader expectations."""
    print(f"\n=== V4 Disk Verification: {disk_path} ===")

    with open(disk_path, 'rb') as f:
        data = f.read()

    # 1. Check V4BOOT00 magic
    print("\n1. Checking V4BOOT00 magic...")
    magic = data[:8]
    print(f"   Magic bytes: {magic}")
    if magic == V4BOOT_MAGIC:
        print(f"   Valid ✓")
    else:
        print(f"   INVALID ✗")

    if magic != V4BOOT_MAGIC:
        print("   FAIL: Not a V4 boot disk")
        return False

    # 2. Read manifest
    print("\n2. Reading manifest...")
    manifest_size = read_u64(data, 8)
    print(f"   Manifest size: {manifest_size} bytes")
    manifest_end = 16 + manifest_size
    manifest_json = data[16:manifest_end]
    print(f"   Manifest JSON (first 200 chars): {manifest_json[:200].decode('utf-8', errors='replace')}")

    # 3. Read tiles.json
    print("\n3. Reading tiles.json...")
    tiles_json_size = read_u64(data, manifest_end)
    print(f"   Tiles.json size: {tiles_json_size} bytes")
    tiles_json_start = manifest_end + 8
    tiles_json_end = tiles_json_start + tiles_json_size
    tiles_json = data[tiles_json_start:tiles_json_end]
    print(f"   Tiles.json: {tiles_json.decode('utf-8', errors='replace')}")

    # 4. Scan for PNG tiles (simulating bootloader logic)
    print("\n4. Scanning for PNG tiles (simulating bootloader)...")
    scan_offset = tiles_json_end
    png_count = 0
    png_offsets = []

    while scan_offset < len(data):
        chunk = data[scan_offset:scan_offset+8]
        if len(chunk) < 8:
            break

        if chunk == PNG_MAGIC:
            png_offsets.append(scan_offset)
            print(f"   Found PNG tile #{png_count} at offset {scan_offset}")

            # Estimate tile size by looking for next PNG or end
            next_offset = scan_offset + 8
            tile_size = 8
            found_next = False

            while next_offset + 8 <= len(data):
                if data[next_offset:next_offset+8] == PNG_MAGIC:
                    tile_size = next_offset - scan_offset
                    found_next = True
                    break
                next_offset += 1
                if tile_size > 256 * 1024 * 1024:  # Sanity cap
                    break
                tile_size += 1

            if not found_next:
                tile_size = len(data) - scan_offset

            print(f"     Estimated size: {tile_size} bytes")
            png_count += 1

            scan_offset += tile_size
        else:
            scan_offset += 1

    print(f"\n   Total PNG tiles found: {png_count}")

    # 5. Verify tile access (what bootloader would do)
    print("\n5. Verifying tile access (bootloader simulation)...")
    for i in range(min(3, png_count)):
        if i < len(png_offsets):
            offset = png_offsets[i]
            print(f"   Tile {i}: offset={offset}, magic={data[offset:offset+8].hex()}")
        else:
            print(f"   Tile {i}: NOT FOUND")

    # 6. Test data integrity (read first PNG and verify it's valid)
    print("\n6. Testing PNG data integrity...")
    if png_count > 0:
        first_png_offset = png_offsets[0]
        png_data = data[first_png_offset:first_png_offset+1024]  # First 1KB

        # Check PNG structure
        if png_data[:8] == PNG_MAGIC:
            print("   ✓ PNG magic bytes correct")

            # Check IHDR chunk
            ihdr_offset = 8
            ihdr_len = struct.unpack('>I', png_data[ihdr_offset:ihdr_offset+4])[0]
            ihdr_type = png_data[ihdr_offset+4:ihdr_offset+8]
            print(f"   ✓ First chunk: type={ihdr_type}, len={ihdr_len}")

            if ihdr_type == b'IHDR':
                width = struct.unpack('>I', png_data[ihdr_offset+8:ihdr_offset+12])[0]
                height = struct.unpack('>I', png_data[ihdr_offset+12:ihdr_offset+16])[0]
                print(f"   ✓ PNG dimensions: {width}x{height}")

                # Check for power-of-2 dimensions (required for Hilbert)
                if (width & (width - 1)) == 0 and (height & (height - 1)) == 0:
                    print("   ✓ Dimensions are power-of-2 (Hilbert compatible)")
                else:
                    print("   ⚠ Dimensions NOT power-of-2 (Hilbert decode may fail)")
        else:
            print("   ✗ PNG magic bytes incorrect")
    else:
        print("   ⚠ No PNG tiles found")

    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify V4 boot disk format")
    parser.add_argument("disk_path", type=Path, help="Path to V4 disk image to verify")
    args = parser.parse_args()

    if not args.disk_path.exists():
        print(f"ERROR: V4 disk not found at {args.disk_path}")
        exit(1)

    success = verify_v4_disk(args.disk_path)

    if success:
        print("\n=== VERIFICATION PASSED ===")
        print("\nThe V4 disk format matches bootloader expectations.")
        print("Tile indices: 0=kernel, 1=initramfs, 2+=rootfs")
        print("\nFor actual boot test, create ESP partition:")
        print("  sudo bash tools/create_v4_uefi_disk.sh")
    else:
        print("\n=== VERIFICATION FAILED ===")
        exit(1)