#!/bin/bash
set -ex

cd /home/jericho/projects/zion/projects/visual_audio/systems/v4_bootloader_x86
cargo build --release --target x86_64-unknown-uefi

# Recreate disk image with fresh bootloader
rm -f /tmp/ubuntu_v4_efi.img
dd if=/usr/share/OVMF/OVMF_VARS_4M.fd of=/tmp/ubuntu_v4_efi.img bs=512 count=9216 conv=notrunc
dd if=target/x86_64-unknown-uefi/release/bootloader_uefi_v4.efi of=/tmp/ubuntu_v4_efi.img bs=512 seek=1 conv=notrunc

cd /home/jericho/projects/zion/projects/visual_audio

echo "Waiting 35 seconds for boot and login prompt..."
(
    sleep 35
    # Send login credentials
    echo "root"
    sleep 1
    echo "israel"
    sleep 3

    # Run verification commands
    echo "uname -a"
    sleep 2
    echo "cat /etc/os-release | head -5"
    sleep 2
    echo "ls /"
    sleep 2
    echo "systemctl is-system-running"
    sleep 2
    echo "exit"
) | timeout 60s qemu-system-x86_64 -m 1G -enable-kvm -cpu host -display none \
    -d int,cpu_reset -D /tmp/qemu_int.log \
    -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
    -drive if=pflash,format=raw,file=/tmp/my_vars.fd \
    -drive id=bootdisk,format=raw,file=/tmp/ubuntu_v4_efi.img,if=none \
    -device ide-hd,drive=bootdisk,bootindex=1 \
    -drive id=rootdisk,file=ubuntu-24.04-server-cloudimg-amd64.raw,format=raw,if=none \
    -device virtio-blk-pci,drive=rootdisk,bootindex=2 \
    -serial mon:stdio 2>&1 | tee /tmp/qemu_serial_login.log

echo ""
echo "=== Login session output ==="
cat /tmp/qemu_serial_login.log | grep -A20 "ubuntu login:"