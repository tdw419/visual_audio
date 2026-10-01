#!/bin/bash
# build_ubuntu_cognitive_pxc1.sh - One-shot reproducible container build
# Inputs: ubuntu-24.04-server-cloudimg-amd64.raw
# Output: ubuntu_cognitive_pxc1_v2/ directory with patched rootfs, initramfs, GGUF

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

# Config
SOURCE_RAW="ubuntu-24.04-server-cloudimg-amd64.raw"
PATCHED_RAW="ubuntu-24.04-server-cloudimg-amd64-patched.raw"
INITRAMFS="initramfs-cognitive/output/initramfs-cognitive.gz"
GGUF="$HOME/.cache/visual_audio/cognitive/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"
OUTPUT_DIR="ubuntu_cognitive_pxc1_v2"

# Check dependencies
if ! command -v virt-customize &> /dev/null; then
    echo "Error: virt-customize not found. Please install libguestfs-tools."
    exit 1
fi

echo "=== 1. Preparing Patched Rootfs ==="
if [ ! -f "$SOURCE_RAW" ]; then
    echo "Error: $SOURCE_RAW not found!"
    exit 1
fi

echo "Copying source raw image to prevent mutating the original..."
cp "$SOURCE_RAW" "$PATCHED_RAW"

echo "Patching /etc/fstab to remove /boot/efi dependencies..."
virt-customize -a "$PATCHED_RAW" \
    --run-command 'sed -i "/\/boot\/efi/s/^/#/" /etc/fstab' \
    --run-command 'sed -i "s/^\(UUID=.*\/boot[[:space:]]\+ext4[[:space:]]\+defaults\)/\1,nofail/" /etc/fstab'

echo ""
echo "=== 2. Verifying Encoder Build ==="
cargo build --release --manifest-path tools/pxc1/Cargo.toml

echo ""
echo "=== 3. Encoding Rootfs into Hilbert Pixels (PXC1 v2) ==="
rm -rf "$OUTPUT_DIR"
tools/pxc1/target/release/pxc1-encode \
    "$OUTPUT_DIR" \
    rootfs "$PATCHED_RAW" \
    initramfs "$INITRAMFS" \
    gguf "$GGUF"

echo ""
echo "=== Verification ==="
tools/pxc1/target/release/pxc1-verify "$OUTPUT_DIR"

echo ""
echo "=== Build Complete! ==="
echo "Output Container: $OUTPUT_DIR/"
