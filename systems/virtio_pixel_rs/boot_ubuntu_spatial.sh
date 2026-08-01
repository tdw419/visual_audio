#!/bin/bash
# End-to-end boot test for VirtIO Pixel vhost-user backend
#
# This script boots Ubuntu Desktop entirely from a spatial MKV container
# via the zero-copy, GPU-native VirtIO Pixel storage bridge.
#
# Usage: ./boot_ubuntu_spatial.sh [mkv_path] [qemu_args...]

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="${PROJECT_ROOT}/systems/virtio_pixel_rs"
SOCKET_PATH="/tmp/virtio-pixel-spatial.sock"
BACKEND_PID=""
QEMU_PID=""

# Default MKV path
MKV_PATH="${1:-${PROJECT_ROOT}/visual_audio.mkv}"

# Additional QEMU arguments
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
    echo "Available MKV files:"
    find "${PROJECT_ROOT}" -name "*.mkv" -type f -exec ls -lh {} \; 2>/dev/null | awk '{print "  " $9 " (" $5 ")"}'
    exit 1
fi

# Check backend is built
if [[ ! -x "${BACKEND_DIR}/target/release/virtio_pixel_backend" ]]; then
    echo "Building Rust backend..."
    cd "${BACKEND_DIR}"
    cargo build --release
fi

# Cleanup function
cleanup() {
    echo ""
    echo "Cleaning up..."
    if [[ -n "${QEMU_PID}" ]]; then
        kill "${QEMU_PID}" 2>/dev/null || true
        wait "${QEMU_PID}" 2>/dev/null || true
    fi
    if [[ -n "${BACKEND_PID}" ]]; then
        kill "${BACKEND_PID}" 2>/dev/null || true
        wait "${BACKEND_PID}" 2>/dev/null || true
    fi
    rm -f "${SOCKET_PATH}"
}

trap cleanup EXIT INT TERM

# Start Rust backend
echo "[1] Starting VirtIO Pixel backend..."
cd "${BACKEND_DIR}"
RUST_LOG=info ./target/release/virtio_pixel_backend "${MKV_PATH}" "${SOCKET_PATH}" &
BACKEND_PID=$!

echo "    Backend PID: ${BACKEND_PID}"
echo "    Waiting for socket..."
sleep 3

# Check socket
if [[ ! -S "${SOCKET_PATH}" ]]; then
    echo "ERROR: Socket not created: ${SOCKET_PATH}"
    echo "Backend output:"
    ps -p "${BACKEND_PID}" -o pid,cmd 2>/dev/null || echo "Backend died"
    exit 1
fi

echo "    Socket ready: ${SOCKET_PATH}"

# Launch QEMU
echo ""
echo "[2] Launching QEMU with vhost-user-blk..."
echo ""

exec qemu-system-x86_64 \
  -machine q35,accel=kvm:kvm:tcg \
  -cpu host \
  -m 2G \
  -smp 2 \
  \
  -device virtio-blk-pci,bus=pcie.0,addr=0x4,chardev=blk0 \
  -chardev socket,id=blk0,path=${SOCKET_PATH},server=off \
  \
  -drive if=virtio,file=${PROJECT_ROOT}/boot_images/ubuntu-24.04-desktop.qcow2,readonly=on,format=qcow2 \
  \
  -display gtk \
  -serial mon:stdio \
  -monitor telnet:127.0.0.1:4444,server,nowait \
  ${QEMU_ARGS}