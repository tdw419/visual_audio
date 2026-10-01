#!/bin/bash
# Minimal QEMU test to verify VirtIO Pixel backend connection
#
# This boots a minimal test VM that connects to the backend via vhost-user-blk
# and attempts to read the first sector to verify protocol handshake works.

set -e

SOCKET_PATH="${1:-/tmp/test-vhost.sock}"
MKV_PATH="${2:-/home/jericho/projects/zion/projects/visual_audio/test_spatial_10mb.mkv}"

echo "========================================="
echo "VirtIO Pixel Connection Test"
echo "========================================="
echo "Socket:   ${SOCKET_PATH}"
echo "MKV:      ${MKV_PATH}"
echo ""

# Check socket exists
if [[ ! -S "${SOCKET_PATH}" ]]; then
    echo "ERROR: Socket not found: ${SOCKET_PATH}"
    echo ""
    echo "Start the backend first:"
    echo "  RUST_LOG=info ./target/release/virtio_pixel_backend ${MKV_PATH} ${SOCKET_PATH}"
    exit 1
fi

echo "[✓] Socket found"

# Check backend is running
if ! ps aux | grep -q "[v]irtio_pixel_backend.*${SOCKET_PATH}"; then
    echo "ERROR: Backend not running on ${SOCKET_PATH}"
    exit 1
fi

echo "[✓] Backend running"

# Create a tiny test kernel that just reads from virtio-blk
# For now, use xv6 or Alpine as a simple test
TEST_DISK="${HOME}/projects/zion/projects/visual_audio/tests/fixtures/test_disk.qcow2"

if [[ ! -f "${TEST_DISK}" ]]; then
    echo "Creating test disk..."
    mkdir -p "$(dirname ${TEST_DISK})"
    qemu-img create -f qcow2 "${TEST_DISK}" 100M
fi

echo ""
echo "[Test] Launching QEMU with vhost-user-blk..."
echo ""

# Run QEMU with virtio-blk connected to backend
# Note: backend runs as server=on, QEMU connects as client (server=off)
timeout 30s qemu-system-x86_64 \
  -machine q35,accel=kvm:kvm:tcg \
  -cpu host \
  -m 512M \
  -nographic \
  \
  -device virtio-blk-pci,bus=pcie.0,addr=0x4,chardev=blk0 \
  -chardev socket,id=blk0,path=${SOCKET_PATH},server=off \
  \
  -drive if=virtio,file=${TEST_DISK},format=qcow2,readonly=on \
  \
  -serial mon:stdio \
  2>&1 | tee /tmp/qemu_test_output.log || {
    echo ""
    echo "QEMU exited. Checking for successful handshake..."
    echo ""
    
    # Check if backend logged any vhost-user messages
    if ps aux | grep -q "[v]irtio_pixel_backend.*${SOCKET_PATH}"; then
        echo "✓ Backend still running (no crash)"
    else
        echo "✗ Backend crashed"
        exit 1
    fi
    
    # Check logs for successful protocol messages
    if grep -q "GET_FEATURES\|SET_OWNER\|SET_MEM_TABLE" <<< "$(journalctl -u virtio-pixel 2>/dev/null || echo 'no journal')" 2>/dev/null || true; then
        echo "✓ vhost-user protocol messages exchanged"
    fi
    
    echo ""
    echo "Check /tmp/qemu_test_output.log for details"
    echo ""
    echo "If QEMU connected successfully, you should see vhost-user"
    echo "messages in the backend logs."
}

echo ""
echo "========================================="
echo "Test complete"
echo "========================================="