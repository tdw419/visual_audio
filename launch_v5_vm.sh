#!/bin/bash
# launch_v5_vm.sh — launch the desktop VM fully detached from the terminal session
# so no vte-spawn scope cleanup can SIGTERM it (the prior launch died that way).
# Prints the QEMU PID.
set -e

killall qemu-system-x86_64 2>/dev/null || true
sleep 1
rm -f /tmp/qemu_serial_v5int.log /tmp/qemu_monitor_v5.sock

cp /usr/share/OVMF/OVMF_VARS_4M.fd /tmp/my_vars_v5int.fd

setsid nohup qemu-system-x86_64 \
    -m 2G \
    -enable-kvm \
    -cpu host \
    -machine q35 \
    -device virtio-vga \
    -monitor unix:/tmp/qemu_monitor_v5.sock,server,nowait \
    -netdev user,id=net0,hostfwd=tcp::2222-:22 \
    -device virtio-net-pci,netdev=net0 \
    -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
    -drive if=pflash,format=raw,file=/tmp/my_vars_v5int.fd \
    -drive id=bootdisk,format=raw,file=/tmp/ubuntu_v4_efi.img,if=none \
    -device ide-hd,drive=bootdisk,bootindex=1 \
    -drive id=rootdisk,file=/home/jericho/projects/zion/projects/visual_audio/ubuntu-desktop-15g.raw,format=raw,if=none \
    -device virtio-blk-pci,drive=rootdisk,bootindex=2 \
    -serial file:/tmp/qemu_serial_v5int.log \
    -display none \
    >/tmp/qemu_v5int_stdout.log 2>&1 &
echo "QEMU_PID=$!"
