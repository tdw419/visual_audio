#!/bin/bash
# Build a 15GB Ubuntu Desktop Image and encode it into PXC1 Hilbert pixels

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

# Config
SOURCE_RAW="ubuntu-24.04-server-cloudimg-amd64.raw"
DESKTOP_RAW="ubuntu-desktop-15g.raw"
INITRAMFS="initramfs-cognitive/output/initramfs-cognitive.gz"
GGUF="$HOME/.cache/visual_audio/cognitive/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"
OUTPUT_DIR="ubuntu_desktop_pxc1_v1"

echo "=== 1. Preparing 15GB Desktop Image ==="
if [ ! -f "$DESKTOP_RAW" ]; then
    echo "Creating 15G raw disk..."
    qemu-img create -f raw "$DESKTOP_RAW" 15G
    
    echo "Expanding source image into 15G disk..."
    # Depending on the source partition layout, usually partition 1 is rootfs. 
    # Use virt-resize to copy and expand the filesystem natively
    virt-resize --expand /dev/sda1 "$SOURCE_RAW" "$DESKTOP_RAW"
    
    echo "Installing ubuntu-desktop-minimal via libguestfs (This will take 10-20 minutes)..."
    virt-customize -a "$DESKTOP_RAW" \
        --memsize 4096 \
        --network \
        --run-command 'apt-get update' \
        --run-command 'DEBIAN_FRONTEND=noninteractive apt-get install -y ubuntu-desktop-minimal' \
        --run-command 'apt-get clean'
else
    echo "Found existing $DESKTOP_RAW, skipping generation."
fi

echo ""
echo "=== 2. Compiling PXC1 Encoder ==="
# We refactored pxc1-encode to stream files so it doesn't OOM on 15GB
cargo build --release --manifest-path tools/pxc1/Cargo.toml

echo ""
echo "=== 3. Encoding Desktop Rootfs into Hilbert Pixels ==="
echo "This will encode 15GB of raw data into PXC1 PNG frames. This will take some time."

tools/pxc1/target/release/pxc1-encode \
    "$OUTPUT_DIR" \
    rootfs "$DESKTOP_RAW" \
    initramfs "$INITRAMFS" \
    gguf "$GGUF"

echo ""
echo "=== Desktop PXC1 encoding complete! ==="
echo "Container ready at: $OUTPUT_DIR/"
echo "Update interactive_ubuntu_pixel.sh to point CONTAINER_DIR to $OUTPUT_DIR to boot it."
