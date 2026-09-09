#!/bin/bash
set -ex

# QEMU boot script for V4 bootloader with Ubuntu rootfs
# This boots the kernel+initramfs from the PDB/V4 boot disk,
# then the initramfs finds and boots the Ubuntu rootfs from /dev/vdb

QEMU_SERIAL="/tmp/qemu_ubuntu_rootfs.log"
UBUNTU_ROOTFS="/home/jericho/projects/zion/projects/visual_audio/ubuntu-24.04-server-cloudimg-amd64.raw"
V4_DISK="/tmp/ubuntu_v4_efi.img"

# Check if files exist
if [ ! -f "$UBUNTU_ROOTFS" ]; then
    echo "ERROR: Ubuntu rootfs not found at $UBUNTU_ROOTFS"
    exit 1
fi

if [ ! -f "$V4_DISK" ]; then
    echo "ERROR: V4 boot disk not found at $V4_DISK"
    exit 1
fi

# Clear previous serial log
rm -f "$QEMU_SERIAL"

# Boot QEMU with:
# - 2GB RAM
# - KVM acceleration
# - OVMF UEFI firmware
# - V4 boot disk as virtio-blk device 0
# - Ubuntu rootfs as virtio-blk device 1
# - Serial output to file
# - No display (headless)
qemu-system-x86_64 \
    -m 2G \
    -enable-kvm \
    -cpu host \
    -display none \
    -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
    -drive if=pflash,format=raw,file=/tmp/my_vars.fd \
    -drive format=raw,file="$V4_DISK",if=virtio \
    -drive format=raw,file="$UBUNTU_ROOTFS",if=virtio \
    -serial file:"$QEMU_SERIAL" \
    -no-reboot &

QEMU_PID=$!
echo "QEMU PID: $QEMU_PID"

# Wait for boot to progress (60 seconds)
echo "Waiting for boot (60 seconds)..."
sleep 60

# Kill QEMU
kill -9 $QEMU_PID 2>/dev/null || true

# Show serial output
echo "=== Serial Output ==="
cat "$QEMU_SERIAL"
echo "=== End of Serial Output ==="

# Check for success indicators
if grep -q "HELLO FROM X86_64 TINY INITRAMFS" "$QEMU_SERIAL"; then
    echo "✓ Initramfs loaded successfully"
else
    echo "✗ Initramfs failed to load"
fi

if grep -q "systemd\|Ubuntu\|Welcome to Ubuntu" "$QEMU_SERIAL"; then
    echo "✓ Ubuntu rootfs booted successfully"
else
    echo "✗ Ubuntu rootfs did not boot"
fi