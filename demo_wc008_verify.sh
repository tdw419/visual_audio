#!/bin/bash
set -e

cd /home/jericho/projects/zion/projects/visual_audio

echo "=== WC008 Verification: V4 Boot + Screenshot Capture ==="
rm -f /tmp/qemu_serial.log /tmp/qemu_monitor.sock /tmp/qemu_screenshot.ppm

echo "Booting QEMU with NO display (headless) — NO host filesystem passthrough"
qemu-system-x86_64 -m 2G -enable-kvm -cpu host \
    -display none \
    -monitor unix:/tmp/qemu_monitor.sock,server,nowait \
    -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
    -drive if=pflash,format=raw,file=/tmp/my_vars.fd \
    -drive id=bootdisk,format=raw,file=/tmp/ubuntu_v4_efi.img,if=none \
    -device ide-hd,drive=bootdisk,bootindex=1 \
    -drive id=rootdisk,file=/home/jericho/projects/zion/projects/visual_audio/ubuntu-desktop-15g.raw,format=raw,if=none \
    -device virtio-blk-pci,drive=rootdisk,bootindex=2 \
    -net nic -net user,hostfwd=tcp::2222-:22 \
    -serial file:/tmp/qemu_serial.log &
QEMU_PID=$!

echo "QEMU PID: $QEMU_PID"
echo "Waiting for boot (40 seconds)..."
sleep 40

echo "Capturing screenshot..."
printf "screendump /tmp/qemu_screenshot.ppm\n" | nc -U /tmp/qemu_monitor.sock 2>&1 > /dev/null
sleep 2

echo "Shutting down QEMU..."
printf "system_powerdown\n" | nc -U /tmp/qemu_monitor.sock 2>&1 > /dev/null
sleep 5
pkill -9 qemu 2>/dev/null

echo ""
echo "=== VERIFICATION RESULTS ==="
echo "1. Boot log tail (last 20 lines):"
tail -20 /tmp/qemu_serial.log
echo ""
echo "2. Screenshot file:"
ls -lh /tmp/qemu_screenshot.ppm
echo ""
echo "3. Screenshot header (should be P6 format):"
head -3 /tmp/qemu_screenshot.ppm
echo ""
echo "wc008_gui binary is at /opt/geos_pixel/wc008_gui in the guest."
echo "To run it manually, boot with: ./demo_wc008_no_passthrough.sh (VNC) or ./demo_wc008_sdl.sh (SDL)"