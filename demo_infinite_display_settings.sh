#!/bin/bash
# Infinite Display Adapter setup
echo "Creating infinite virtual canvas (8192x4096)..."
xrandr --newmode "8192x4096_30.00"  1423.00  8192 8792 9672 11152  4096 4099 4104 4255 -hsync +vsync
xrandr --addmode Virtual-1 "8192x4096_30.00" || true
xrandr --output Virtual-1 --mode "8192x4096_30.00" --panning 8192x4096 || echo "Could not set output Virtual-1. If using QEMU with -vga std, you may be limited to standard resolutions."

echo "Canvas created. Try panning by pushing your mouse to the edge of the window."
