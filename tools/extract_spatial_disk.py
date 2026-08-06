#!/usr/bin/env python3
"""
Extract spatial disk from MKV to raw image for NBD boot.

This script decodes the Hilbert-curve encoded spatial storage back to
a raw disk image that can be served via qemu-nbd.

Usage:
    python3 extract_spatial_disk.py alpine_minimal.mkv /tmp/alpine_minimal.raw
"""

import sys
import os
import struct
import json
import subprocess
import tempfile
import numpy as np
from PIL import Image


def hilbert_d2xy(n, d):
    """Convert Hilbert index d to (x, y) coordinates on n×n grid."""
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


def extract_frames_from_mkv(mkv_path, output_dir):
    """Extract frames from MKV using ffmpeg."""
    print(f"Extracting frames from MKV: {mkv_path}")

    # Get frame count
    probe_cmd = [
        'ffprobe', '-v', 'error',
        '-select_streams', 'v:0',
        '-count_frames',
        '-show_entries', 'stream=nb_read_frames',
        '-of', 'csv=p=0',
        mkv_path
    ]
    result = subprocess.run(probe_cmd, capture_output=True, text=True)
    frame_count = int(result.stdout.strip())
    print(f"  Frame count: {frame_count}")

    # Extract frames (0-indexed, vsync vfr for proper frame numbering)
    extract_cmd = [
        'ffmpeg', '-y',
        '-i', mkv_path,
        '-vsync', 'vfr',
        '-start_number', '0',
        f'{output_dir}/frame_%06d.png'
    ]
    subprocess.run(extract_cmd, capture_output=True, check=True)

    frames = []
    for i in range(frame_count):
        frame_path = os.path.join(output_dir, f'frame_{i:06d}.png')
        if not os.path.exists(frame_path):
            print(f"  WARNING: Frame {i} not found at {frame_path}")
            continue
        img = Image.open(frame_path)
        arr = np.array(img)
        frames.append(arr)
        os.remove(frame_path)

    print(f"  ✓ Extracted {len(frames)} frames")
    return frames


def decode_hilbert_to_bytes(frames, disk_size):
    """
    Decode Hilbert-encoded frames back to raw disk bytes.

    Frame layout (from disk_to_printable.py):
    - Rows 0-127: Header (metadata)
    - Rows 128-3839: Primary data (Hilbert encoding)
    - Rows 3840-3967: QR zone (reserved)
    - Rows 3968-4095: Footer (Ascii85 recovery)

    Hilbert encoding stores bytes in R channel only.
    """
    print(f"Decoding Hilbert encoding to {disk_size} bytes...")

    primary_start_row = 128
    grid_size = 4096

    # Calculate how many bytes we need
    num_bytes = disk_size
    output = bytearray(num_bytes)

    byte_idx = 0
    for frame_idx, frame in enumerate(frames):
        if byte_idx >= num_bytes:
            break

        print(f"  Frame {frame_idx + 1}/{len(frames)}...", end='\r')

        for hilbert_idx in range(0, (3840 - 128) * 4096):  # Primary region size
            if byte_idx >= num_bytes:
                break

            x, y = hilbert_d2xy(grid_size, hilbert_idx)
            y += primary_start_row

            # Read byte from R channel (pixel values 0-255)
            if y < frame.shape[0] and x < frame.shape[1]:
                output[byte_idx] = frame[y, x, 0]
                byte_idx += 1

    print(f"\n  ✓ Decoded {byte_idx} bytes")
    return bytes(output)


def load_meta(meta_path):
    """Load metadata JSON."""
    if os.path.exists(meta_path):
        with open(meta_path, 'r') as f:
            return json.load(f)
    return {}


def main():
    if len(sys.argv) < 3:
        print("Usage: extract_spatial_disk.py <mkv_path> <output_raw_path>")
        print("Example: extract_spatial_disk.py alpine_minimal.mkv /tmp/alpine_minimal.raw")
        sys.exit(1)

    mkv_path = sys.argv[1]
    output_path = sys.argv[2]

    # Load metadata
    meta_path = mkv_path + '.meta.json'
    meta = load_meta(meta_path)
    disk_size = meta.get('disk_size', 3145728)  # Default 3MB
    source = meta.get('source_image', 'unknown')

    print("=" * 70)
    print("Spatial Disk Extraction")
    print("=" * 70)
    print(f"MKV:    {mkv_path}")
    print(f"Output: {output_path}")
    print(f"Size:   {disk_size} bytes ({disk_size / (1024*1024):.2f} MB)")
    print(f"Source: {source}")
    print("")

    # Extract frames from MKV
    with tempfile.TemporaryDirectory() as temp_dir:
        frames = extract_frames_from_mkv(mkv_path, temp_dir)

        # Decode Hilbert encoding
        disk_bytes = decode_hilbert_to_bytes(frames, disk_size)

    # Write raw disk image
    with open(output_path, 'wb') as f:
        f.write(disk_bytes)

    print("")
    print("=" * 70)
    print("Extraction Complete")
    print("=" * 70)
    print(f"Output: {output_path}")
    print(f"Size:   {len(disk_bytes)} bytes")

    # Verify MBR signature
    if len(disk_bytes) >= 512:
        mbr_sig = disk_bytes[510:512].hex()
        expected = '55aa'
        if mbr_sig == expected:
            print(f"MBR:    Valid ({mbr_sig}) ✓")
        else:
            print(f"MBR:    Invalid ({mbr_sig}, expected {expected}) ✗")

    print("")
    print("Ready to boot via NBD:")
    print(f"  qemu-nbd --socket=/tmp/spatial-nbd.sock --format=raw {output_path}")
    print("  qemu-system-riscv64 -drive file=nbd+unix:///tmp/spatial-nbd.sock,if=virtio ...")


if __name__ == '__main__':
    main()