#!/usr/bin/env python3
"""Verify metadata is actually in the container at expected offset"""

import subprocess
import struct

# Extract metadata offset bytes from container
offset = 4716694251  # Calculated offset
frame_index = 282  # Which frame contains the metadata

# Extract frame 282
cmd = [
    'ffmpeg', '-y',
    '-i', 'ubuntu_cognitive_vac2_v3_full.nut',
    '-vf', f'select=eq(n\\,{frame_index})',
    '-vframes', '1',
    '-f', 'image2pipe',
    '-pix_fmt', 'rgb24',
    '-vcodec', 'rawvideo',
    '-'
]

print(f"Extracting frame {frame_index}...")
proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
frame_data, err = proc.communicate()
print(f"Extracted {len(frame_data)} bytes")

# Extract 1KB from expected metadata offset within frame
frame_offset = 2296555  # From debug output
if frame_offset < len(frame_data):
    chunk = frame_data[frame_offset:frame_offset + 1024]

    # Look for 8-byte length prefix + JSON
    if len(chunk) >= 8:
        meta_len = struct.unpack('<Q', chunk[:8])[0]
        print(f"Found length prefix: {meta_len} bytes")

        if meta_len > 0 and meta_len < 1024:
            json_data = chunk[8:8+meta_len]
            try:
                import json
                meta = json.loads(json_data.decode('utf-8'))
                print("✓ Metadata found!")
                print(json.dumps(meta, indent=2))
            except:
                print("❌ Invalid JSON")
                print(f"Raw bytes: {json_data[:100]}")
        else:
            print(f"❌ Invalid length: {meta_len}")
    else:
        print("❌ Not enough bytes for length prefix")
else:
    print(f"❌ Frame offset {frame_offset} beyond frame size")

# Also check frame 1 (first data frame) for debugging
print("\n=== Checking frame 1 (first data frame) ===")
frame_data_frame1 = subprocess.check_output([
    'ffmpeg', '-y',
    '-i', 'ubuntu_cognitive_vac2_v3_full.nut',
    '-vf', 'select=eq(n\\,1)',
    '-vframes', '1',
    '-f', 'image2pipe',
    '-pix_fmt', 'rgb24',
    '-vcodec', 'rawvideo',
    '-'
], stderr=subprocess.DEVNULL)

# Check for non-zero bytes (would indicate real data)
non_zero_count = sum(1 for b in frame_data_frame1 if b != 0)
print(f"Frame 1: {non_zero_count} non-zero bytes out of {len(frame_data_frame1)}")
print(f"Percentage: {non_zero_count / len(frame_data_frame1) * 100:.1f}%")

# Check if it looks like a disk image (MBR signature at offset 510)
if len(frame_data_frame1) > 510:
    # In BGR24, 3 bytes per pixel, so byte offset 510 is at pixel 170
    pixel_offset = 170
    b = frame_data_frame1[pixel_offset * 3]
    g = frame_data_frame1[pixel_offset * 3 + 1]
    r = frame_data_frame1[pixel_offset * 3 + 2]

    # MBR signature is 0x55 0xAA at bytes 510 and 511
    if b == 0x55 and g == 0xAA:
        print("✓ Found MBR signature in frame 1!")
    else:
        print(f"MBR check: expected 0x55 0xAA, got 0x{b:02x} 0x{g:02x}")