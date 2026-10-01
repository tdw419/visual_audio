#!/usr/bin/env python3
"""Create minimal test container for VirtIO-Pixel"""

import subprocess
import struct
import os

# Create tiny test data (1MB of zeroes)
test_data = b'\x00' * (1024 * 1024)

# Encode using existing tools
# For now, just create a simple MKV with 1 frame
cmd = [
    'ffmpeg', '-y',
    '-f', 'rawvideo',
    '-pix_fmt', 'rgb24',
    '-s', '1024x1024',
    '-i', '/dev/zero',  # Black pixels (padding)
    '-frames:v', '1',   # Hard stop at 1 frame — without this, ffmpeg encodes
                        # /dev/zero forever and fills /tmp (7GB incident 2026-09-08)
    '-c:v', 'rawvideo',
    '-f', 'nut',
    '/tmp/tiny_test.nut'
]

print(f"Running: {' '.join(cmd)}")
subprocess.run(cmd, check=True)

# Get size
size = os.path.getsize('/tmp/tiny_test.nut')
print(f"Created /tmp/tiny_test.nut ({size:,} bytes)")

# Create meta.json
meta = {
    "frames": 1,
    "bytes_per_frame": 1024*1024,
    "disk_size": 1024*1024,
    "rootfs_frames": 1,
    "cognitive_frames": 0
}

import json
with open('/tmp/tiny_test.nut.meta.json', 'w') as f:
    json.dump(meta, f, indent=2)

print(f"Created /tmp/tiny_test.nut.meta.json")
print("\nTest with:")
print(f"  ./systems/virtio_pixel_rs/target/release/virtio_pixel_backend /tmp/tiny_test.nut /tmp/test.sock")