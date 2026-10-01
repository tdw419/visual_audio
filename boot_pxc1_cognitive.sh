#!/bin/bash
# Boot Ubuntu with PXC1 cognitive container via VirtIO-Pixel backend

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTAINER_DIR="$PROJECT_ROOT/ubuntu_cognitive_pxc1_v1"
BACKEND="$PROJECT_ROOT/systems/virtio_pixel_rs/target/release/virtio_pixel_backend"
SOCKET="/tmp/virtio-pixel-pxc1.sock"
BACKEND_LOG="/tmp/virtio_pxc1_backend.log"
QEMU_LOG="/tmp/virtio_pxc1_boot.log"
KERNEL="/home/jericho/scratch/vmlinuz-virt"

# Check inputs
if [ ! -d "$CONTAINER_DIR" ]; then
    echo "Error: Container directory not found: $CONTAINER_DIR"
    echo "Run: ./encode_ubuntu_pxc1.sh"
    exit 1
fi

if [ ! -f "$BACKEND" ]; then
    echo "Error: Backend not found: $BACKEND"
    echo "Run: cargo build --release --manifest-path systems/virtio_pixel_rs/Cargo.toml"
    exit 1
fi

if [ ! -f "$KERNEL" ]; then
    echo "Error: Kernel not found: $KERNEL"
    exit 1
fi

echo "=== PXC1 Cognitive Boot via VirtIO-Pixel ==="
echo "Container: $CONTAINER_DIR"
echo "Backend: $BACKEND"
echo "Socket: $SOCKET"
echo "Kernel: $KERNEL"
echo ""

# Verify container
if [ ! -f "$CONTAINER_DIR/header.json" ]; then
    echo "Error: header.json not found in container"
    exit 1
fi

FRAMES=$(cat "$CONTAINER_DIR/header.json" | jq -r '.total_frames')
echo "Container frames: $FRAMES (PXC1 format)"

# Cleanup
pkill -9 virtio_pixel_backend 2>/dev/null || true
sleep 1
rm -f "$SOCKET"
rm -rf /home/jericho/scratch/qemu_shm
mkdir -p /home/jericho/scratch/qemu_shm

# Start backend
echo "[1] Starting VirtIO-Pixel backend (PXC1 mode)..."
# Backend expects: mkv_path socket_path
$BACKEND "$CONTAINER_DIR" "$SOCKET" > "$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"

# Wait for socket
echo -n "Waiting for socket..."
for i in {1..30}; do
    if [ -S "$SOCKET" ]; then
        echo " ✓"
        break
    fi
    echo -n "."
    if [ $i -eq 30 ]; then
        echo " ❌ Timeout!"
        kill $BACKEND_PID 2>/dev/null
        cat "$BACKEND_LOG"
        exit 1
    fi
    sleep 1
done

# QEMU boot
echo ""
echo "[2] Booting QEMU with PXC1 container..."
echo ""

qemu-system-x86_64 \
    -machine q35,memory-backend=ram \
    -object memory-backend-file,share=on,size=4G,mem-path=/home/jericho/scratch/qemu_shm,id=ram \
    -m 4G \
    -smp 4 \
    -cpu host \
    -enable-kvm \
    -kernel "$KERNEL" \
    -initrd "$PROJECT_ROOT/initramfs-cognitive/output/initramfs-cognitive.gz" \
    -append "console=ttyS0" \
    -display none \
    -chardev socket,id=blk0,path="$SOCKET" \
    -device vhost-user-blk-pci,chardev=blk0,num-queues=1 \
    -serial stdio 2>&1 | tee "$QEMU_LOG"

# Cleanup
echo ""
echo "=== Container Shutdown ==="
kill $BACKEND_PID 2>/dev/null || true
rm -f "$SOCKET"
echo "Backend log: $BACKEND_LOG"
echo "Boot log: $QEMU_LOG"

# Check results
echo ""
echo "=== Verification ==="
if grep -q "Hash verified:" "$QEMU_LOG"; then
    echo "✓ PXC1 header parsed successfully"
fi

if grep -q "Extracted.*bytes" "$QEMU_LOG"; then
    echo "✓ GGUF extraction succeeded"
fi

if grep -q "status.*success" "$QEMU_LOG"; then
    echo "✓ Cognitive inference completed"
    echo ""
    echo "=== COGNITIVE OUTPUT ==="
    grep -A 5 "Cognitive OUTPUT" "$QEMU_LOG" | head -10
    exit 0
else
    echo "⚠️  Unknown result - check logs"
    tail -20 "$QEMU_LOG"
    exit 1
fi