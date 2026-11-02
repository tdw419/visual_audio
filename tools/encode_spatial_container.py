#!/usr/bin/env python3
"""
Encode disk images and cognitive payloads into spatial MKV (.nut) containers.

Memory-optimized version: streams frames directly to ffmpeg without holding
entire arrays in RAM.
"""

import argparse
import json
import os
import struct
import subprocess
from pathlib import Path


# Precompute Hilbert LUT for 4096×4096
def precompute_hilbert_lut(n=4096):
    """Precompute Hilbert curve mapping to avoid recomputation."""
    lut = {}
    x, y = 0, 0
    s = 1
    for d in range(n * n):
        t = d
        x, y = 0, 0
        s = 1
        while s < n:
            rx = (t >> 1) & 1
            ry = (t ^ rx) & 1
            if ry == 0:
                if rx == 1:
                    x = s - 1 - x
                    y = s - 1 - y
                x, y = y, x
            x += s * rx
            y += s * ry
            t >>= 2
            s <<= 1
        lut[d] = (x, y)
    return lut


# Global LUT for efficiency
HILBERT_LUT = None


def hilbert_d2xy(n, d):
    """Hilbert curve: map d (0 to n²-1) to (x, y) coordinates."""
    global HILBERT_LUT
    if HILBERT_LUT is None:
        HILBERT_LUT = precompute_hilbert_lut(n)
    return HILBERT_LUT.get(d, (0, 0))


# Encode byte to RGB pixel (Visual Audio encoding)
def byte_to_pixel(byte_val):
    SPECIAL_OFFSET = 16
    id_val = byte_val + SPECIAL_OFFSET
    r = (id_val >> 16) & 0xFF
    g = (id_val >> 8) & 0xFF
    b = id_val & 0xFF
    return r, g, b


import numpy as np

# Load global LUT once
_HILBERT_LUT = None

def encode_bytes_to_frame_stream(data, frame_size=4096, frame_fp=None):
    """
    Encode raw bytes into BGR24 frames using Hilbert curve mapping.
    Streams directly to file using vectorized numpy operations.
    """
    global _HILBERT_LUT
    capacity = frame_size * frame_size
    if len(data) > capacity:
        raise ValueError(f"Data size {len(data)} exceeds frame capacity {capacity}")

    if _HILBERT_LUT is None:
        lut_path = os.path.join(os.path.dirname(__file__), "hilbert_lut_64M.npy")
        if os.path.exists(lut_path):
            _HILBERT_LUT = np.load(lut_path)
        else:
            raise FileNotFoundError(f"Missing {lut_path}. Cannot use fast vectorized encode.")

    # 1. Pad data
    if len(data) < capacity:
        padded = np.zeros(capacity, dtype=np.uint8)
        padded[:len(data)] = np.frombuffer(data, dtype=np.uint8)
    else:
        padded = np.frombuffer(data, dtype=np.uint8)

    # 2. Add SPECIAL_OFFSET (16)
    id_vals = padded.astype(np.uint32) + 16

    # 3. Create flat pixel array (RGB)
    pixels = np.zeros((capacity, 3), dtype=np.uint8)
    pixels[:, 0] = (id_vals >> 16) & 0xFF   # Red
    pixels[:, 1] = (id_vals >> 8) & 0xFF    # Green
    pixels[:, 2] = id_vals & 0xFF           # Blue

    # 4. Map to spatial pixels using Hilbert LUT
    spatial_pixels = np.zeros_like(pixels)
    spatial_pixels[_HILBERT_LUT] = pixels

    # 5. Stream out
    frame_fp.write(spatial_pixels.tobytes())


def write_cognitive_metadata(payload_start, payload_size, initramfs_size, gguf_size):
    """
    Create cognitive_boot.json metadata.

    Returns:
        bytes: 8-byte length prefix + JSON bytes
    """
    metadata = {
        "payload_start": payload_start,
        "payload_size": payload_size,
        "components": {
            "initramfs": {
                "size": initramfs_size,
                "format": "gzip"
            },
            "gguf": {
                "size": gguf_size,
                "format": "gguf_v3 Q4_K_M"
            }
        }
    }

    metadata_json = json.dumps(metadata, separators=(',', ':')).encode('utf-8')
    metadata_len = len(metadata_json)

    # Format: [8-byte length (little endian)] + JSON bytes
    return struct.pack('<Q', metadata_len) + metadata_json


