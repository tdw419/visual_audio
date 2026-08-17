#!/bin/bash
# Cognitive Container Boot - Session Fixes Applied

set -e

MKV_FILE="ubuntu_cognitive_vac2_v3_full.nut"
SOCKET="/tmp/virtio_cognitive.sock"
BACKEND_LOG="/tmp/virtio_cognitive_backend.log"
QEMU_LOG="container_boot.log"

echo "=== Cognitive Container Boot (Session Fixes Applied) ==="
echo "Container: $MKV_FILE"
echo ""
echo "Fixes applied this session:"
echo "  1. Backend: decoded_size = (frames - 1) * bytes_per_frame (off-by-one fix)"
echo "  2. Backend: meta.json lookup with_suffix (was replacing .nut)"
echo "  3. Initramfs: offset 4716694251 (after initramfs + gguf, not at start)"
echo ""

if [ ! -f "$MKV_FILE" ]; then
    echo "❌ Container not found: $MKV_FILE"
    echo "Run: python3 tools/encode_spatial_container.py \\"
    echo "    ubuntu-24.04-server-cloudimg-amd64.raw \\"
    echo "    initramfs-cognitive/output/initramfs-cognitive.gz \\"
    echo "    ~/.cache/visual_audio/gguf/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf \\"
    echo "    $MKV_FILE"
    exit 1
fi

# Check container integrity
FRAMES=$(ffprobe -v error -count_frames -show_entries stream=nb_read_frames -of default=noprint_wrappers=1 "$MKV_FILE")
echo "Container frames: $FRAMES (expected: 283)"
if [ "$FRAMES" -ne 283 ]; then
    echo "⚠️  Container incomplete - may fail at metadata offset"
fi
echo ""

# Clean up
rm -f "$SOCKET"
rm -rf /home/jericho/scratch/qemu_shm
mkdir -p /home/jericho/scratch/qemu_shm

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

# Boot
echo "[2] Starting QEMU Container..."

qemu-system-x86_64 \
    -machine q35,memory-backend=ram \
    -object memory-backend-file,share=on,size=4G,mem-path=/home/jericho/scratch/qemu_shm,id=ram \
    -m 4G \
    -smp 4 \
    -cpu host \
    -enable-kvm \
    -kernel /home/jericho/scratch/vmlinuz-virt \
    -initrd initramfs-cognitive/output/initramfs-cognitive.gz \
    -append "console=ttyS0 quiet container_boot" \
    -display none \
    -chardev socket,id=blk0,path="$SOCKET" \
    -device vhost-user-blk-pci,chardev=blk0,num-queues=1 \
    -serial stdio | tee "$QEMU_LOG"

echo ""
echo "=== Container Shutdown ==="
kill $BACKEND_PID 2>/dev/null || true
rm -f "$SOCKET"
echo "Log saved to: $QEMU_LOG"

# Check results
if grep -q "Cognitive payload detected at offset 4716694251" "$QEMU_LOG"; then
    echo "✓ Metadata found at correct offset"
fi

if grep -q "LLM weights extracted successfully" "$QEMU_LOG"; then
    echo "✓ LLM extraction succeeded"
    exit 0
elif grep -q "Could not find cognitive metadata" "$QEMU_LOG"; then
    echo "❌ Metadata not found (container incomplete?)"
    exit 1
else
    echo "⚠️  Unknown result - check logs"
    exit 1
fi