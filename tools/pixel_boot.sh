#!/bin/bash
# Minimal pixel-native boot: export a PXC1 section to a raw disk image and
# boot it with plain QEMU. No vhost-user backend, no Rust runtime, no
# initramfs surgery — PXC1's row-major byte-to-pixel mapping means a
# section's frames concatenate directly into a valid boot disk.
#
# Usage: pixel_boot.sh <container_dir> [section] [ssh_port]
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTAINER="${1:?usage: pixel_boot.sh <container_dir> [section] [ssh_port]}"
SECTION="${2:-rootfs}"
SSH_PORT="${3:-2222}"
OUT="/tmp/$(basename "$CONTAINER")_${SECTION}.raw"

echo "=== Pixel Boot (raw export, no backend) ==="
echo "Container: $CONTAINER"
echo "Section:   $SECTION"
echo "SSH:       ssh -p $SSH_PORT <user>@127.0.0.1"
echo "To exit QEMU: Ctrl-A, then X"
echo "============================================"
echo ""

if [ ! -f "$OUT" ]; then
    python3 "$SCRIPT_DIR/pxc1_raw_export.py" "$CONTAINER" "$SECTION" "$OUT"
else
    echo "Reusing existing export: $OUT (delete it to force re-export)"
fi

qemu-system-x86_64 \
    -m 4G -smp 4 -cpu host -enable-kvm \
    -drive file="$OUT",format=raw,if=virtio \
    -netdev user,id=net0,hostfwd=tcp::${SSH_PORT}-:22 \
    -device virtio-net-pci,netdev=net0 \
    -serial stdio
