#!/bin/bash
# boot_v4_for_kms_test.sh — boot V4 (ubuntu-desktop-15g.raw) on its own
# SSH port/monitor socket/serial log so it can coexist with the live V5 VM.
# Used to verify v5_interactive's raw DRM/KMS + evdev path without touching
# the live V5 guest.
set -e

cd "$(dirname "$0")"

cp /usr/share/OVMF/OVMF_VARS_4M.fd /tmp/my_vars_v4kms.fd

qemu-system-x86_64 \
    -m 16G \
    -enable-kvm \
    -cpu host \
    -machine q35 \
    -device virtio-vga \
    -display sdl \
    -monitor unix:/tmp/qemu_monitor_v4kms.sock,server,nowait \
    -netdev user,id=net0,hostfwd=tcp::2226-:22 \
    -device virtio-net-pci,netdev=net0 \
    -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
    -drive if=pflash,format=raw,file=/tmp/my_vars_v4kms.fd \
    -drive id=bootdisk,format=raw,file=/tmp/ubuntu_v4_efi_kmstest.img,if=none \
    -device ide-hd,drive=bootdisk,bootindex=1 \
    -drive id=rootdisk,file="$(pwd)/ubuntu-desktop-15g.raw",format=raw,if=none \
    -device virtio-blk-pci,drive=rootdisk,bootindex=2 \
    -fsdev local,id=zionfs,path=/home/jericho/projects/zion,security_model=mapped-xattr \
    -device virtio-9p-pci,fsdev=zionfs,mount_tag=zion \
    -serial file:/tmp/qemu_serial_v4kms.log \
    &
echo "V4 VM (KMS test) started (pid $!) — SSH: ssh -p 2226 jericho@127.0.0.1 (password: israel)"
