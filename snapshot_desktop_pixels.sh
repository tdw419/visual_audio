#!/bin/bash
# Boot the full-pixel Ubuntu desktop, let it settle to an idle logged-in state,
# then checkpoint the entire running VM (CPU + RAM + device state) via QEMU
# migration-to-file and encode that checkpoint as a new PXC1 "ram_snapshot"
# section. resume_desktop_pixels.sh can then skip boot entirely and resume
# straight into this exact moment.
set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTAINER_DIR="$PROJECT_ROOT/ubuntu_desktop_pxc1_v1"
SNAPSHOT_CONTAINER_DIR="$PROJECT_ROOT/ubuntu_desktop_pxc1_v1_snapshot"
BACKEND="$PROJECT_ROOT/systems/virtio_pixel_rs/target/release/virtio_pixel_backend"
ENCODER="$PROJECT_ROOT/tools/pxc1/target/release/pxc1-encode"
SOCKET="/tmp/virtio-pixel-snapshot.sock"
MONITOR="/tmp/qmon-snapshot.sock"
SHM_DIR="/home/jericho/scratch/qemu_shm_snapshot"
STATE_FILE="/home/jericho/scratch/vm_state.bin"
SETTLE_SECONDS="${1:-100}"

echo "=== Pixel Desktop Checkpoint ==="
echo "Booting $CONTAINER_DIR, waiting ${SETTLE_SECONDS}s to settle, then snapshotting."
echo "================================================================"

pkill -9 -f "virtio_pixel_backend $CONTAINER_DIR" 2>/dev/null || true
pkill -9 -f "qemu-system-x86_64.*$SOCKET" 2>/dev/null || true
rm -f "$SOCKET" "$MONITOR" "$STATE_FILE"
rm -rf "$SHM_DIR"
mkdir -p "$SHM_DIR"

echo "Starting pixel block device backend..."
"$BACKEND" "$CONTAINER_DIR" "$SOCKET" > /tmp/virtio_snapshot_backend.log 2>&1 &
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

echo "Booting (SeaBIOS -> GRUB -> pixel disk kernel)..."
qemu-system-x86_64 \
    -machine q35,memory-backend=ram \
    -object memory-backend-file,share=on,size=4G,mem-path="$SHM_DIR",id=ram \
    -m 4G \
    -smp 4 \
    -cpu host \
    -enable-kvm \
    -vga std \
    -usb -device usb-tablet \
    -vnc :3 \
    -monitor unix:"$MONITOR",server=on,wait=off \
    -chardev socket,id=blk0,path="$SOCKET" \
    -device vhost-user-blk-pci,chardev=blk0,num-queues=1,bootindex=1 \
    -daemonize -pidfile /tmp/qemu_snapshot.pid

QEMU_PID=$(cat /tmp/qemu_snapshot.pid)

echo "Waiting ${SETTLE_SECONDS}s for boot + autologin to settle..."
sleep "$SETTLE_SECONDS"

if ! kill -0 "$QEMU_PID" 2>/dev/null; then
    echo "Error: QEMU exited before settling."
    kill $BACKEND_PID 2>/dev/null
    exit 1
fi

echo "Pausing VM and dumping full state (CPU + RAM + devices)..."
{
    echo 'stop'
    sleep 1
    echo "migrate \"exec:cat > $STATE_FILE\""
    sleep 1
} | socat - unix-connect:"$MONITOR" > /dev/null 2>&1

# Wait for migration to report completed
for i in $(seq 1 60); do
    STATUS=$(echo 'info migrate' | socat - unix-connect:"$MONITOR" 2>/dev/null | tr -d '\r' | sed 's/\x1b\[[0-9;]*[a-zA-Z]//g' | grep -o "Migration status: [a-z]*" | awk '{print $3}')
    if [ "$STATUS" = "completed" ]; then break; fi
    sleep 1
done

if [ "$STATUS" != "completed" ]; then
    echo "Error: migration did not complete (status: $STATUS)."
    kill "$QEMU_PID" $BACKEND_PID 2>/dev/null
    exit 1
fi

echo "✓ State captured: $(du -h "$STATE_FILE" | cut -f1)"

kill "$QEMU_PID" 2>/dev/null

echo "Encoding checkpoint into PXC1 (rootfs + ram_snapshot)..."
rm -rf "$SNAPSHOT_CONTAINER_DIR"
"$ENCODER" "$SNAPSHOT_CONTAINER_DIR" \
    rootfs "$PROJECT_ROOT/ubuntu-desktop-shrunk.raw" \
    ram_snapshot "$STATE_FILE"

kill $BACKEND_PID 2>/dev/null
rm -f "$SOCKET" "$MONITOR"

echo ""
echo "=== Checkpoint complete ==="
echo "Container: $SNAPSHOT_CONTAINER_DIR"
echo "Run ./resume_desktop_pixels.sh to boot straight into this moment."
