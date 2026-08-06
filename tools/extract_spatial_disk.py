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
        # Handle both grayscale (2D) and RGB (3D) formats
        if arr.ndim == 2:
            arr = arr[:, :, np.newaxis]  # Add channel dimension
        frames.append(arr)
        os.remove(frame_path)

    print(f"  ✓ Extracted {len(frames)} frames")
    return frames


def decode_pixel_to_byte(r: int, g: int, b: int) -> int:
    """Decode RGB pixel to byte (matching Rust lib.rs decode_pixel_to_byte)"""
    SPECIAL_OFFSET = 16
    id_val = (r << 16) | (g << 8) | b
    if id_val >= SPECIAL_OFFSET:
        # Result may exceed 255 for corrupted data, cap at 255
        return min((id_val - SPECIAL_OFFSET) & 0xFF, 255)
    return 0  # Padding pixel


def decode_hilbert_to_bytes(frames, disk_size):
    """
    Decode Hilbert-encoded frames back to raw disk bytes.

    For vectorized-encoder MKVs (encoder: "vectorized"):
    - Frame 0: Directory frame (skip - metadata only)
    - Frame 1+: Data frames with Hilbert encoding in rows 128-3839
    - Each byte encoded as RGB triplet: id = (R<<16)|(G<<8)|B, byte = id - 16

    For scalar-encoder MKVs (no "encoder" field or encoder: "scalar"):
    - Each byte stored at hilbert_d2xy(grid_size, byte_idx) in primary region
    - Uses single channel (grayscale)
    """
    print(f"Decoding Hilbert encoding to {disk_size} bytes...")

    primary_start_row = 128
    primary_end_row = 3840
    grid_size = 4096

    output = bytearray(disk_size)
    byte_idx = 0

    for frame_idx, frame in enumerate(frames):
        if byte_idx >= disk_size:
            break

        print(f"  Frame {frame_idx + 1}/{len(frames)}...", end='\r')

        # Frame 0 is directory frame (metadata only, skip data decode)
        if frame_idx == 0:
            print(f"\n  Frame 0: Directory frame (metadata only, skipping)")
            continue

        # Detect encoding type from metadata or fallback to checking the Red channel
        # Vectorized format uses (byte + 16), so R is 0 (id >> 16) and G is 0 or 1 (id >> 8)
        # We can't easily guess it by looking at the green channel alone.
        # But we know new MKVs use it.
        # Let's check if the directory frame has encoding='decode_pixel_to_byte'
        is_vectorized = True # We force vectorized for now since that's what the Rust backend uses

        if is_vectorized:
            # Vectorized encoding: bytes stored as RGB triplets across primary region
            # Primary region: rows 128-3839 (3712 rows), columns 0-4095 (4096 cols)
            primary_region = frame[primary_start_row:primary_end_row, :, :]
            flat_pixels = primary_region.reshape(-1, 3)  # (N, 3) array of RGB pixels

            for r, g, b in flat_pixels:
                if byte_idx >= disk_size:
                    break
                output[byte_idx] = decode_pixel_to_byte(int(r), int(g), int(b))
                byte_idx += 1
        else:
            # Scalar encoding: each byte at sequential Hilbert index
            for hilbert_idx in range(0, (primary_end_row - primary_start_row) * grid_size):
                if byte_idx >= disk_size:
                    break

                x, y = hilbert_d2xy(grid_size, hilbert_idx)
                y += primary_start_row

                if y < primary_end_row and x < grid_size:
                    output[byte_idx] = frame[y, x, 0]
                    byte_idx += 1

    print(f"\n  ✓ Decoded {byte_idx} bytes")
    return bytes(output)


def load_meta(mkv_path):
    """Load metadata JSON from .meta.json file."""
    # Try .meta.json appended to mkv_path first
    meta_path = mkv_path + '.meta.json'
    if os.path.exists(meta_path):
        with open(meta_path, 'r') as f:
            return json.load(f)

    # Try replacing .mkv with .meta.json
    if mkv_path.endswith('.mkv'):
        meta_path = mkv_path[:-4] + '.meta.json'
        if os.path.exists(meta_path):
            with open(meta_path, 'r') as f:
                return json.load(f)

    return None


def main():
    if len(sys.argv) < 3:
        print("Usage: extract_spatial_disk.py <mkv_path> <output_raw_path>")
        print("Example: extract_spatial_disk.py alpine_minimal.mkv /tmp/alpine_minimal.raw")
        sys.exit(1)

    mkv_path = sys.argv[1]
    output_path = sys.argv[2]

    # Load metadata to get correct disk size
    meta = load_meta(mkv_path)
    if meta and 'disk_size' in meta:
        disk_size = meta['disk_size']
        source = meta.get('source_image', 'unknown')
    else:
        # Fallback: default 3MB
        disk_size = 3145728
        source = 'unknown (no metadata)'
        print(f"Warning: No metadata found, using default size {disk_size} bytes")

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