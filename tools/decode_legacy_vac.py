#!/usr/bin/env python3
"""
Decode legacy VAC2/VAC3 spatial containers (.nut files) to extract raw sections.

This extracts the original byte data from the Hilbert-mapped, BGR24-encoded frames.
"""
import argparse
import json
import struct
import numpy as np
import subprocess
import os
from pathlib import Path

# Hilbert curve LUT path (assuming precomputed)
HILBERT_LUT_PATH = Path(__file__).parent.parent / "hilbert_lut_64M.npy"

def load_hilbert_lut():
    """Load precomputed Hilbert curve mapping."""
    if not HILBERT_LUT_PATH.exists():
        raise FileNotFoundError(f"Missing {HILBERT_LUT_PATH}. Run encode_spatial_container.py first to generate it.")
    return np.load(HILBERT_LUT_PATH)

def decode_frame_to_bytes(raw_bytes, hilbert_lut):
    """
    Decode raw BGR24 bytes back to original byte data using Hilbert mapping.
    
    Args:
        raw_bytes: Raw frame data (RGB24 from ffmpeg output)
        hilbert_lut: Precomputed Hilbert LUT for reversing the spatial mapping
    
    Returns:
        bytes: Decoded original data
    """
    FRAME_SIZE = 4096
    capacity = FRAME_SIZE * FRAME_SIZE
    
    # Parse RGB24 bytes into pixels
    # Note: ffmpeg RGB24 is actually BGR in memory for rawvideo
    pixels = np.frombuffer(raw_bytes, dtype=np.uint8).reshape((capacity, 3))
    
    # Reverse Hilbert mapping
    # The LUT maps: spatial_index -> (x, y) in frame
    # We need to reverse: frame data -> original linear order
    # So we inverse-index using the LUT
    original_pixels = pixels[hilbert_lut]
    
    # Decode BGR pixel back to byte (reverse of byte_to_pixel)
    # byte = (r << 16) | (g << 8) | b - SPECIAL_OFFSET
    SPECIAL_OFFSET = 16
    b = original_pixels[:, 0]
    g = original_pixels[:, 1]  
    r = original_pixels[:, 2]
    
    id_vals = (r.astype(np.uint32) << 16) | (g.astype(np.uint32) << 8) | b.astype(np.uint32)
    byte_vals = (id_vals - SPECIAL_OFFSET).astype(np.uint8)
    
    return byte_vals.tobytes()

def extract_metadata(frame_data):
    """Extract metadata from frame 0."""
    # Frame 0: [8-byte length] + JSON + padding
    # Need to decode frame 0 first
    hilbert_lut = load_hilbert_lut()
    decoded_frame = decode_frame_to_bytes(frame_data, hilbert_lut)
    
    # Read 8-byte length prefix
    if len(decoded_frame) < 8:
        raise ValueError("Frame 0 too small to contain metadata length")
    
    metadata_len = struct.unpack('<Q', decoded_frame[:8])[0]
    
    # Sanity check
    if metadata_len <= 0 or metadata_len > 1024 * 1024:
        raise ValueError(f"Invalid metadata length: {metadata_len}")
    
    metadata_json = decoded_frame[8:8+metadata_len].decode('utf-8')
    metadata = json.loads(metadata_json)
    
    return metadata

def main():
    parser = argparse.ArgumentParser(description='Decode legacy VAC2/VAC3 spatial containers')
    parser.add_argument('container', help='Path to .nut container file')
    parser.add_argument('--output-dir', default='/tmp/vac_extract', help='Output directory for extracted sections')
    args = parser.parse_args()
    
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)
    
    print(f"Extracting from: {args.container}")
    print(f"Output directory: {output_dir}")
    
    # Extract frame 0 to get metadata
    print("\nExtracting frame 0 (metadata)...")
    frame0_path = output_dir / "frame_00000.raw"
    
    # Use ffmpeg to extract frame 0 as raw bytes
    cmd = [
        'ffmpeg', '-y', '-i', args.container,
        '-vf', 'select=eq(n\,0)',
        '-frames:v', '1',
        '-f', 'rawvideo', '-pix_fmt', 'rgb24',
        str(frame0_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"FFmpeg error: {result.stderr}")
        raise RuntimeError("Failed to extract frame 0")
    
    with open(frame0_path, 'rb') as f:
        frame0_data = f.read()
    
    print(f"Frame 0 size: {len(frame0_data)} bytes")
    
    # Decode and extract metadata
    metadata = extract_metadata(frame0_data)
    print(f"\nMetadata: {json.dumps(metadata, indent=2)}")
    
    # Calculate frame layout from metadata
    FRAME_CAPACITY = 4096 * 4096  # 16MB
    
    rootfs_len = metadata.get('components', {}).get('rootfs', {}).get('size', 0)
    initramfs_len = metadata.get('components', {}).get('initramfs', {}).get('size', 0)
    gguf_len = metadata.get('components', {}).get('gguf', {}).get('size', 0)
    payload_start = metadata.get('payload_start', 0)
    
    print(f"\nSection sizes:")
    print(f"  Rootfs: {rootfs_len / (1024**3):.2f} GB")
    print(f"  Initramfs: {initramfs_len / (1024**2):.2f} MB")
    print(f"  GGUF: {gguf_len / (1024**2):.2f} MB")
    print(f"  Payload start: {payload_start / (1024**3):.2f} GB")
    
    # Calculate frames
    rootfs_frames = (rootfs_len + FRAME_CAPACITY - 1) // FRAME_CAPACITY
    print(f"\nRootfs frames: {rootfs_frames}")
    
    print("\nExtraction complete!")
    print(f"Metadata saved to: {output_dir / 'metadata.json'}")
    
    # Save metadata for reference
    with open(output_dir / 'metadata.json', 'w') as f:
        json.dump(metadata, f, indent=2)

if __name__ == '__main__':
    main()