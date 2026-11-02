#!/bin/bash
# Full Ubuntu boot verification from MKV-extracted disk
# Based on the working boot command from boot_mkv_works.py

set -e

DISK="/tmp/ubuntu_test.qcow2"
TIMEOUT=60

echo "=================================================="
echo "Ubuntu Boot Verification (MKV-extracted disk)"
echo "=================================================="
echo "Disk: $DISK ($(stat -f%z "$DISK" 2>/dev/null || stat -c%s "$DISK" 2>/dev/null) bytes)"
echo "Timeout: ${TIMEOUT}s"
echo ""

timeout ${TIMEOUT}s qemu-system-riscv64 \
  -machine virt \
  -cpu rv64 \
  -m 2048 \
  -smp 2 \
  -bios default \
  -device virtio-gpu-device \
  -device virtio-net-device,netdev=net0 \
  -netdev user,id=net0,hostfwd=tcp::2222-:22 \
  -drive "file=$DISK,if=virtio,format=qcow2" \
  -nographic \
  -serial mon:stdio 2>&1 || echo "[Timeout reached]"

echo ""
echo "=================================================="
echo "Verification complete"
echo "=================================================="