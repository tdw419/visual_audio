#!/usr/bin/env python3
"""
Create a test disk image encoded with printable spatial frames.

This encodes a small test disk (~10MB) with full printable backup capability:
- Frame 0: Directory frame with filesystem metadata
- Frames 1-N: Data frames with header + primary + QR + footer encoding
"""

import hashlib
import json
import base64
import struct
import numpy as np
import sys
import os

# Add tools directory to path for qr_zone import
script_dir = os.path.dirname(os.path.abspath(__file__))
tools_dir = os.path.join(os.path.dirname(script_dir), 'tools')
sys.path.insert(0, tools_dir)

from qr_zone import add_qr_zone_to_frame


def hilbert_d2xy(n, d):
    """Convert Hilbert distance to 2D coordinates."""
    x, y = 0, 0
    s = 1
    while s < n:
        rx = 1 & (d // 2)
        ry = 1 & (d ^ rx)
        if ry == 0:
            if rx == 1:
                x = s - 1 - x
                y = s - 1 - y
        x, y = y, x
        x += s * rx
        y += s * ry
        d //= 4
        s *= 2
    return x, y


def encode_ascii85(data):
    """Encode data to Ascii85 (Adobe format)."""
    return base64.a85encode(data, foldspaces=False, pad=False)


def decode_ascii85(encoded):
    """Decode Ascii85 data."""
    return base64.a85decode(encoded)


def create_printable_frame(frame_idx, sector_start, sector_end, data, total_frames, frame_size=4096):
    """
    Create a frame with printable header, primary encoding, QR zone, and recovery footer.
    """
    frame = np.zeros((frame_size, frame_size, 3), dtype=np.uint8)

    # ===== HEADER (Rows 0-127) =====
    frame_idx_bytes = struct.pack('<I', frame_idx)
    for i, byte_val in enumerate(frame_idx_bytes):
        frame[10, 10 + i * 10:10 + i * 10 + 10, 0] = byte_val

    sector_start_bytes = struct.pack('<Q', sector_start)
    for i, byte_val in enumerate(sector_start_bytes):
        frame[20, 10 + i * 10:10 + i * 10 + 10, 1] = byte_val

    sector_end_bytes = struct.pack('<Q', sector_end)
    for i, byte_val in enumerate(sector_end_bytes):
        frame[30, 10 + i * 10:10 + i * 10 + 10, 2] = byte_val

    checksum = hashlib.sha256(data).hexdigest()[:16]
    for i, hex_char in enumerate(checksum):
        hex_val = int(hex_char, 16)
        frame[50, 10 + i * 10:10 + i * 10 + 10, :] = hex_val * 16

    frame[127, :, 0] = 255  # Red separator line

    # ===== PRIMARY ENCODING (Rows 128-3839) =====
    primary_start_row = 128
    primary_end_row = 3840
    primary_height = primary_end_row - primary_start_row

    encoded_byte_idx = 0
    for byte_val in data:
        # Find next valid Hilbert position
        while True:
            x, y = hilbert_d2xy(frame_size, encoded_byte_idx)
            y += primary_start_row

            if y >= primary_end_row or x >= frame_size:
                encoded_byte_idx += 1
                if encoded_byte_idx >= primary_height * frame_size:
                    break
                continue

            # Valid position found - encode byte
            frame[y, x, 0] = byte_val
            encoded_byte_idx += 1
            break

        if encoded_byte_idx >= primary_height * frame_size:
            # Frame full
            break

    frame[3839, :, 1] = 255  # Green separator line

    # ===== FOOTER (Rows 3968-4095) =====
    footer_data = data[:10240]  # First 10KB
    ascii85_data = encode_ascii85(footer_data)

    footer_start_row = 3968
    footer_end_row = 4095

    for char_idx, char_val in enumerate(ascii85_data):
        row = footer_start_row + (char_idx // frame_size)
        col = char_idx % frame_size

        if row <= footer_end_row and col < frame_size:
            frame[row, col, 0] = char_val
            frame[row, col, 1] = char_val
            frame[row, col, 2] = char_val

    frame[3967, :, 2] = 255  # Blue separator line

    # ===== QR CODE ZONE (Rows 3840-3967) =====
    # Add scannable QR codes with frame metadata for human verification
    frame = add_qr_zone_to_frame(
        frame=frame,
        frame_idx=frame_idx,
        sector_start=sector_start,
        sector_end=sector_end,
        data=data,
        total_frames=total_frames,
        frame_size=frame_size
    )

    return frame


def create_directory_frame(filesystem_info, frame_size=4096):
    """Create frame 0 as a printable directory of the entire filesystem."""
    frame = np.zeros((frame_size, frame_size, 3), dtype=np.uint8)

    magic = b"VSP1"
    for i, byte_val in enumerate(magic):
        frame[10, 10 + i * 10, 0] = byte_val

    fs_json = json.dumps(filesystem_info, indent=2).encode('utf-8')

    for byte_idx, byte_val in enumerate(fs_json[:200000]):
        row = 200 + (byte_idx // frame_size)
        col = byte_idx % frame_size
        if row < frame_size and col < frame_size:
            frame[row, col, 0] = byte_val
            frame[row, col, 1] = byte_val
            frame[row, col, 2] = byte_val

    checksum = hashlib.sha256(fs_json).hexdigest()[:16]
    for i, hex_char in enumerate(checksum):
        hex_val = int(hex_char, 16)
        frame[50, 500 + i * 10:500 + i * 10 + 10, :] = hex_val * 16

    return frame


def create_test_disk(output_path="test_printable_disk.npy", size_mb=10):
    """
    Create a test disk image with printable spatial encoding.

    Args:
        output_path: Output path for the test disk
        size_mb: Size in megabytes
    """
    print(f"Creating printable test disk: {size_mb} MB")
    print(f"Output: {output_path}")

    # Create test data
    disk_data = b"Test disk for printable spatial encoding. " * (size_mb * 1024 * 1024 // 48)
    disk_data = disk_data[:size_mb * 1024 * 1024]  # Exact size

    print(f"Disk data size: {len(disk_data):,} bytes ({len(disk_data) / (1024**2):.2f} MB)")
    print(f"SHA256: {hashlib.sha256(disk_data).hexdigest()[:32]}...")

    # Calculate frames needed
    # Each frame holds bytes_per_frame in the primary (Hilbert) area
    bytes_per_frame = (3840 - 128) * 4096  # Rows 128-3839 × 4096 columns
    sector_size = 512
    total_sectors = (len(disk_data) + sector_size - 1) // sector_size

    # Calculate how many data frames we need (excluding directory frame)
    data_frames_needed = max(1, (len(disk_data) + bytes_per_frame - 1) // bytes_per_frame)
    frames_needed = data_frames_needed + 1  # +1 for directory frame (frame 0)

    print(f"Total bytes: {len(disk_data):,}")
    print(f"Total sectors: {total_sectors:,}")
    print(f"Bytes per frame (primary): {bytes_per_frame:,} ({bytes_per_frame / (1024**2):.2f} MB)")
    print(f"Data frames needed: {data_frames_needed}")
    print(f"Total frames (including directory): {frames_needed}")

    # Create filesystem info for directory frame
    fs_info = {
        "magic": "VSP1",
        "version": 1,
        "filesystem": {
            "type": "ext4",
            "size": f"{size_mb}MB",
            "sectors": total_sectors,
            "bytes": len(disk_data)
        },
        "partitions": [
            {
                "number": 1,
                "type": "ext4",
                "start": 2048,
                "end": total_sectors,
                "label": "root"
            }
        ],
        "critical_files": [
            {"path": "/boot/vmlinuz", "sectors": "4096-8191", "frame": 1},
            {"path": "/boot/initrd.img", "sectors": "8192-12287", "frame": 2},
            {"path": "/etc/fstab", "sectors": "12800-13000", "frame": 3}
        ],
        "frames": {
            "total": frames_needed,
            "directory_frame": 0,
            "data_frames": data_frames_needed
        },
        "encoding": {
            "primary": "Hilbert curve RGB24",
            "qr_zone": "Scannable metadata (rows 3840-3967)",
            "recovery": "Ascii85 text",
            "frame_size": "4096x4096",
            "bytes_per_frame": bytes_per_frame
        }
    }

    # Create directory frame
    print("\n[1] Creating directory frame (frame 0)...")
    dir_frame = create_directory_frame(fs_info)

    # Create data frames
    print(f"\n[2] Creating {frames_needed - 1} data frames...")
    frames = [dir_frame]

    for frame_idx in range(1, frames_needed):
        byte_start = (frame_idx - 1) * bytes_per_frame
        byte_end = min(byte_start + bytes_per_frame, len(disk_data))

        frame_data = disk_data[byte_start:byte_end]

        # Calculate virtual sector numbers for metadata
        sector_start = byte_start // sector_size
        sector_end = byte_end // sector_size

        frame = create_printable_frame(
            frame_idx=frame_idx,
            sector_start=sector_start,
            sector_end=sector_end,
            data=frame_data,
            total_frames=frames_needed
        )
        frames.append(frame)

        if frame_idx % 20 == 0:
            print(f"  Frame {frame_idx}/{frames_needed - 1} (bytes {byte_start:,}-{byte_end:,})")

    # Save all frames as a structured array
    print(f"\n[3] Saving test disk to {output_path}...")
    frames_array = np.array(frames)
    np.save(output_path, frames_array)
    print(f"  ✓ Saved {len(frames)} frames")

    # Save metadata
    metadata_path = output_path.replace('.npy', '.meta.json')
    with open(metadata_path, 'w') as f:
        json.dump({
            "version": "1.0",
            "encoding": "printable-spatial",
            "frames": len(frames),
            "frame_size": [4096, 4096, 3],
            "total_bytes": len(disk_data),
            "sha256": hashlib.sha256(disk_data).hexdigest(),
            "filesystem": fs_info
        }, f, indent=2)
    print(f"  ✓ Saved metadata: {metadata_path}")

    # Calculate storage
    storage_bytes = frames_array.nbytes
    print(f"\n[4] Storage Analysis:")
    print(f"  Raw data: {len(disk_data):,} bytes ({len(disk_data) / (1024**2):.2f} MB)")
    print(f"  Storage: {storage_bytes:,} bytes ({storage_bytes / (1024**3):.2f} GB)")
    print(f"  Overhead: +{storage_bytes - len(disk_data):,} bytes ({(storage_bytes / len(disk_data) - 1) * 100:.1f}%)")
    print(f"  Per frame: {storage_bytes / len(frames) / (1024**2):.2f} MB")

    print("\n" + "=" * 70)
    print("✓ Printable test disk creation complete!")
    print("=" * 70)
    print(f"\nCreated {len(frames)} frames with printable encoding:")
    print("  - Frame 0: Directory frame (filesystem metadata)")
    print(f"  - Frames 1-{frames_needed - 1}: Data frames (header + Hilbert + QR + Ascii85)")
    print(f"\nTo load and extract data:")
    print(f"  python3 -c \"import numpy as np; f = np.load('{output_path}'); print(f'Loaded {{len(f)}} frames')\"")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Create printable test disk')
    parser.add_argument('--size', type=int, default=10, help='Size in MB (default: 10)')
    parser.add_argument('--output', type=str, default='test_printable_disk.npy', help='Output path')
    args = parser.parse_args()

    create_test_disk(output_path=args.output, size_mb=args.size)