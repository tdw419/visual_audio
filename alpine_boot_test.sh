#!/bin/bash
# Simple Alpine x86_64 boot test — boots from ISO to login prompt

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

ISO="boot_images/alpine-virt-x86_64.iso"
LOG="/tmp/alpine_x86_boot.log"

if [ ! -f "$ISO" ]; then
    echo "❌ ISO not found: $ISO"
    echo "Download with:"
    echo "  wget -O boot_images/alpine-virt-x86_64.iso https://dl-cdn.alpinelinux.org/alpine/v3.20/releases/x86_64/alpine-virt-3.20.3-x86_64.iso"
    exit 1
fi

echo "=== Alpine x86_64 Boot Test ==="
echo "ISO: $ISO"
echo "Log: $LOG"
echo ""

# Boot QEMU
qemu-system-x86_64 \
    -enable-kvm \
    -m 512M \
    -smp 1 \
    -drive file="$ISO",media=cdrom,readonly=on \
    -nographic -serial mon:stdio \
    -no-reboot > "$LOG" 2>&1 &
QEMU_PID=$!

echo "QEMU PID: $QEMU_PID"
echo "Waiting for login prompt..."

# Wait for Alpine to boot
TIMEOUT=30
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
    if grep -q "localhost login:" "$LOG" 2>/dev/null; then
        echo ""
        echo "✓ Alpine booted successfully!"
        echo ""
        echo "Boot log (last 12 lines):"
        tail -12 "$LOG"
        echo ""
        echo "Boot time: ~${ELAPSED}s"
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