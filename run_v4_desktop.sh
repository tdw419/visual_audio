#!/bin/bash
set -ex

cd /home/jericho/projects/zion/projects/visual_audio

# Clear old logs
rm -f /tmp/qemu_serial.log /tmp/qemu_int.log

echo "=== Booting Ubuntu Desktop via V4 bootloader ==="
echo "Disk: ubuntu-desktop-15g.raw (15GB)"
echo ""

# Boot QEMU and wait for login prompt
timeout 180s qemu-system-x86_64 -m 2G -enable-kvm -cpu host -display none \
    -d int,cpu_reset -D /tmp/qemu_int.log \
    -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
    -drive if=pflash,format=raw,file=/tmp/my_vars.fd \
    -drive id=bootdisk,format=raw,file=/tmp/ubuntu_v4_efi.img,if=none \
    -device ide-hd,drive=bootdisk,bootindex=1 \
    -drive id=rootdisk,file=ubuntu-desktop-15g.raw,format=raw,if=none \
    -device virtio-blk-pci,drive=rootdisk,bootindex=2 \
    -serial file:/tmp/qemu_serial.log 2>&1 || echo "Exit code: $?"

echo ""
echo "=== Serial output tail ==="
tail -50 /tmp/qemu_serial.log

echo ""
echo "=== Checking for login prompt ==="
if grep -q "ubuntu login:" /tmp/qemu_serial.log; then
    echo "✓ Login prompt reached!"
    echo ""
    echo "=== Lines containing 'ubuntu login:' ==="
    grep -B2 -A2 "ubuntu login:" /tmp/qemu_serial.log | tail -10
else
    echo "✗ Login prompt not found"
fi

echo ""
echo "=== Checking for boot completion ==="
grep -E "Reached target|Started|Finished" /tmp/qemu_serial.log | tail -20