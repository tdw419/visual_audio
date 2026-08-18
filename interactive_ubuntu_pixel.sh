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

# Pick a display backend: a local GTK window if a display server is
# actually available (and QEMU was built with GTK support), otherwise fall
# back to VNC (e.g. headless boxes, this sandbox, remote sessions).
DISPLAY_ARGS="-vnc :1"
DISPLAY_MSG="Serial console prints here; connect a VNC viewer to 127.0.0.1:5901
(vncviewer localhost:5901, or any VNC client) to see the GUI."
if { [ -n "$DISPLAY" ] || [ -n "$WAYLAND_DISPLAY" ]; } && \
   qemu-system-x86_64 -display help 2>/dev/null | grep -q "^gtk"; then
    DISPLAY_ARGS="-display gtk"
    DISPLAY_MSG="Serial console prints here; a QEMU window will open automatically."
fi

echo "=== Interactive Pixel Ubuntu Boot ==="
echo "This will boot the Ubuntu 24.04 Desktop OS from the pixel container."
echo "$DISPLAY_MSG"
echo "SSH: ssh -p 2222 jericho@127.0.0.1  (password: israel)"
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

# Wait for HTTP daemon (writeback endpoint)
for i in {1..30}; do
    if curl -s http://127.0.0.1:8769/health > /dev/null 2>&1; then break; fi
    sleep 1
done

echo "Backend ready. Writeback endpoint available."
echo ""

# Periodic writeback - each writeback takes ~37s (full rootfs re-encode), so the
# interval must be much longer than that or it starves the guest's ext4 journal
# mid-write and corrupts the filesystem (confirmed at 30s). 300s gives the guest
# ~85% idle time between flushes.
WRITEBACK_INTERVAL=300
(
    sleep "$WRITEBACK_INTERVAL"
    while true; do
        START=$(date +%s)
        RESULT=$(curl -s -X POST http://127.0.0.1:8769/writeback)
        DURATION=$(( $(date +%s) - START ))
        if echo "$RESULT" | grep -q '"ok":true'; then
            echo "[$(date +%H:%M:%S)] ✓ periodic writeback (${DURATION}s)"
        else
            echo "[$(date +%H:%M:%S)] ✗ periodic writeback failed: ${RESULT:-connection error}"
        fi
        sleep "$WRITEBACK_INTERVAL"
    done
) &
WRITEBACK_LOOP_PID=$!

# Trap handler - save changes on exit
cleanup() {
    echo ""
    kill $WRITEBACK_LOOP_PID 2>/dev/null || true

    echo "=== Final writeback to pixel container ==="
    if curl -s -X POST http://127.0.0.1:8769/writeback | grep -q '"ok":true'; then
        echo "✓ Writeback complete - changes saved to $CONTAINER_DIR"
    else
        echo "✗ Writeback failed - changes not saved"
    fi

    kill $BACKEND_PID 2>/dev/null || true
    rm -f "$SOCKET"
    echo "Interactive session ended."
}
trap cleanup EXIT INT TERM

echo "=== Persistence Notice ==="
echo "Changes auto-save to the pixel container every ${WRITEBACK_INTERVAL}s, plus on clean exit."
echo "Worst case data loss on a crash/kill: up to ${WRITEBACK_INTERVAL}s of guest writes."
echo "To force a writeback without exiting: curl -X POST http://127.0.0.1:8769/writeback"
echo "==========================================================="
echo ""

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
    $DISPLAY_ARGS \
    -netdev user,id=net0,hostfwd=tcp::2222-:22 \
    -device virtio-net-pci,netdev=net0 \
    -chardev socket,id=blk0,path="$SOCKET" \
    -device vhost-user-blk-pci,chardev=blk0,num-queues=1,bootindex=1 \
    -fsdev local,id=zionshare,path=/home/jericho/zion,security_model=mapped-xattr \
    -device virtio-9p-pci,fsdev=zionshare,mount_tag=host_zion \
    -serial stdio
