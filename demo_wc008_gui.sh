#!/bin/bash
set -e

cd /home/jericho/projects/zion/projects/visual_audio

echo "=== WC008 End-to-End Demo: V4 Boot + GPU Window Coordinator GUI ==="
rm -f /tmp/qemu_serial.log

echo "Booting QEMU with VNC enabled (vnc=:1) and 9p passthrough for host_zion..."
# Note: we use -display vnc=:1 instead of -display none
qemu-system-x86_64 -m 2G -enable-kvm -cpu host \
    -display vnc=:1 \
    -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
    -drive if=pflash,format=raw,file=/tmp/my_vars.fd \
    -drive id=bootdisk,format=raw,file=/tmp/ubuntu_v4_efi.img,if=none \
    -device ide-hd,drive=bootdisk,bootindex=1 \
    -drive id=rootdisk,file=ubuntu-desktop-15g.raw,format=raw,if=none \
    -device virtio-blk-pci,drive=rootdisk,bootindex=2 \
    -virtfs local,path=/home/jericho/zion,mount_tag=host_zion,security_model=none,id=zionshare \
    -net nic -net user,hostfwd=tcp::2222-:22 \
    -serial file:/tmp/qemu_serial.log &
QEMU_PID=$!

echo ""
echo "QEMU started. VNC available on :1"
echo "To view the Ubuntu Desktop GUI, open another terminal and run:"
echo "  vncviewer localhost:1"
echo ""
echo "Once booted, log into the Ubuntu GUI, open a terminal, and run:"
echo "  sudo mkdir -p /host_zion"
echo "  sudo mount -t 9p -o trans=virtio,version=9p2000.L host_zion /host_zion"
echo "  cd /host_zion/projects/visual_audio/systems/geos_pixel"
echo "  cargo run --example wc008_gui --features gpu"
echo ""
echo "Press Ctrl+C to stop QEMU."

wait $QEMU_PID
