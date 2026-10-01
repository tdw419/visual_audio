#!/bin/bash
# Alpine x86_64 Boot Test

set -e

ISO="boot_images/alpine-virt-x86_64.iso"
LOG="/tmp/alpine_x86_boot.log"
PID_FILE="/tmp/alpine_x86_boot.pid"

if [ ! -f "$ISO" ]; then
    echo "❌ ISO not found: $ISO"
    exit 1
fi

echo "=== Alpine x86_64 Boot Test ==="
echo "ISO: $ISO"
echo "Log: $LOG"
echo ""

# Boot QEMU (live mode from ISO)
qemu-system-x86_64 \
    -enable-kvm \
    -m 512M \
    -smp 1 \
    -drive file="$ISO",media=cdrom,readonly=on \
    -nographic -serial mon:stdio \
    -no-reboot > "$LOG" 2>&1 &
QEMU_PID=$!

echo "QEMU PID: $QEMU_PID"
echo "Waiting for Alpine boot prompt..."

# Wait for login prompt or timeout
TIMEOUT=30
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
    if grep -q "localhost login:" "$LOG" 2>/dev/null; then
        echo ""
        echo "✓ Alpine booted successfully!"
        kill $QEMU_PID 2>/dev/null || true
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