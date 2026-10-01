#!/bin/bash
# Infinite virtual canvas for Ubuntu VM - autodetects output name

set -e

echo "[*] Detecting connected display output..."
OUTPUT=$(xrandr | grep " connected" | awk '{print $1}')

if [ -z "$OUTPUT" ]; then
    echo "[!] No connected display found"
    exit 1
fi

echo "[+] Found output: $OUTPUT"

# Check if mode already exists
if xrandr | grep -q "8192x4096_30.00"; then
    echo "[*] Mode 8192x4096_30.00 already exists"
else
    echo "[*] Creating 8192x4096 virtual mode..."
    xrandr --newmode "8192x4096_30.00"  1423.00  8192 8792 9672 11152  4096 4099 4104 4255 -hsync +vsync
    xrandr --addmode $OUTPUT "8192x4096_30.00"
fi

echo "[*] Applying mode with panning..."
xrandr --output $OUTPUT --mode "8192x4096_30.00" --panning 8192x4096

echo ""
echo "[+] Infinite canvas enabled!"
echo "    Virtual resolution: 8192 x 4096"
echo "    Push mouse to edges to pan the viewport"
echo "    Run 'xrandr --output $OUTPUT --auto' to disable"