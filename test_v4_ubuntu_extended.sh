#!/bin/bash
set -ex

# Extended test to see what devices are available
QEMU_SERIAL="/tmp/qemu_v4_ubuntu_extended.log"
V4_DISK="/tmp/ubuntu_v4_efi.img"
UBUNTU_ROOTFS="/home/jericho/projects/zion/projects/visual_audio/ubuntu-24.04-server-cloudimg-amd64.raw"
VARS_FD="/tmp/my_vars_extended.fd"

# Create UEFI vars file if needed
if [ ! -f "$VARS_FD" ]; then
    dd if=/dev/zero of="$VARS_FD" bs=1M count=4 2>/dev/null
fi

# Clear previous log
rm -f "$QEMU_SERIAL"

echo "Extended boot test - checking block devices..."
echo ""

# Boot QEMU with both drives
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
    -no-reboot \
    -monitor none &

QEMU_PID=$!
echo "QEMU PID: $QEMU_PID"

# Wait for boot
sleep 45

# Kill QEMU
kill -9 $QEMU_PID 2>/dev/null || true
wait $QEMU_PID 2>/dev/null || true

echo ""
echo "=== Serial Output ==="
tail -100 "$QEMU_SERIAL"
echo ""
echo "=== Log saved to $QEMU_SERIAL ==="