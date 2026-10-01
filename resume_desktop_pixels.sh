#!/bin/bash
# Resume the pixel-encoded VM checkpoint made by snapshot_desktop_pixels.sh.
# Skips SeaBIOS, GRUB, the kernel boot sequence, and GDM entirely -- the
# guest starts already logged in, exactly where the checkpoint was taken.
set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTAINER_DIR="$PROJECT_ROOT/ubuntu_desktop_pxc1_v1_snapshot"
BACKEND="$PROJECT_ROOT/systems/virtio_pixel_rs/target/release/virtio_pixel_backend"
DECODER="$PROJECT_ROOT/tools/pxc1/target/release/pxc1-decode"
SOCKET="/tmp/virtio-pixel-interactive.sock"
MONITOR="/tmp/qmon.sock"
SHM_DIR="/home/jericho/scratch/qemu_shm"
STATE_FILE="/home/jericho/scratch/vm_state_resume.bin"

if [ ! -d "$CONTAINER_DIR" ]; then
    echo "Error: no checkpoint found at $CONTAINER_DIR"
    echo "Run ./snapshot_desktop_pixels.sh first."
    exit 1
fi

echo "=== Zero-Boot Pixel Desktop Resume ==="
echo "Connect a VNC viewer to 127.0.0.1:5901 to see the GUI."
echo "======================================="

pkill -9 -f "virtio_pixel_backend $CONTAINER_DIR" 2>/dev/null || true
pkill -9 -f "qemu-system-x86_64.*$SOCKET" 2>/dev/null || true
rm -f "$SOCKET" "$MONITOR"
rm -rf "$SHM_DIR"
mkdir -p "$SHM_DIR"

echo "Starting pixel block device backend..."
"$BACKEND" "$CONTAINER_DIR" "$SOCKET" > /tmp/virtio_resume_backend.log 2>&1 &
BACKEND_PID=$!

for i in $(seq 1 60); do
    [ -S "$SOCKET" ] && break
    sleep 1
done
if [ ! -S "$SOCKET" ]; then
    echo "Error: backend socket failed to start."
    kill $BACKEND_PID 2>/dev/null
    exit 1
fi

echo "Decoding ram_snapshot section from pixels..."
"$DECODER" "$CONTAINER_DIR" ram_snapshot "$STATE_FILE"

echo "Resuming straight from checkpoint (no boot)..."
qemu-system-x86_64 \
    -machine q35,memory-backend=ram \
    -object memory-backend-file,share=on,size=4G,mem-path="$SHM_DIR",id=ram \
    -m 4G \
    -smp 4 \
    -cpu host \
    -enable-kvm \
    -vga std \
    -usb -device usb-tablet \
    -vnc :1 \
    -monitor unix:"$MONITOR",server=on,wait=off \
    -chardev socket,id=blk0,path="$SOCKET" \
    -device vhost-user-blk-pci,chardev=blk0,num-queues=1,bootindex=1 \
    -incoming "exec:cat $STATE_FILE" \
    -daemonize -pidfile /tmp/qemu_resume_live.pid

QEMU_PID=$(cat /tmp/qemu_resume_live.pid)

# Wait for migration-in to complete, then unpause.
for i in $(seq 1 30); do
    STATUS=$(echo 'info migrate' | socat - unix-connect:"$MONITOR" 2>/dev/null | tr -d '\r' | sed 's/\x1b\[[0-9;]*[a-zA-Z]//g' | grep -o "Migration status: [a-z]*" | awk '{print $3}')
    [ "$STATUS" = "completed" ] && break
    sleep 0.5
done
echo 'cont' | socat - unix-connect:"$MONITOR" > /dev/null 2>&1

echo ""
echo "=== Resumed. QEMU pid $QEMU_PID, VNC on 127.0.0.1:5901 ==="
echo "The guest is running from the exact moment it was checkpointed."
echo "kill $QEMU_PID  (and the backend) when done."
