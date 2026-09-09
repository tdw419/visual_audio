#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Test Alpine x86_64 Boot ==="

DISK="boot_images/alpine_x86_test.qcow2"
ISO="boot_images/alpine-virt-x86_64.iso"
LOG="/tmp/alpine_x86_boot.log"

# Check if disk exists
if [ ! -f "$DISK" ]; then
    echo "Creating 2G test disk..."
    mkdir -p boot_images
    qemu-img create -f qcow2 "$DISK" 2G
fi

# Check if ISO exists
if [ ! -f "$ISO" ]; then
    echo "❌ ISO not found: $ISO"
    exit 1
fi

echo "Disk: $DISK"
echo "ISO: $ISO"
echo "Log: $LOG"
echo ""

# Boot QEMU (live mode from ISO)
qemu-system-x86_64 \
    -enable-kvm \
    -m 512M \
    -smp 1 \
    -drive file="$DISK",format=qcow2,if=virtio \
    -drive file="$ISO",media=cdrom,readonly=on \
    -nographic -serial mon:stdio \
    -no-reboot > "$LOG" 2>&1 &
QEMU_PID=$!

echo "QEMU PID: $QEMU_PID"
echo "Waiting for Alpine boot prompt..."

# Wait for login prompt or timeout
TIMEOUT=45
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
    if grep -q "localhost login:" "$LOG" 2>/dev/null; then
        echo ""
        echo "✓ Alpine booted successfully!"
        echo ""
        echo "Boot log (last 15 lines):"
        tail -15 "$LOG"
        kill $QEMU_PID 2>/dev/null || true
        wait $QEMU_PID 2>/dev/null || true
        exit 0
    fi
    sleep 2
    ELAPSED=$((ELAPSED + 2))
    echo -n "."
done

echo ""
echo "❌ Boot timeout after ${TIMEOUT}s"
kill $QEMU_PID 2>/dev/null || true
tail -20 "$LOG"
exit 1