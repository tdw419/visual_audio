#!/bin/bash
# boot_v5_vm.sh — boot the V5 VM: a copy of the V4 desktop image
# (ubuntu-desktop-v5.raw, copied from ubuntu-desktop-15g.raw) for building a
# new environment independently of V4. Runs on its own SSH port/monitor
# socket so it can coexist with a running V4 VM.
set -e

cd "$(dirname "$0")"

cp /usr/share/OVMF/OVMF_VARS_4M.fd /tmp/my_vars_v5vm.fd

qemu-system-x86_64 \
    -m 16G \
    -enable-kvm \
    -cpu host \
    -machine q35 \
    -device virtio-vga \
    -display sdl \
    -monitor unix:/tmp/qemu_monitor_v5vm.sock,server,nowait \
    -netdev user,id=net0,hostfwd=tcp::2224-:22 \
    -device virtio-net-pci,netdev=net0 \
    -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
    -drive if=pflash,format=raw,file=/tmp/my_vars_v5vm.fd \
    -drive id=bootdisk,format=raw,file=/tmp/ubuntu_v4_efi.img,if=none \
    -device ide-hd,drive=bootdisk,bootindex=1 \
    -drive id=rootdisk,file="$(pwd)/ubuntu-desktop-v5.raw",format=raw,if=none \
    -device virtio-blk-pci,drive=rootdisk,bootindex=2 \
    -fsdev local,id=zionfs,path=/home/jericho/projects/zion,security_model=mapped-xattr \
    -device virtio-9p-pci,fsdev=zionfs,mount_tag=zion \
    -serial file:/tmp/qemu_serial_v5vm.log \
    &
echo "V5 VM started (pid $!) — SSH: ssh -p 2224 jericho@127.0.0.1 (password: israel)"
