#!/bin/bash
# Boot Alpine Linux from NBD-served spatial MKV
# Workaround for QEMU 8.2.2 vhost-user bug

set -e

MKV_PATH="${1:-test_data/spatial_boot/alpine_minimal.mkv}"
RAW_PATH="/tmp/alpine_minimal.raw"
NBD_SOCKET="/tmp/spatial-nbd.sock"

cleanup() {
    echo "Cleaning up..."
    qemu-nbd -d /dev/nbd0 2>/dev/null || true
    rm -f "$NBD_SOCKET"
    pkill -f qemu-nbd 2>/dev/null || true
    pkill -f qemu-system-riscv64 2>/dev/null || true
}

trap cleanup EXIT

echo "======================================================================"
echo "Alpine Spatial Boot - NBD Workaround"
echo "======================================================================"
echo "MKV: $MKV_PATH"
echo "RAW: $RAW_PATH"
echo "NBD: $NBD_SOCKET"
echo ""

# Check MKV exists
if [ ! -f "$MKV_PATH" ]; then
    echo "ERROR: MKV file not found: $MKV_PATH"
    echo ""
    echo "Available MKVs in test_data/spatial_boot:"
    ls -lh test_data/spatial_boot/*.mkv 2>/dev/null || echo "  (none found)"
    exit 1
fi

# Extract from MKV if needed
if [ ! -f "$RAW_PATH" ]; then
    echo "Step 1: Extracting MKV to raw image..."
    bash tools/mkv_to_nbd.sh "$MKV_PATH" "$RAW_PATH"
    echo ""
fi

# Verify MBR signature
echo "Step 2: Verifying MBR..."
MBR_SIG=$(xxd -l 2 -s 510 -p "$RAW_PATH")
if [ "$MBR_SIG" = "55aa" ]; then
    echo "  ✓ MBR signature valid (55aa)"
else
    echo "  ✗ MBR signature invalid: $MBR_SIG (expected 55aa)"
    echo ""
    echo "First 64 bytes:"
    xxd -l 64 "$RAW_PATH"
    exit 1
fi
echo ""

# Check boot images
if [ ! -f boot_images/alpine_Image ]; then
    echo "ERROR: Boot kernel not found: boot_images/alpine_Image"
    exit 1
fi

if [ ! -f boot_images/alpine_initrd ]; then
    echo "ERROR: Initramfs not found: boot_images/alpine_initrd"
    exit 1
fi

# Start NBD server
echo "Step 3: Starting NBD server..."
qemu-nbd --socket="$NBD_SOCKET" --format=raw --read-only "$RAW_PATH" &
NBD_PID=$!
echo "  NBD PID: $NBD_PID"

# Wait for socket
sleep 2
if [ ! -S "$NBD_SOCKET" ]; then
    echo "ERROR: NBD socket not created: $NBD_SOCKET"
    kill $NBD_PID
    exit 1
fi
echo "  ✓ NBD socket ready"
echo ""

# Boot QEMU
echo "Step 4: Booting QEMU from NBD..."
echo "  Kernel: boot_images/alpine_Image"
echo "  Initrd: boot_images/alpine_initrd"
echo "  Root:   /dev/vda (NBD)"
echo ""
echo "======================================================================"
echo "QEMU Boot Log"
echo "======================================================================"
echo ""

timeout 60 qemu-system-riscv64 \
    -nographic \
    -machine virt \
    -cpu rv64 \
    -m 512M \
    -drive file=nbd+unix://$NBD_SOCKET,if=virtio,index=0,bootindex=0 \
    -kernel boot_images/alpine_Image \
    -initrd boot_images/alpine_initrd \
    -append "console=ttyS0 earlycon root=/dev/vda rw" \
    -no-reboot 2>&1 | tee /tmp/alpine_nbd_boot.log || true

echo ""
echo "======================================================================"
echo "Boot Log Saved: /tmp/alpine_nbd_boot.log"
echo "======================================================================"

# Check for success
if grep -q "Welcome to Alpine" /tmp/alpine_nbd_boot.log; then
    echo ""
    echo "✓ BOOT SUCCESSFUL!"
    echo ""
    echo "Blocker Resolution:"
    echo "  - QEMU 8.2.2 vhost-user bug bypassed via NBD"
    echo "  - Spatial boot path working"
    echo "  - Ready to proceed with Ubuntu Desktop boot"
else
    echo ""
    echo "⚠ Boot may have failed (check log above)"
    echo ""
    echo "Last 30 lines:"
    tail -30 /tmp/alpine_nbd_boot.log
    exit 1
fi