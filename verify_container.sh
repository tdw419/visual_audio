#!/bin/bash
# Quick verification of the newly encoded container

set -e

CONTAINER="ubuntu_cognitive_vac2_v3_full.nut"

echo "=== Container Verification ==="
echo "Container: $CONTAINER"

# Check file size
if [ ! -f "$CONTAINER" ]; then
    echo "❌ Container not found!"
    exit 1
fi

SIZE=$(stat -c%s "$CONTAINER")
echo "File size: $(numfmt --to=iec $SIZE)"

# Verify frame count
FRAMES=$(ffprobe -v error -count_frames -show_entries stream=nb_read_frames -of default=noprint_wrappers=1 "$CONTAINER" 2>/dev/null || echo "N/A")
echo "Frames: $FRAMES"

# Check metadata
if [ -f "$CONTAINER.meta.json" ]; then
    echo ""
    echo "Metadata:"
    cat "$CONTAINER.meta.json"
else
    echo "⚠️  No .meta.json file found"
fi

# Decode first few bytes to verify Hilbert mapping
echo ""
echo "Hilbert decode test (first 64 bytes):"
python3 << 'EOF'
import numpy as np

def hilbert_d2xy(n, d):
    x, y = 0, 0
    s = 1
    t = d
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
    return x, y

def decode_pixel_to_byte(r, g, b):
    id_val = (r << 16) | (g << 8) | b
    SPECIAL_OFFSET = 16
    if id_val >= SPECIAL_OFFSET:
        return id_val - SPECIAL_OFFSET
    return 0

# Read frame 1 (first data frame after metadata)
import subprocess
result = subprocess.run([
    'ffmpeg', '-y', '-loglevel', 'error',
    '-ss', '1', '-i', 'ubuntu_cognitive_vac2_v3_full.nut',
    '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'
], capture_output=True)

if result.returncode == 0 and len(result.stdout) >= 64 * 3:
    data = np.frombuffer(result.stdout[:64*3], dtype=np.uint8).reshape(64, 3)
    decoded = []
    for i in range(64):
        x, y = hilbert_d2xy(4096, i)
        r, g, b = data[i]
        byte = decode_pixel_to_byte(r, g, b)
        decoded.append(byte)
    print("First 64 decoded bytes:", ' '.join(f'{b:02x}' for b in decoded[:16]))
else:
    print("Failed to decode frame")
EOF

echo ""
echo "✓ Verification complete"