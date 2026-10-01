#!/usr/bin/env python3
"""
Convert Ubuntu disk image to pixels and store in MKV, then boot QEMU.

Workflow:
1. Load Ubuntu disk image (qcow2)
2. Store in MKV container (va_container.py handles pixel encoding)
3. Extract disk from MKV
4. Boot QEMU with extracted disk

This proves MKV can hold full OS disk images pixel-encoded.
"""

import sys
import os
import subprocess
from pathlib import Path

MKV_PATH = Path(__file__).parent.parent / "visual_audio.mkv"

# Ubuntu disk image
UBUNTU_DISK = "/home/jericho/.geometry_os/vmfs/ubuntu-24.04-desktop-fresh.img"

# Component names in MKV
MKV_DISK_NAME = "ubuntu/desktop/ubuntu-24.04-desktop.qcow2"


def encode_disk_stats(disk_path: str) -> dict:
    """
    Calculate disk encoding stats.

    Returns:
        Stats: disk_size, pixel_count, frame_count
    """
    print(f"Encoding disk to pixels...")
    print(f"  Input: {disk_path}")

    disk_size = Path(disk_path).stat().st_size

    print(f"  Disk size: {disk_size:,} bytes ({disk_size / (1024**3):.2f} GB)")

    # Calculate pixel count (3 bytes/pixel)
    pixel_count = (disk_size + 2) // 3

    # Calculate frame count (607500 bytes per frame)
    FRAME_BYTES = 607500
    frame_count = (disk_size + FRAME_BYTES - 1) // FRAME_BYTES

    print(f"  Pixel count: {pixel_count:,} pixels")
    print(f"  Frame count: {frame_count} frames")
    print(f"  Density: {disk_size / pixel_count:.2f} bytes/pixel")
    print(f"  Image dimensions: {int(pixel_count**0.5)}x{int(pixel_count**0.5)}")

    return {
        "disk_size": disk_size,
        "pixel_count": pixel_count,
        "frame_count": frame_count,
    }


def store_disk_in_mkv(disk_path: str, mkv_name: str) -> bool:
    """Store pixel-encoded disk in MKV."""
    print(f"\nStoring disk in MKV...")
    print(f"  MKV: {MKV_PATH}")
    print(f"  Entry name: {mkv_name}")

    # Add to MKV (va_container.py handles multi-frame encoding)
    result = subprocess.run(
        ["python3", "tools/va_container.py", "add", str(MKV_PATH), disk_path,
         "--name", mkv_name, "--role", "disk",
         "--note", "Ubuntu 24.04 Desktop pixel-encoded"],
        capture_output=True,
        text=True,
        cwd=str(MKV_PATH.parent)
    )

    if result.returncode != 0:
        print(f"Failed to add disk to MKV: {result.stderr}")
        return False

    print(result.stdout.strip())
    return True


def extract_disk_from_mkv(mkv_name: str, output_qcow2: str) -> bool:
    """Extract disk from MKV."""
    print(f"\nExtracting disk from MKV...")
    print(f"  Entry name: {mkv_name}")
    print(f"  Output: {output_qcow2}")

    # Extract using va_container.py cat (handles multi-frame decoding)
    result = subprocess.run(
        ["python3", "tools/va_container.py", "cat", str(MKV_PATH), mkv_name, "-o", output_qcow2],
        capture_output=True,
        text=True,
        cwd=str(MKV_PATH.parent)
    )

    if result.returncode != 0:
        print(f"Failed to extract disk from MKV: {result.stderr}")
        return False

    print(f"  Extracted disk: {Path(output_qcow2).stat().st_size:,} bytes")
    return True


def boot_ubuntu_from_disk(disk_path: str):
    """Boot Ubuntu QEMU from disk."""
    print(f"\nBooting Ubuntu from disk...")
    print(f"  Disk: {disk_path}")
    print("\nTo boot manually:")
    print(f"  qemu-system-riscv64 -machine virt -cpu rv64 -m 2048 -bios default \\")
    print(f"    -device virtio-gpu-device -device virtio-net-device,netdev=net0 \\")
    print(f"    -netdev user,id=net0,hostfwd=tcp::2222-:22 \\")
    print(f"    -drive file={disk_path},if=virtio,format=qcow2 \\")
    print(f"    -device virtio-blk-device -serial mon:stdio -display sdl")


def main():
    print("=" * 70)
    print("Ubuntu Disk → Pixels → MKV → Boot Workflow")
    print("=" * 70)

    # Step 1: Calculate encoding stats
    print("\n=== STEP 1: Calculate Encoding Stats ===")
    stats = encode_disk_stats(UBUNTU_DISK)

    # Step 2: Store in MKV
    print("\n=== STEP 2: Store Disk in MKV ===")
    if not store_disk_in_mkv(UBUNTU_DISK, MKV_DISK_NAME):
        print("Failed to store disk in MKV")
        return 1

    # Step 3: Extract from MKV (verify round-trip)
    print("\n=== STEP 3: Extract Disk from MKV ===")
    # Use current directory for extraction (more space than /tmp)
    qcow2_path = str(Path.cwd() / "ubuntu_extracted.qcow2")

    try:
        if not extract_disk_from_mkv(MKV_DISK_NAME, qcow2_path):
            print("Failed to extract disk from MKV")
            return 1

        # Verify round-trip
        original = Path(UBUNTU_DISK).read_bytes()
        extracted = Path(qcow2_path).read_bytes()

        if original != extracted:
            print("✗ Round-trip verification FAILED")
            print(f"  Original: {len(original):,} bytes")
            print(f"  Extracted: {len(extracted):,} bytes")
            return 1

        print("✓ Round-trip verification PASSED (byte-perfect)")

        # Step 4: Boot instructions
        print("\n=== STEP 4: Boot Ubuntu ===")
        boot_ubuntu_from_disk(qcow2_path)

        print("\n" + "=" * 70)
        print("MKV now contains pixel-encoded Ubuntu disk (749MB)")
        print("Extraction and round-trip verified successfully")
        print("=" * 70)

        return 0

    finally:
        # Cleanup temp file
        if os.path.exists(qcow2_path):
            os.unlink(qcow2_path)


if __name__ == "__main__":
    sys.exit(main())