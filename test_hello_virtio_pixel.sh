#!/bin/bash
# Test VirtIO-Pixel backend with hello.img (via test.nut)

set -e

MKV_FILE="test.nut"
KERNEL="/home/jericho/projects/zion/projects/visual_audio/boot_images/hello.img"
SOCKET="/tmp/test_hello_virtio.sock"
BACKEND_LOG="/tmp/test_hello_backend.log"

echo "=== Test VirtIO-Pixel with hello.img ==="
echo "Container: $MKV_FILE (5 frames)"
echo "Kernel: $KERNEL"

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
        cat "$BACKEND_LOG"
        exit 1
    fi
    sleep 1
done

# Boot hello.img
echo "[2] Booting hello.img..."
qemu-system-riscv64 \
    -machine virt \
    -nographic \
    -bios default \
    -kernel "$KERNEL" \
    -chardev socket,id=blk0,path="$SOCKET" \
    -device vhost-user-blk-device,chardev=blk0 \
    -no-reboot 2>&1 | tee /tmp/test_hello_boot.log &
QEMU_PID=$!

# Wait for hello message or timeout
TIMEOUT=30
ELAPSED=0
echo "Waiting for hello message..."
while [ $ELAPSED -lt $TIMEOUT ]; do
    if grep -q "HELLO FROM THE SPOKEN KERNEL" /tmp/test_hello_boot.log 2>/dev/null; then
        echo ""
        echo "✓ hello.img booted successfully with VirtIO-Pixel!"
        kill $QEMU_PID 2>/dev/null || true
        kill $BACKEND_PID
        exit 0
    fi
    sleep 2
    ELAPSED=$((ELAPSED + 2))
    echo -n "."
done

echo ""
echo "❌ Boot timeout"
kill $QEMU_PID 2>/dev/null || true
kill $BACKEND_PID

echo ""
echo "Boot log:"
tail -50 /tmp/test_hello_boot.log

echo ""
echo "Backend log:"
tail -30 "$BACKEND_LOG"

exit 1