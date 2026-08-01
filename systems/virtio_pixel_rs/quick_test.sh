#!/bin/bash
# Quick vhost-user-blk test with QEMU
#
# Tests basic vhost-user protocol handshake without full boot

set -e

SOCKET_PATH="/tmp/test-vhost.sock"
MKV_PATH="${1:-/home/jericho/projects/zion/projects/visual_audio/test_spatial_10mb.mkv}"

echo "========================================="
echo "VirtIO Pixel Quick Test"
echo "========================================="
echo "Socket:   ${SOCKET_PATH}"
echo "MKV:      ${MKV_PATH}"
echo ""

# Check backend is running
if ! ps aux | grep -q "[v]irtio_pixel_backend.*${SOCKET_PATH}"; then
    echo "ERROR: Backend not running"
    echo "Start with: RUST_LOG=info ./target/release/virtio_pixel_backend ${MKV_PATH} ${SOCKET_PATH}"
    exit 1
fi

echo "[✓] Backend running"
echo ""
echo "[Test] Launching QEMU with vhost-user-blk-pci..."
echo ""

# Try direct vhost-user-blk-pci (no chardev needed)
timeout 20s qemu-system-x86_64 \
  -machine q35,accel=kvm:kvm:tcg \
  -cpu host \
  -m 512M \
  -nographic \
  -nodefaults \
  -kernel /dev/null \
  \
  -device vhost-user-blk-pci,num-queues=1,addr=0x4 \
  \
  -chardev socket,id=char0,path=${SOCKET_PATH},server=off 2>&1 || true

echo ""
echo "Check backend output above for vhost-user protocol messages"
echo "(GET_FEATURES, SET_OWNER, SET_MEM_TABLE, etc.)"