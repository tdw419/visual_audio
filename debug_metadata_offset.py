#!/usr/bin/env python3
"""Debug metadata offset calculation"""

import struct
import json

# From encoder output
rootfs_len = 3758096384  # 3.5 GB (224 frames * 16MB)
initramfs_len = 289738492  # 276.36 MB
gguf_len = 668859375  # 637.81 MB
FRAME_CAPACITY = 16777216  # 16MB

# Create metadata (same as encoder)
metadata_json = json.dumps({
    "payload_start": rootfs_len,
    "payload_size": initramfs_len + gguf_len + 256,
    "components": {
        "initramfs": {"size": initramfs_len, "format": "gzip"},
        "gguf": {"size": gguf_len, "format": "GGUF Q4_K_M"}
    }
}, separators=(',', ':')).encode('utf-8')
metadata_len = len(metadata_json)
metadata_bytes = struct.pack('<Q', metadata_len) + metadata_json

print(f"=== Metadata Debug ===")
print(f"Metadata JSON: {metadata_json.decode('utf-8')}")
print(f"Metadata length: {metadata_len} bytes")
print(f"Total metadata bytes: {len(metadata_bytes)} (8-byte prefix + JSON)")
print()

# Cognitive payload layout
cognitive_start_frame = 224  # Frame 225 is first cognitive frame
cognitive_offset_in_payload = initramfs_len + gguf_len
absolute_metadata_offset = rootfs_len + cognitive_offset_in_payload

print(f"=== Offset Calculation ===")
print(f"Rootfs: {rootfs_len} bytes ({rootfs_len / (1024**3):.2f} GB)")
print(f"  → Frames 1-224 (224 frames)")
print(f"Cognitive start: frame 225 at offset {rootfs_len}")
print(f"  Initramfs: {initramfs_len / (1024**2):.2f} MB")
print(f"  GGUF: {gguf_len / (1024**2):.2f} MB")
print(f"  Metadata offset within cognitive: {cognitive_offset_in_payload} bytes")
print(f"Absolute metadata offset: {absolute_metadata_offset} bytes ({absolute_metadata_offset / (1024**3):.2f} GB)")
print()

# Calculate which frame and offset
metadata_frame_index = (absolute_metadata_offset // FRAME_CAPACITY) + 1  # +1 for frame 0 metadata
metadata_frame_offset = absolute_metadata_offset % FRAME_CAPACITY

print(f"=== Metadata Location ===")
print(f"Target frame: {metadata_frame_index} (frame {metadata_frame_index} of {283})")
print(f"Target offset within frame: {metadata_frame_offset} bytes")
print()

# What initramfs expects
initramfs_offset = 3758096384  # Hardcoded in initramfs-cognitive/init
print(f"=== What Initramfs Expects ===")
print(f"Hardcoded offset: {initramfs_offset} bytes")
print(f"Difference: {absolute_metadata_offset - initramfs_offset} bytes")
print()

if absolute_metadata_offset != initramfs_offset:
    print("❌ OFFSET MISMATCH!")
    print(f"   Initramfs will scan at {initramfs_offset}")
    print(f"   But metadata is at {absolute_metadata_offset}")
    print(f"   Gap: {(absolute_metadata_offset - initramfs_offset) / (1024**2):.2f} MB")
else:
    print("✓ Offsets match!")