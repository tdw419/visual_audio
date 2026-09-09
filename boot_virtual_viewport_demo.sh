#!/bin/bash
# Boot Pixel Linux with Virtual Viewpoint Extension
set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTAINER_DIR="$PROJECT_ROOT/ubuntu_desktop_pxc1_v1"
BACKEND="$PROJECT_ROOT/systems/virtio_pixel_rs/target/release/virtio_pixel_backend_ext"
SOCKET="/tmp/virtio-pixel-virtual-viewport.sock"

# Second container for off-screen demo
CONTAINER_DIR_2="$PROJECT_ROOT/ubuntu_desktop_pxc1_v2"

if [ ! -d "$CONTAINER_DIR_2" ]; then
    echo "Creating second container for off-screen demo..."
    cp -r "$CONTAINER_DIR" "$CONTAINER_DIR_2"
    echo "✓ Second container created"
fi

echo "=== Virtual Viewpoint Demo Boot ==="
echo "This boots Pixel Linux with infinite desktop capabilities."
echo "Two containers will be available at different virtual coordinates."
echo ""

# Cleanup
pkill -9 virtio_pixel_backend 2>/dev/null || true
rm -f "$SOCKET"
rm -rf /home/jericho/scratch/qemu_shm
mkdir -p /home/jericho/scratch/qemu_shm

# Start extended backend
echo "Starting virtual viewport backend..."
$BACKEND "$CONTAINER_DIR" "$SOCKET" "$CONTAINER_DIR_2" > /tmp/virtio_viewport_backend.log 2>&1 &
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

echo "Backend ready."
echo ""

echo "Booting into virtual viewport environment..."
echo ""

# Boot with QEMU
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
    -netdev user,id=net0,hostfwd=tcp::2222-:22 \
    -device virtio-net-pci,netdev=net0 \
    -chardev socket,id=blk0,path="$SOCKET" \
    -device vhost-user-blk-pci,chardev=blk0,num-queues=1,bootindex=1 \
    -fsdev local,id=zionshare,path=/home/jericho/zion,security_model=mapped-xattr \
    -device virtio-9p-pci,fsdev=zionshare,mount_tag=host_zion \
    -serial stdio
