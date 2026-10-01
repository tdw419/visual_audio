#!/bin/bash
# Minimal Cognitive Container Boot
# Demonstrates "The Screen is the Mind" extraction without full systemd boot

set -e

# Configuration
MKV_FILE="ubuntu_cognitive_vac2_v3_full.nut"  # Full untruncated container
if [ ! -f "$MKV_FILE" ]; then
    MKV_FILE="ubuntu_cognitive_vac2_v3.nut"  # Fallback to truncated version
    if [ ! -f "$MKV_FILE" ]; then
        # Fallback to older container if v3 doesn't exist
        if [ -f "ubuntu_cognitive_vac2.nut" ]; then
            MKV_FILE="ubuntu_cognitive_vac2.nut"
        else
            echo "❌ Container not found (tried: ubuntu_cognitive_vac2_v3_full.nut, ubuntu_cognitive_vac2_v3.nut, ubuntu_cognitive_vac2.nut)"
            exit 1
        fi
    fi
fi
SOCKET="/tmp/virtio_cognitive.sock"
BACKEND_LOG="/tmp/virtio_cognitive_backend.log"
QEMU_LOG="container_boot.log"

if [ ! -f "$MKV_FILE" ]; then
    # Fallback to older container if v3 doesn't exist
    if [ -f "ubuntu_cognitive_vac2.nut" ]; then
        MKV_FILE="ubuntu_cognitive_vac2.nut"
    else
        echo "❌ Container $MKV_FILE not found"
        exit 1
    fi
fi

echo "=== Cognitive Container Boot ==="
echo "Container: $MKV_FILE"

# Clean up old sockets
rm -f "$SOCKET"
rm -rf /home/jericho/scratch/qemu_shm

# Create shared memory file for QEMU 8.2 compatibility
mkdir -p /home/jericho/scratch/qemu_shm

# Start the virtio-pixel backend
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

echo "[2] Starting Minimal QEMU Container..."

# We use -serial stdio to print the boot logs directly to the console
# -display none disables the graphical VNC/SDL output

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

echo "=== Container Shutdown ==="
kill $BACKEND_PID 2>/dev/null || true
rm -f "$SOCKET"
echo "Log saved to: $QEMU_LOG"
