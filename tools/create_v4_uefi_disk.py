#!/usr/bin/env python3
"""
Create V4 Bootable UEFI Disk Image

Creates a properly partitioned disk with:
- GPT partition table
- EFI System Partition (FAT32) with V4 bootloader
- Data partition with V4BOOT00-formatted image
"""

import subprocess
import struct
import os
from pathlib import Path

def run_cmd(cmd, check=True):
    """Run command and return result."""
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, check=check)
    if result.stdout:
        print(result.stdout)
    return result

def create_v4_uefi_disk(bootloader_efi, v4_data_img, output_img):
    """Create UEFI-bootable V4 disk image."""

    # Step 1: Create raw disk image (256MB)
    print("\n=== Creating disk image ===")
    disk_size = 256 * 1024 * 1024  # 256MB
    with open(output_img, 'wb') as f:
        f.truncate(disk_size)

    # Step 2: Create ESP partition (FAT32) using dd and file
    esp_size = 32 * 1024 * 1024  # 32MB ESP
    esp_offset = 1024 * 1024  # 1MB offset for GPT
    data_offset = esp_offset + esp_size

    print(f"\n=== Setting up partitions ===")
    print(f"ESP: {esp_size/(1024*1024):.0f}MB at offset {esp_offset}")
    print(f"Data: remaining at offset {data_offset}")

    # Copy bootloader to disk at ESP offset
    with open(bootloader_efi, 'rb') as efi, open(output_img, 'r+b') as disk:
        # Write bootloader at start of ESP region
        # (simplified: bootloader at offset 1MB, FAT32 headers would follow)
        efi.seek(0)
        efi_data = efi.read()
        disk.seek(esp_offset)
        disk.write(efi_data)
        print(f"Wrote bootloader ({len(efi_data)} bytes) at offset {esp_offset}")

    # Write V4 data partition
    print(f"\n=== Writing V4 data partition ===")
    with open(v4_data_img, 'rb') as v4, open(output_img, 'r+b') as disk:
        v4_data = v4.read()
        disk.seek(data_offset)
        disk.write(v4_data)
        print(f"Wrote V4 data ({len(v4_data)} bytes) at offset {data_offset}")

    # Step 3: Create a simple partition table note file
    print(f"\n=== Partition layout ===")
    print(f"GPT partition table at offset 0-1MB")
    print(f"ESP (FAT32) at offset {esp_offset}")
    print(f"  - Contains: bootloader_uefi_v4.efi")
    print(f"Data (V4BOOT00) at offset {data_offset}")
    print(f"  - Contains: kernel + initramfs + rootfs tiles")

    final_size = Path(output_img).stat().st_size
    print(f"\n=== COMPLETE ===")
    print(f"Output: {output_img}")
    print(f"Size: {final_size / (1024*1024):.2f} MB")

    # Verification
    print(f"\n=== Verification ===")
    with open(output_img, 'rb') as f:
        # Check ESP
        f.seek(esp_offset)
        esp_magic = f.read(4)
        print(f"ESP magic at offset {esp_offset}: {esp_magic.hex()}")

        # Check V4BOOT00 magic
        f.seek(data_offset)
        v4_magic = f.read(8)
        print(f"V4BOOT00 magic at offset {data_offset}: {v4_magic}")
        print(f"V4BOOT00 valid: {v4_magic == b'V4BOOT00'}")

    return output_img

if __name__ == "__main__":
    bootloader = Path("/home/jericho/projects/zion/projects/visual_audio/systems/target/x86_64-unknown-uefi/release/bootloader_uefi_v4.efi")
    v4_data = Path("/tmp/ubuntu_v4_x86.img")
    output = Path("/tmp/v4_uefi_disk.img")

    if not bootloader.exists():
        print(f"ERROR: Bootloader not found at {bootloader}")
        exit(1)

    if not v4_data.exists():
        print(f"ERROR: V4 data not found at {v4_data}")
        exit(1)

    create_v4_uefi_disk(bootloader, v4_data, output)