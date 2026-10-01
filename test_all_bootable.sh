#!/bin/bash
set -x

echo "=== Testing arch_desktop.qcow2 ==="
pkill -f qemu-system-x86_64 2>/dev/null || true
sleep 0.5

timeout 20 qemu-system-x86_64 \
    -M pc \
    -m 2048M \
    -enable-kvm \
    -nographic \
    -drive file=boot_images/arch_desktop.qcow2,format=qcow2 \
    2>&1 | head -100

echo ""
echo "=== Testing ubuntu-24.04-desktop.qcow2 with OVMF ==="
pkill -f qemu-system-x86_64 2>/dev/null || true
sleep 0.5

timeout 20 qemu-system-x86_64 \
    -M pc \
    -m 2048M \
    -enable-kvm \
    -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
    -drive if=pflash,format=raw,file=/usr/share/OVMF/OVMF_VARS_4M.fd \
    -drive file=boot_images/ubuntu-24.04-desktop.qcow2,format=qcow2 \
    -nographic \
    2>&1 | head -100

exit 0