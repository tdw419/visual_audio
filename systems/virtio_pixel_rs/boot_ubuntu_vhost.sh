#!/bin/bash
# Boot Ubuntu from spatial MKV using VirtIO Pixel vhost-user backend
#
# This script launches QEMU with vhost-user-blk device connected to
# the Rust VirtIO Pixel backend that reads disk data from spatial MKV.
#
# Usage: ./boot_ubuntu_vhost.sh [mkv_path] [qemu_args...]

set -e

# Configuration
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="${PROJECT_ROOT}/systems/virtio_pixel_rs"
SOCKET_PATH="/tmp/virtio-pixel-rs.sock"
BACKEND_PID=""
QEMU_PID=""

# Default MKV path (check command line or use visual_audio.mkv)
MKV_PATH="${1:-${PROJECT_ROOT}/visual_audio.mkv}"

# Additional QEMU arguments (skip script path)
shift 2>/dev/null || true
QEMU_ARGS="$@"

echo "========================================="
echo "VirtIO Pixel Spatial Boot"
echo "========================================="
echo "MKV:      ${MKV_PATH}"
echo "Socket:   ${SOCKET_PATH}"
echo "Backend:  ${BACKEND_DIR}"
echo ""

# Check MKV exists
if [[ ! -f "${MKV_PATH}" ]]; then
    echo "ERROR: MKV not found: ${MKV_PATH}"
    echo ""
    echo "Usage: $0 [mkv_path] [qemu_args...]"
    echo ""
    echo "Available MKV files:"
    find "${PROJECT_ROOT}" -name "*.mkv" -type f -exec ls -lh {} \; 2>/dev/null | awk '{print "  " $9 " (" $5 ")"}'
    exit 1
fi

# Check Rust backend is built
if [[ ! -x "${BACKEND_DIR}/target/release/virtio_pixel_backend" ]]; then
    echo "Building Rust backend..."
    cd "${BACKEND_DIR}"
    cargo build --release
fi

# Cleanup function
cleanup() {
    echo ""
    echo "Cleaning up..."
    
    # Kill QEMU
    if [[ -n "${QEMU_PID}" ]]; then
        echo "Stopping QEMU (PID: ${QEMU_PID})..."
        kill "${QEMU_PID}" 2>/dev/null || true
        wait "${QEMU_PID}" 2>/dev/null || true
    fi
    
    # Kill backend
    if [[ -n "${BACKEND_PID}" ]]; then
        echo "Stopping backend (PID: ${BACKEND_PID})..."
        kill "${BACKEND_PID}" 2>/dev/null || true
        wait "${BACKEND_PID}" 2>/dev/null || true
    fi
    
    # Remove socket
    rm -f "${SOCKET_PATH}"
    
    echo "Cleanup complete."
}

# Set cleanup on exit
trap cleanup EXIT INT TERM

# Start Rust backend
echo "[1] Starting VirtIO Pixel backend..."
cd "${BACKEND_DIR}"
RUST_LOG=info ./target/release/virtio_pixel_backend "${MKV_PATH}" "${SOCKET_PATH}" &
BACKEND_PID=$!

echo "    Backend PID: ${BACKEND_PID}"
echo "    Waiting for socket..."
sleep 2  # Give backend time to start

# Check socket was created
if [[ ! -S "${SOCKET_PATH}" ]]; then
    echo "ERROR: Socket not created: ${SOCKET_PATH}"
    echo "Backend output:"
    wait "${BACKEND_PID}" || true
    exit 1
fi

echo "    Socket ready: ${SOCKET_PATH}"

# Launch QEMU
echo ""
echo "[2] Launching QEMU with vhost-user-blk..."
echo ""

QEMU_CMD="qemu-system-x86_64 \
  -machine q35,accel=kvm:kvm:tcg \
  -cpu host \
  -m 2G \
  -object memory-backend-memfd,id=mem,size=2G,share=on \
  -numa node,memdev=mem \
  -smp 2 \
  \
  -device vhost-user-blk-pci,bus=pcie.0,addr=0x4,chardev=blk0,num-queues=1 \
  -chardev socket,id=blk0,path=${SOCKET_PATH},server=off \
  \
  -drive if=virtio,file=${PROJECT_ROOT}/boot_images/ubuntu-24.04-desktop.qcow2,readonly=on,format=qcow2 \
  \
  -display gtk \
  -serial mon:stdio \
  -monitor telnet:127.0.0.1:4444,server,nowait \
  ${QEMU_ARGS}"

echo "QEMU Command:"
echo "${QEMU_CMD}"
echo ""

# Run QEMU
exec ${QEMU_CMD}