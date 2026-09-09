#!/bin/bash
set -e

cd /home/jericho/projects/zion/projects/visual_audio

echo "=== V5 Development: Hardware-Accelerated VM (virtio-vga-gl) ==="
rm -f /tmp/qemu_serial.log /tmp/qemu_monitor.sock

echo "Booting QEMU with SDL display (gl=on) and virtio-vga-gl for hardware Vulkan/3D acceleration"
echo "This will allow geos_pixel_v5 to use the host GPU via Venus/Virgl instead of falling back to llvmpipe."

qemu-system-x86_64 -m 2G -enable-kvm -cpu host \
    -display sdl \
    -device virtio-vga \
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
echo ""
echo "Press Ctrl+C to stop QEMU."

wait $QEMU_PID
