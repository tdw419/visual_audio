#!/bin/bash
# Quick verification: extract Ubuntu disk from MKV and boot QEMU

set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MKV_PATH="$REPO_ROOT/visual_audio.mkv"
OUTPUT_DISK="$REPO_ROOT/ubuntu_verify.qcow2"

echo "=================================================="
echo "Ubuntu MKV Boot Verification"
echo "=================================================="
echo "MKV: $MKV_PATH"
echo ""

# Step 1: Extract Ubuntu disk from MKV
echo "[1/2] Extracting Ubuntu disk from MKV..."
python3 "$REPO_ROOT/tools/va_container.py" cat "$MKV_PATH" "ubuntu/desktop/ubuntu-24.04-desktop.qcow2" -o "$OUTPUT_DISK"

EXTRACTED_SIZE=$(stat -f%z "$OUTPUT_DISK" 2>/dev/null || stat -c%s "$OUTPUT_DISK" 2>/dev/null)
echo "Extracted: $EXTRACTED_SIZE bytes"

# Step 2: Boot QEMU
echo ""
echo "[2/2] Booting Ubuntu QEMU (nographic, serial to stdout)..."
echo "Hit Ctrl+A, X to exit QEMU"
echo ""

qemu-system-riscv64 \
  -machine virt \
  -cpu rv64 \
  -m 2048 \
  -smp 2 \
  -bios default \
  -device virtio-net-device,netdev=net0 \
  -netdev user,id=net0,hostfwd=tcp::2222-:22 \
  -drive "file=$OUTPUT_DISK,if=virtio,format=qcow2,id=hd0" \
  -device virtio-blk-pci,drive=hd0 \
  -nographic \
  -serial mon:stdio

echo ""
echo "Boot verification complete"