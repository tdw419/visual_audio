#!/bin/bash
# Encode Ubuntu 24.04 Server + Cognitive Payload as PXC1 container

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

# Source files
ROOTFS="$PROJECT_ROOT/ubuntu-24.04-server-cloudimg-amd64.raw"
INITRAMFS="$PROJECT_ROOT/initramfs-cognitive/output/initramfs-cognitive.gz"
GGUF="$HOME/.cache/visual_audio/cognitive/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"
OUTPUT="$PROJECT_ROOT/ubuntu_cognitive_pxc1_v1"

# Check inputs
for f in "$ROOTFS" "$INITRAMFS" "$GGUF"; do
    if [ ! -f "$f" ]; then
        echo "Error: $f not found"
        exit 1
    fi
done

echo "=== PXC1 Ubuntu Cognitive Container ==="
echo "Rootfs: $ROOTFS ($(du -h "$ROOTFS" | cut -f1))"
echo "Initramfs: $INITRAMFS ($(du -h "$INITRAMFS" | cut -f1))"
echo "GGUF: $GGUF ($(du -h "$GGUF" | cut -f1))"
echo "Output: $OUTPUT/"
echo

# Encode
cargo run --release --manifest-path tools/pxc1/Cargo.toml --bin pxc1-encode -- \
    "$OUTPUT" \
    rootfs "$ROOTFS" \
    initramfs "$INITRAMFS" \
    gguf "$GGUF"

echo
echo "=== Verifying ==="
cargo run --release --manifest-path tools/pxc1/Cargo.toml --bin pxc1-verify -- "$OUTPUT"

echo
echo "=== Extracting test sections ==="
echo "Extracting initramfs to /tmp/test_initramfs.gz..."
cargo run --release --manifest-path tools/pxc1/Cargo.toml --bin pxc1-decode -- "$OUTPUT" initramfs /tmp/test_initramfs.gz

echo "Extracting gguf to /tmp/test_tinyllama.gguf..."
cargo run --release --manifest-path tools/pxc1/Cargo.toml --bin pxc1-decode -- "$OUTPUT" gguf /tmp/test_tinyllama.gguf

echo
echo "=== Verification ==="
echo "Comparing extracted files:"
diff <(md5sum "$INITRAMFS") <(md5sum /tmp/test_initramfs.gz) && echo "✓ Initramfs match" || echo "✗ Initramfs mismatch"
diff <(md5sum "$GGUF") <(md5sum /tmp/test_tinyllama.gguf) && echo "✓ GGUF match" || echo "✗ GGUF mismatch"

echo
echo "Done! Container ready at: $OUTPUT/"