#!/bin/bash
set -e

# Quick test of V4 bootloader with Ubuntu rootfs
QEMU_SERIAL="/tmp/qemu_v4_ubuntu_test.log"
V4_DISK="/tmp/ubuntu_v4_efi.img"
UBUNTU_ROOTFS="/home/jericho/projects/zion/projects/visual_audio/ubuntu-24.04-server-cloudimg-amd64.raw"
VARS_FD="/tmp/my_vars_test.fd"

# Create UEFI vars file if needed
if [ ! -f "$VARS_FD" ]; then
    dd if=/dev/zero of="$VARS_FD" bs=1M count=4 2>/dev/null
fi

# Clear previous log
rm -f "$QEMU_SERIAL"

echo "Testing V4 bootloader with Ubuntu rootfs attached..."
echo ""

# Boot QEMU for 30 seconds to see what happens
timeout 30 qemu-system-x86_64 \
    -m 1G \
    -enable-kvm \
    -cpu host \
    -display none \
    -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
    -drive if=pflash,format=raw,file="$VARS_FD" \
    -drive format=raw,file="$V4_DISK",if=virtio \
    -drive format=raw,file="$UBUNTU_ROOTFS",if=virtio \
    -serial file:"$QEMU_SERIAL" \
    -no-reboot 2>&1 || true

echo ""
echo "=== Serial Output (last 50 lines) ==="
tail -50 "$QEMU_SERIAL" 2>/dev/null || echo "No serial output found"
echo ""
echo "=== Full log saved to $QEMU_SERIAL ==="