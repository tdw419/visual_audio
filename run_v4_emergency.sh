#!/bin/bash
set -ex

# Build the bootloader
cd /home/jericho/projects/zion/projects/visual_audio/systems/v4_bootloader_x86
cargo build --release --target x86_64-unknown-uefi

# Rebuild the disk image fresh from scratch
rm -f /tmp/ubuntu_v4_efi.img
dd if=/usr/share/OVMF/OVMF_VARS_4M.fd of=/tmp/ubuntu_v4_efi.img bs=512 count=9216 conv=notrunc
dd if=target/x86_64-unknown-uefi/release/bootloader_uefi_v4.efi of=/tmp/ubuntu_v4_efi.img bs=512 seek=1 conv=notrunc

# Verify cmdline was burned in
echo "=== Verifying cmdline in disk image ==="
strings /tmp/ubuntu_v4_efi.img | grep "console=ttyS0" | tail -1

# Boot and wait for emergency shell
echo ""
echo "=== Booting with emergency target ==="
cd /home/jericho/projects/zion/projects/visual_audio
rm -f /tmp/qemu_serial.log

timeout 30s qemu-system-x86_64 -m 1G -enable-kvm -cpu host -display none \
    -d int,cpu_reset -D /tmp/qemu_int.log \
    -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
    -drive if=pflash,format=raw,file=/tmp/my_vars.fd \
    -drive id=bootdisk,format=raw,file=/tmp/ubuntu_v4_efi.img,if=none \
    -device ide-hd,drive=bootdisk,bootindex=1 \
    -drive id=rootdisk,file=ubuntu-24.04-server-cloudimg-amd64.raw,format=raw,if=none \
    -device virtio-blk-pci,drive=rootdisk,bootindex=2 \
    -serial file:/tmp/qemu_serial.log 2>&1 || echo "QEMU exited: $?"

echo ""
echo "=== Serial output tail ==="
tail -30 /tmp/qemu_serial.log

echo ""
echo "=== Looking for emergency shell ==="
grep -i "emergency\|give root password\|sh-\# *\|root@.*:~#\|/ #" /tmp/qemu_serial.log | tail -5