#!/bin/bash
# Fixed boot script with proper cleanup and timing

set -e

echo "=== VirtIO Pixel Spatial Boot Test ==="
echo ""

MKV_PATH="/home/jericho/projects/zion/projects/visual_audio/visual_audio.mkv"
SOCKET_PATH="/tmp/virtio-pixel-spatial.sock"
BACKEND_BIN="./target/release/virtio_pixel_backend"

cd /home/jericho/projects/zion/projects/visual_audio/systems/virtio_pixel_rs

# Cleanup function
cleanup() {
    echo "Cleaning up..."
    pkill -f virtio_pixel_backend 2>/dev/null || true
    pkill -f qemu-system-x86_64 2>/dev/null || true
    rm -f $SOCKET_PATH
    sleep 1
}
trap cleanup EXIT

# Cleanup before starting
cleanup

# Build backend if needed
if [ ! -f "$BACKEND_BIN" ]; then
    echo "Building backend..."
    cargo build --release
fi

# Start backend in background with full logging
echo "Starting VirtIO Pixel backend..."
$BACKEND_BIN "$MKV_PATH" "$SOCKET_PATH" 2>&1 &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"

# Wait for socket AND backend to be ready
echo "Waiting for backend to initialize..."
for i in {1..60}; do
    if [ -S "$SOCKET_PATH" ] && ps -p $BACKEND_PID > /dev/null 2>&1; then
        echo "✓ Backend and socket ready"
        break
    fi
    sleep 0.5
done

if [ ! -S "$SOCKET_PATH" ]; then
    echo "✗ Socket not created"
    exit 1
fi

if ! ps -p $BACKEND_PID > /dev/null 2>&1; then
    echo "✗ Backend died"
    exit 1
fi

# Give backend extra time to fully initialize
sleep 2

# Launch QEMU with VirtIO block device pointing to our vhost-user socket
echo "Launching QEMU with VirtIO Pixel backend..."
qemu-system-x86_64 \
    -chardev socket,id=blk0,path=$SOCKET_PATH \
    -device vhost-user-blk-pci,chardev=blk0,bootindex=0 \
    -m 2G -smp 2 \
    -display none -serial mon:stdio \
    -no-reboot 2>&1 &
QEMU_PID=$!
echo "QEMU PID: $QEMU_PID"

# Wait for boot (indefinitely - user can Ctrl-C to stop)
echo "Waiting for boot (Ctrl-C to stop)..."
wait $QEMU_PID
EXIT_CODE=$?

echo ""
echo "=== Boot completed with exit code: $EXIT_CODE ==="

exit $EXIT_CODE