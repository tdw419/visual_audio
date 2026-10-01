#!/bin/bash
# boot_v5_interactive_test.sh — boot the desktop VM for Phase 3 interactive verification.
# Fixes over the prior session's VM:
#  1. Explicit virtio-net-pci so SSH actually works (old cmdline had no NIC probe).
#  2. Monitor socket on a known path for mouse injection + screendump.
#  3. -display none: input is injected at device-emulation level via the QEMU
#     monitor (PS/2 controller), which is independent of the SDL display backend.
set -e

killall qemu-system-x86_64 2>/dev/null || true
rm -f /tmp/qemu_serial_v5int.log /tmp/qemu_monitor_v5.sock

cp /usr/share/OVMF/OVMF_VARS_4M.fd /tmp/my_vars_v5int.fd

qemu-system-x86_64 \
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
    &
echo "QEMU started (pid $!)"
