#!/bin/bash
set -ex

# QEMU boot script for V4 bootloader with Ubuntu rootfs
# This boots the kernel+initramfs from the PDB/V4 boot disk,
# then the initramfs finds and boots the Ubuntu rootfs from /dev/vdb

QEMU_SERIAL="/tmp/qemu_ubuntu_rootfs_v2.log"
UBUNTU_ROOTFS="/home/jericho/projects/zion/projects/visual_audio/ubuntu-24.04-server-cloudimg-amd64.raw"
V4_DISK="/tmp/ubuntu_v4_efi_v2.img"
VARS_FD="/tmp/my_vars_v2.fd"

# Check if files exist
if [ ! -f "$UBUNTU_ROOTFS" ]; then
    echo "ERROR: Ubuntu rootfs not found at $UBUNTU_ROOTFS"
    exit 1
fi

if [ ! -f "$V4_DISK" ]; then
    echo "ERROR: V4 boot disk not found at $V4_DISK"
    echo "Please run: bash tools/build_v4_disk_v2.sh"
    exit 1
fi

# Create UEFI variables file if needed
if [ ! -f "$VARS_FD" ]; then
    dd if=/dev/zero of="$VARS_FD" bs=1M count=4 2>/dev/null
fi

# Clear previous serial log
rm -f "$QEMU_SERIAL"

echo "=== Booting V4 with Ubuntu rootfs ==="
echo "V4 Boot Disk: $V4_DISK"
echo "Ubuntu Rootfs: $UBUNTU_ROOTFS"
echo "Serial log: $QEMU_SERIAL"
echo ""

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
    -drive if=pflash,format=raw,file="$VARS_FD" \
    -drive format=raw,file="$V4_DISK",if=virtio \
    -drive format=raw,file="$UBUNTU_ROOTFS",if=virtio \
    -serial file:"$QEMU_SERIAL" \
    -no-reboot &

QEMU_PID=$!
echo "QEMU PID: $QEMU_PID"

# Wait for boot to progress (90 seconds)
echo "Waiting for boot (90 seconds)..."
sleep 90

# Kill QEMU
kill -9 $QEMU_PID 2>/dev/null || true
wait $QEMU_PID 2>/dev/null || true

# Show serial output
echo ""
echo "=== Serial Output ==="
cat "$QEMU_SERIAL"
echo "=== End of Serial Output ==="
echo ""

# Check for success indicators
if grep -q "V4 Bootloader Initramfs" "$QEMU_SERIAL"; then
    echo "✓ Initramfs loaded successfully"
else
    echo "✗ Initramfs failed to load"
fi

if grep -q "systemd\|Ubuntu\|Welcome to Ubuntu\|Reached target" "$QEMU_SERIAL"; then
    echo "✓ Ubuntu rootfs booted successfully"
else
    echo "✗ Ubuntu rootfs did not boot"
fi