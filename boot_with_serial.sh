#!/bin/bash
set -x

pkill -f qemu-system-x86_64 2>/dev/null || true
sleep 0.5

# Boot with serial console captured to see where it gets stuck
qemu-system-x86_64 \
    -M pc \
    -m 2048M \
    -enable-kvm \
    -vnc :1 \
    -device virtio-vga \
    -usb \
    -device usb-tablet \
    -drive file=boot_images/arch_desktop.qcow2,format=qcow2,snapshot=on \
    -serial file:/tmp/qemu_serial.log \
    -daemonize

QEMU_PID=$!
echo "QEMU PID: $QEMU_PID"

# Wait for boot
sleep 60

# Show serial output
echo "=== Serial output ==="
tail -100 /tmp/qemu_serial.log

# Show process state
echo "=== Process state ==="
ps aux | grep $QEMU_PID | grep -v grep

# Test VNC
echo "=== Testing VNC ==="
python3 test_vnc.py || true

# Cleanup
kill $QEMU_PID 2>/dev/null

exit 0