def encode_container(rootfs_path, initramfs_path, gguf_path, output_path):
    """
    Encode Ubuntu rootfs + cognitive payload into spatial MKV container.
    Memory-optimized: streams data without loading everything into RAM.
    """
    FRAME_SIZE = 4096
    FRAME_CAPACITY = FRAME_SIZE * FRAME_SIZE  # 16777216 bytes (16MB per frame)

    # Get file sizes without loading contents
    rootfs_len = os.path.getsize(rootfs_path)
    initramfs_len = os.path.getsize(initramfs_path)
    gguf_len = os.path.getsize(gguf_path)

    print(f"File sizes:")
    print(f"  Rootfs: {rootfs_len / (1024**3):.2f} GB")
    print(f"  Initramfs: {initramfs_len / (1024**2):.2f} MB")
    print(f"  GGUF: {gguf_len / (1024**2):.2f} MB")

    # Calculate frame layout
    rootfs_frames = (rootfs_len + FRAME_CAPACITY - 1) // FRAME_CAPACITY

    # Create cognitive metadata
    metadata_bytes = write_cognitive_metadata(
        payload_start=rootfs_len,
        payload_size=initramfs_len + gguf_len + 256,
        initramfs_size=initramfs_len,
        gguf_size=gguf_len
    )

    cognitive_data = initramfs_len + gguf_len + len(metadata_bytes)
    cognitive_frames = (cognitive_data + FRAME_CAPACITY - 1) // FRAME_CAPACITY

    total_frames = 1 + rootfs_frames + cognitive_frames

    print(f"\nEncoding plan:")
    print(f"  Rootfs frames: {rootfs_frames}")
    print(f"  Cognitive frames: {cognitive_frames}")
    print(f"  Total frames: {total_frames}")
    print(f"  Decoded size: {total_frames * FRAME_CAPACITY / (1024**3):.2f} GB")

    # Start ffmpeg process
    ffmpeg_cmd = [
        'ffmpeg', '-y',
        '-f', 'rawvideo',
        '-pix_fmt', 'rgb24',
        '-s', f'{FRAME_SIZE}x{FRAME_SIZE}',
        '-r', '1',
        '-i', '-',
        '-c:v', 'rawvideo',
        '-f', 'nut',
        output_path
    ]

    proc = subprocess.Popen(
        ffmpeg_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    # Use memoryview to avoid copies
    proc_stdin = proc.stdin

    # Frame 0: Metadata
    print(f"\nEncoding frame 0: metadata ({len(metadata_bytes)} bytes)...")
    metadata_frame_data = bytearray(FRAME_CAPACITY)
    metadata_frame_data[:len(metadata_bytes)] = metadata_bytes
    encode_bytes_to_frame_stream(metadata_frame_data, FRAME_SIZE, proc_stdin)

    # Frames 1-N: Rootfs (stream from disk)
    print(f"\nEncoding frames 1-{rootfs_frames}: rootfs...")
    with open(rootfs_path, 'rb') as rootfs_fp:
        for frame_idx in range(rootfs_frames):
            offset = frame_idx * FRAME_CAPACITY
            rootfs_fp.seek(offset)
            chunk = rootfs_fp.read(FRAME_CAPACITY)
            if len(chunk) < FRAME_CAPACITY:
                # Pad with zeros if needed
                chunk = chunk + bytes(FRAME_CAPACITY - len(chunk))
            encode_bytes_to_frame_stream(chunk, FRAME_SIZE, proc_stdin)
            if (frame_idx + 1) % 10 == 0:
                print(f"  {frame_idx + 1}/{rootfs_frames} frames")

    # Frames N+1-M: Cognitive payload (stream from files)
    print(f"\nEncoding frames {rootfs_frames + 1}-{total_frames - 1}: cognitive payload...")

    # We will read exactly cognitive_data bytes.
    # To easily handle boundaries, we can create a generator that yields bytes.
    def cognitive_stream():
        yield metadata_bytes
        with open(initramfs_path, 'rb') as f:
            while True:
                data = f.read(1024 * 1024)
                if not data: break
                yield data
        with open(gguf_path, 'rb') as f:
            while True:
                data = f.read(1024 * 1024)
                if not data: break
                yield data

    def read_exact(gen, size):
        buf = bytearray()
        while len(buf) < size:
            try:
                chunk = next(gen)
                buf.extend(chunk)
            except StopIteration:
                break
        
        # If we read too much, we need to push back. But since we only need to read in FRAME_CAPACITY chunks, 
        # let's just use a simple stateful reader.
        pass # Handled below by a better class approach

    class ChunkReader:
        def __init__(self):
            self.gen = cognitive_stream()
            self.buffer = bytearray()
        def read(self, size):
            while len(self.buffer) < size:
                try:
                    self.buffer.extend(next(self.gen))
                except StopIteration:
                    break
            res = self.buffer[:size]
            self.buffer = self.buffer[size:]
            return bytes(res)
            
    reader = ChunkReader()

    for frame_idx in range(cognitive_frames):
        chunk = reader.read(FRAME_CAPACITY)
        if len(chunk) < FRAME_CAPACITY:
            chunk = chunk + bytes(FRAME_CAPACITY - len(chunk))
        
        encode_bytes_to_frame_stream(chunk, FRAME_SIZE, proc_stdin)
        if (frame_idx + 1) % 5 == 0:
            print(f"  {frame_idx + 1}/{cognitive_frames} frames")

    # Let communicate() handle closing stdin to avoid ValueError in Python 3.12
    stdout, stderr = proc.communicate()

    if proc.returncode != 0:
        print(f"FFmpeg error: {stderr.decode('utf-8')}")
        raise RuntimeError("FFmpeg encoding failed")

    print(f"\n✓ Encoding complete: {output_path}")

    # Write metadata JSON for backend
    meta_path = Path(output_path).with_suffix('.nut.meta.json')
    meta = {
        "frames": total_frames,
        "bytes_per_frame": FRAME_CAPACITY,
        "disk_size": total_frames * FRAME_CAPACITY,
        "rootfs_frames": rootfs_frames,
        "cognitive_frames": cognitive_frames,
        "rootfs_bytes": rootfs_len,
        "cognitive_bytes": cognitive_data
    }
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)
    print(f"✓ Metadata written: {meta_path}")


def main():
    parser = argparse.ArgumentParser(description='Encode spatial MKV containers for cognitive boot')
    parser.add_argument('rootfs', help='Rootfs disk image (raw format)')
    parser.add_argument('initramfs', help='Cognitive initramfs (gz)')
    parser.add_argument('gguf', help='LLM weights (GGUF)')
    parser.add_argument('output', help='Output .nut file')
    args = parser.parse_args()

    encode_container(args.rootfs, args.initramfs, args.gguf, args.output)


if __name__ == '__main__':
    main()