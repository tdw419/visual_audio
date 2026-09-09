#!/bin/bash
# Test the infinite map + VNC streaming pipeline

set -e

echo "[1/4] Checking if VM is running..."
if ! pgrep -f "qemu-system.*pixel_ubuntu" > /dev/null; then
    echo "[!] VM not running. Start it with: ./pixel_ubuntu.sh"
    exit 1
fi
echo "[+] VM is running"

echo "[2/4] Checking VNC server..."
if ! netstat -tln 2>/dev/null | grep -q ":5901 "; then
    echo "[!] VNC not listening on :5901"
    exit 1
fi
echo "[+] VNC listening on :5901"

echo "[3/4] Checking if compositor is running..."
if ! pgrep -f "infinite_map_rs" > /dev/null; then
    echo "[!] Compositor not running. Start it with:"
    echo "    cd systems/infinite_map_rs && cargo run --release"
    exit 1
fi
echo "[+] Compositor is running"

echo "[4/4] Starting VNC streamer..."
cd systems/infinite_map_rs
chmod +x vnc_streamer.py
./vnc_streamer.py