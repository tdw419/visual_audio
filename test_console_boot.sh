#!/bin/bash
set -x
pkill -f qemu-system-x86_64 2>/dev/null || true
sleep 0.5

# Boot ubuntu_desktop.qcow2 with serial console to see boot output
# This will show us if the image actually boots or is broken
timeout 20 qemu-system-x86_64 \
    -M pc \
    -m 2048M \
    -enable-kvm \
    -nographic \
    -drive file=boot_images/ubuntu_desktop.qcow2,format=qcow2 \
    2>&1 | head -100

exit 0