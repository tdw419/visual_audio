#!/bin/bash
# Minimal test: Boot Alpine rootfs with QEMU directly (no VirtIO-Pixel)

set -e

DISK="alpine_minimal_bootable.img"
KERNEL="/home/jericho/scratch/vmlinuz-virt"

if [ ! -f "$DISK" ]; then
    echo "❌ Disk not found: $DISK"
    exit 1
fi

if [ ! -f "$KERNEL" ]; then
    echo "❌ Kernel not found: $KERNEL"
    echo "Need Linux kernel with virtio drivers"
    exit 1
fi

echo "=== Test Alpine Boot (Direct QEMU, No Backend) ==="
echo "Disk: $DISK"
echo "Kernel: $KERNEL"
echo ""

qemu-system-x86_64 \
    -m 2G \
    -smp 2 \
    -kernel "$KERNEL" \
    -drive "file=$DISK,format=raw,if=virtio" \
    -append "console=ttyS0,115200n8 root=/dev/vda1 ro" \
    -nographic \
    -no-reboot 2>&1 | tee /tmp/test_alpine_direct.log &
QEMU_PID=$!

# Wait for boot or timeout
TIMEOUT=30
ELAPSED=0
echo "Waiting for Alpine boot..."
while [ $ELAPSED -lt $TIMEOUT ]; do
    if grep -q "Welcome to Alpine\|root@.*:/#\|login:" /tmp/test_alpine_direct.log 2>/dev/null; then
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
echo "❌ Boot timeout"
kill $QEMU_PID 2>/dev/null || true
tail -50 /tmp/test_alpine_direct.log
exit 1