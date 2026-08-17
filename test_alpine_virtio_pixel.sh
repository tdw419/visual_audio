#!/bin/bash
# Simple test: Boot Alpine minimal disk image with VirtIO-Pixel backend

set -e

MKV_FILE="alpine_minimal_bootable.raw"
SOCKET="/tmp/test_alpine_virtio_pixel.sock"
BACKEND_LOG="/tmp/test_alpine_backend.log"

echo "=== Test Alpine Boot with VirtIO-Pixel Backend ==="
echo "Image: $MKV_FILE"

# Clean up
rm -f "$SOCKET"
rm -rf /home/jericho/scratch/qemu_shm_test
mkdir -p /home/jericho/scratch/qemu_shm_test

# Start backend
echo "[1] Starting VirtIO-Pixel backend..."
./systems/virtio_pixel_rs/target/release/virtio_pixel_backend \
    "$MKV_FILE" \
    "$SOCKET" > "$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!

# Wait for socket
echo -n "Waiting for backend socket..."
for i in {1..30}; do
    if [ -S "$SOCKET" ]; then
        echo " ✓"
        break
    fi
    echo -n "."
    if [ $i -eq 30 ]; then
        echo " ❌ Timeout!"
        kill $BACKEND_PID
        exit 1
    fi
    sleep 1
done

# Boot Alpine
echo "[2] Booting Alpine with kernel..."

# Use minimal initramfs kernel
KERNEL="/home/jericho/scratch/vmlinuz-virt"
if [ ! -f "$KERNEL" ]; then
    echo "Kernel not found at $KERNEL"
    echo "This test requires a Linux kernel with virtio drivers"
    kill $BACKEND_PID
    exit 1
fi

qemu-system-x86_64 \
    -machine q35,memory-backend=ram \
    -object memory-backend-file,share=on,size=4G,mem-path=/home/jericho/scratch/qemu_shm_test,id=ram \
    -m 4G \
    -smp 4 \
    -cpu host \
    -enable-kvm \
    -kernel "$KERNEL" \
    -append "console=ttyS0,115200n8 root=/dev/vda1 ro quiet" \
    -virtfs local,path=/tmp,mount_tag=host0,security_model=mapped \
    -device virtio-serial-pci \
    -chardev socket,path=$SOCKET,server=off,id=vsock \
    -device vhost-user-blk-pci,chardev=vsock \
    -serial stdio \
    -display none \
    -no-reboot 2>&1 | tee /tmp/test_alpine_boot.log &
QEMU_PID=$!

# Wait for boot (30s timeout)
TIMEOUT=30
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
    if grep -q "Welcome to Alpine\|root@.*:/#" /tmp/test_alpine_boot.log 2>/dev/null; then
        echo ""
        echo "✓ Alpine booted successfully!"
        kill $QEMU_PID 2>/dev/null || true
        kill $BACKEND_PID
        exit 0
    fi
    sleep 2
    ELAPSED=$((ELAPSED + 2))
    echo -n "."
done

echo ""
echo "❌ Boot timeout after ${TIMEOUT}s"
kill $QEMU_PID 2>/dev/null || true
kill $BACKEND_PID

echo ""
echo "Boot log:"
tail -50 /tmp/test_alpine_boot.log

exit 1