#!/bin/bash
set -e

cd /home/jericho/projects/zion/projects/visual_audio

echo "=== WC008 End-to-End Demo: V4 Boot + GPU Window Coordinator GUI ==="
rm -f /tmp/qemu_serial.log /tmp/qemu_monitor.sock

echo "Booting QEMU with VNC enabled (vnc=:1) and QEMU monitor socket — NO host filesystem passthrough"
echo "wc008_gui binary is baked into the guest at /opt/geos_pixel/wc008_gui"
qemu-system-x86_64 -m 2G -enable-kvm -cpu host \
    -display vnc=:1 \
    -monitor unix:/tmp/qemu_monitor.sock,server,nowait \
    -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
    -drive if=pflash,format=raw,file=/tmp/my_vars.fd \
    -drive id=bootdisk,format=raw,file=/tmp/ubuntu_v4_efi.img,if=none \
    -device ide-hd,drive=bootdisk,bootindex=1 \
    -drive id=rootdisk,file=/home/jericho/projects/zion/projects/visual_audio/ubuntu-desktop-15g.raw,format=raw,if=none \
    -device virtio-blk-pci,drive=rootdisk,bootindex=2 \
    -net nic -net user,hostfwd=tcp::2222-:22 \
    -serial file:/tmp/qemu_serial.log &
QEMU_PID=$!

echo "QEMU started with PID: $QEMU_PID"
echo "QEMU monitor socket: /tmp/qemu_monitor.sock"
echo "VNC available on :1"
echo ""
echo "Waiting for boot (serial console shows 'ubuntu login:')..."
echo "Press Ctrl+C to stop QEMU."

wait $QEMU_PID