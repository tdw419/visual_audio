#!/bin/bash
# Verify Golden Image Self-Hosting Build
# Run this after building the golden image to verify all self-hosting components

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

CONTAINER_DIR="ubuntu_desktop_pxc1_v1"

echo "=== Golden Image Self-Hosting Verification ==="
echo ""

# Check if container exists
if [ ! -f "$CONTAINER_DIR/header.json" ]; then
    echo "❌ ERROR: Container not found at $CONTAINER_DIR"
    echo "Run ./build_desktop_pxc1.sh first"
    exit 1
fi

echo "✓ Container exists: $CONTAINER_DIR"
echo ""

# Check PXC1 structure
echo "=== PXC1 Container Structure ==="
FRAME_COUNT=$(ls -1 "$CONTAINER_DIR"/frame_*.png 2>/dev/null | wc -l)
echo "✓ Frames found: $FRAME_COUNT"

if [ -f "$CONTAINER_DIR/header.json" ]; then
    echo "✓ Header file exists"
    # Display basic info from header
    python3 -c "
import json
try:
    with open('$CONTAINER_DIR/header.json') as f:
        header = json.load(f)
    print(f\"  Format: {header.get('format', 'unknown')}\")
    print(f\"  Frame size: {header.get('frame_size', 'unknown')}\")
    print(f\"  Sections: {len(header.get('sections', []))}\")
    total_bytes = sum(s.get('byte_length', 0) for s in header.get('sections', []))
    print(f\"  Total disk: {total_bytes / (1024**3):.2f} GB\")
except Exception as e:
    print(f\"  Could not parse header: {e}\")
" 2>/dev/null || echo "  Could not parse header details"
else
    echo "❌ Header file missing"
fi

if [ -f "$CONTAINER_DIR/.pxc1_delta.jnl" ]; then
    JNL_SIZE=$(stat -c%s "$CONTAINER_DIR/.pxc1_delta.jnl")
    echo "✓ COW journal exists (size: $JNL_SIZE bytes)"
else
    echo "⚠ No COW journal (clean container)"
fi

echo ""

# Check desktop image
echo "=== Desktop Image Build ==="
if [ -f "ubuntu-desktop-15g.raw" ]; then
    DISK_SIZE=$(stat -c%s "ubuntu-desktop-15g.raw")
    echo "✓ Desktop image exists (size: $((DISK_SIZE / 1024**3))GB)"
else
    echo "⚠ Desktop image not found (build may be incomplete)"
fi

echo ""

# Check build components
echo "=== Build Components ==="

# v2 backend
if [ -f "systems/virtio_pixel_rs_v2/target/release/virtio_pixel_backend_v2" ]; then
    BACKEND_SIZE=$(stat -c%s "systems/virtio_pixel_rs_v2/target/release/virtio_pixel_backend_v2")
    echo "✓ v2 backend exists (size: $((BACKEND_SIZE / 1024))KB)"
else
    echo "❌ v2 backend not found - run: cargo build --release --manifest-path systems/virtio_pixel_rs_v2/Cargo.toml"
fi

# Self-host launcher
if [ -f "tools/pixel_self_host_nested_vm.sh" ]; then
    echo "✓ Self-host launcher exists"
else
    echo "❌ Self-host launcher not found"
fi

# Fork tool
if [ -f "tools/pixel_fork_container.sh" ]; then
    echo "✓ Container fork tool exists"
else
    echo "❌ Container fork tool not found"
fi

# PXC1 encoder
if [ -f "tools/pxc1/target/release/pxc1-encode" ]; then
    echo "✓ PXC1 encoder exists"
else
    echo "❌ PXC1 encoder not found - run: cargo build --release --manifest-path tools/pxc1/Cargo.toml"
fi

echo ""

# Check virt-customize availability
echo "=== Build Environment ==="
if command -v virt-customize &> /dev/null; then
    echo "✓ virt-customize available"
else
    echo "❌ virt-customize not found - install: sudo apt-get install libguestfs-tools"
fi

if command -v virt-resize &> /dev/null; then
    echo "✓ virt-resize available"
else
    echo "❌ virt-resize not found - install: sudo apt-get install libguestfs-tools"
fi

if command -v qemu-img &> /dev/null; then
    echo "✓ qemu-img available"
else
    echo "❌ qemu-img not found - install: sudo apt-get install qemu-utils"
fi

echo ""

# Expected container contents
echo "=== Expected Golden Image Contents ==="
echo "The golden image should contain after build:"
echo ""
echo "  /usr/local/bin/"
echo "  ├── virtio_pixel_backend_v2      # v2 pixel backend"
echo "  ├── pixel_self_host_nested_vm.sh # Self-host launcher"
echo "  └── pixel_fork_container.sh       # Zero-copy forker"
echo ""
echo "  /usr/bin/"
echo "  └── qemu-system-x86_64            # QEMU hypervisor"
echo ""
echo "  /var/lib/"
echo "  └── pixel_containers/             # Container storage"
echo ""
echo "  /usr/local/share/doc/pixel-self-hosting/"
echo "  └── README.txt                    # Self-hosting documentation"
echo ""
echo "  /etc/systemd/system/systemd-networkd-wait-online.service.d/"
echo "  └── timeout.conf                  # 5-second timeout"
echo ""

# Build instructions
echo "=== Build Instructions ==="
echo "To build the golden image:"
echo ""
echo "1. Ensure no VMs are using ubuntu_desktop_pxc1_v1"
echo "2. Run: ./build_desktop_pxc1.sh"
echo "3. Wait 25-45 minutes for build to complete"
echo "4. Boot and verify: ./pixel_ubuntu_v2.sh"
echo ""
echo "Build will:"
echo "  • Create 15GB Ubuntu Desktop with minimal UI"
echo "  • Install QEMU, network tools, and self-hosting components"
echo "  • Configure systemd for fast nested boots (5s timeout)"
echo "  • Encode to PXC1 pixel frames"
echo "  • Include complete self-hosting documentation"
echo ""

# Quick test (if container ready)
echo "=== Quick Self-Hosting Test ==="
if [ -f "$CONTAINER_DIR/header.json" ] && [ -f "tools/pixel_self_host_nested_vm.sh" ]; then
    echo "To test self-hosting capability immediately:"
    echo ""
    echo "  1. Boot current VM: ./pixel_ubuntu_v2.sh"
    echo "  2. Inside VM, test forking:"
    echo "     sudo pixel_fork_container.sh ubuntu_desktop_pxc1_v1 /tmp/test_fork"
    echo "  3. Test nested boot:"
    echo "     sudo pixel_self_host_nested_vm.sh --container /tmp/test_fork --quick"
    echo ""
else
    echo "Build golden image first to enable self-hosting tests"
fi

echo "=== Verification Complete ==="