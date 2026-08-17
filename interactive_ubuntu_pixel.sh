#!/bin/bash
# Interactive Ubuntu Boot via VirtIO-Pixel backend
set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTAINER_DIR="$PROJECT_ROOT/ubuntu_desktop_pxc1_v1"
BACKEND="$PROJECT_ROOT/systems/virtio_pixel_rs/target/release/virtio_pixel_backend"
SOCKET="/tmp/virtio-pixel-interactive.sock"
NATIVE_BOOT_DIR="/home/jericho/scratch/ubuntu_boot_native"
KERNEL="$NATIVE_BOOT_DIR/vmlinuz-6.8.0-136-generic"
INITRD="$NATIVE_BOOT_DIR/initrd.img-6.8.0-136-generic"

echo "=== Interactive Pixel Ubuntu Boot ==="
echo "This will boot the Ubuntu 24.04 Desktop OS from the pixel container."
echo "Serial console prints here; connect a VNC viewer to 127.0.0.1:5901"
echo "(vncviewer localhost:5901, or any VNC client) to see the GUI."
echo "To exit QEMU, press Ctrl-A, then press X."
echo "==========================================================="
echo ""

# Cleanup
pkill -9 virtio_pixel_backend 2>/dev/null || true
rm -f "$SOCKET"
rm -rf /home/jericho/scratch/qemu_shm
mkdir -p /home/jericho/scratch/qemu_shm

# Start backend
echo "Starting pixel block device backend..."
$BACKEND "$CONTAINER_DIR" "$SOCKET" > /tmp/virtio_interactive_backend.log 2>&1 &
BACKEND_PID=$!

# Wait for socket
for i in {1..60}; do
    if [ -S "$SOCKET" ]; then break; fi
    sleep 1
done

if [ ! -S "$SOCKET" ]; then
    echo "Error: Backend socket failed to start."
    kill $BACKEND_PID 2>/dev/null
    exit 1
fi

echo "Booting into interactive console..."
echo ""

# Boot with QEMU natively (SeaBIOS -> GRUB -> Pixel Disk Kernel)
qemu-system-x86_64 \
    -machine q35,memory-backend=ram \
    -object memory-backend-file,share=on,size=4G,mem-path=/home/jericho/scratch/qemu_shm,id=ram \
    -m 4G \
    -smp 4 \
    -cpu host \
    -enable-kvm \
    -vga std \
    -usb -device usb-tablet \
    -vnc :1 \
    -chardev socket,id=blk0,path="$SOCKET" \
    -device vhost-user-blk-pci,chardev=blk0,num-queues=1,bootindex=1 \
    -serial stdio

# Cleanup on exit
kill $BACKEND_PID 2>/dev/null || true
rm -f "$SOCKET"
echo ""
echo "Interactive session ended."
