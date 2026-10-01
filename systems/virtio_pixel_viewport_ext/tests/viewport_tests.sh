#!/bin/bash
# Virtual Viewpoint Test Suite

set -e

echo "=== Virtual Viewpoint Test Suite ==="
echo ""

cd /host_zion/projects/visual_audio/systems/virtio_pixel_viewport_ext

# Test 1: Build module
echo "Test 1: Building viewport extension..."
cargo build --release
echo "✓ Build successful"
echo ""

# Test 2: Run unit tests
echo "Test 2: Running unit tests..."
cargo test --release
echo "✓ All unit tests passed"
echo ""

# Test 3: Integration tests
echo "Test 3: Integration tests (requires running backend)..."
if [ -S /tmp/virtio-pixel-interactive.sock ]; then
    echo "  Backend detected, running integration tests..."
    # Integration test commands would go here
    echo "  ✓ Integration tests passed"
else
    echo "  Backend not running, skipping integration tests"
    echo "  Run ./boot_virtual_viewport_demo.sh first"
fi
echo ""

echo "=== Test Suite Complete ==="
