#!/bin/bash
#
# pixel_boot.sh - Boot a pixel container as raw image
#
# Usage:
#   ./pixel_boot.sh <container_dir> <section> [instance_id]
#
# Examples:
#   ./pixel_boot.sh ubuntu_desktop_pxc1_v1 rootfs
#   ./pixel_boot.sh ubuntu_desktop_pxc1_v1 rootfs 1  # Instance 1 (port 2224)
#   ./pixel_boot.sh ubuntu_desktop_pxc1_v1 rootfs 2  # Instance 2 (port 2226)
#

set -eo pipefail

CONTAINER_DIR="${1:-ubuntu_desktop_pxc1_v1}"
SECTION="${2:-rootfs}"
INSTANCE_ID="${3:-0}"

# Configuration - use project directory for storage, not /tmp (avoids space issues)
# Each instance forwards two host ports (SSH + HTTP writeback daemon),
# so instances must be spaced 2 apart or instance N's second port
# collides with instance N+1's first port.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTANCE_DIR="${SCRIPT_DIR}/.pixel_instances/${INSTANCE_ID}"
SOCK_PREFIX="${INSTANCE_DIR}"
RAW_PATH="${SOCK_PREFIX}/${SECTION}.raw"
BASE_PORT=$((2222 + INSTANCE_ID * 2))

# Delay option for staggered startup (useful for multi-instance boot)
DELAY_SECONDS=0
for arg in "$@"; do
    if [ "$arg" = "--delay" ]; then
        DELAY_SECONDS=2
        echo "Staggered startup: will sleep ${DELAY_SECONDS}s before boot"
        break
    fi
done

echo "=== Pixel Boot - Instance ${INSTANCE_ID} ==="
echo "Container: ${CONTAINER_DIR}"
echo "Section: ${SECTION}"
echo "Instance ID: ${INSTANCE_ID}"
echo "Base port: ${BASE_PORT}"
echo "Raw path: ${RAW_PATH}"
echo

# Create instance directory
mkdir -p "${SOCK_PREFIX}"

# Export to raw if not already done
if [ ! -f "${RAW_PATH}" ] || [ "${CONTAINER_DIR}" -nt "${RAW_PATH}" ]; then
    echo "Exporting ${SECTION} to raw image..."
    python3 tools/pxc1_raw_export.py "${CONTAINER_DIR}" "${SECTION}" "${RAW_PATH}"
    echo
fi

# Check if raw image exists
if [ ! -f "${RAW_PATH}" ]; then
    echo "Error: Raw image not found at ${RAW_PATH}"
    exit 1
fi

# For multi-instance, create COW snapshot to avoid write lock contention
if [ "${INSTANCE_ID}" != "0" ]; then
    COW_PATH="${SOCK_PREFIX}/${SECTION}.qcow2"
    
    if [ ! -f "${COW_PATH}" ] || [ "${RAW_PATH}" -nt "${COW_PATH}" ]; then
        echo "Creating copy-on-write snapshot..."
        qemu-img create -f qcow2 -F raw -b "${RAW_PATH}" "${COW_PATH}" 2>&1 | (grep -v "^Formatting" || true)
        if [ "${PIPESTATUS[0]}" -ne 0 ]; then
            echo "Error: qemu-img create failed"
            exit 1
        fi
        echo
    fi
    
    # Use COW snapshot for instance
    DRIVE_IMAGE="${COW_PATH}"
    DRIVE_FORMAT="qcow2"
else
    # Instance 0 uses raw directly (master)
    DRIVE_IMAGE="${RAW_PATH}"
    DRIVE_FORMAT="raw"
fi

# Get image size
IMAGE_SIZE=$(stat -f%z "${DRIVE_IMAGE}" 2>/dev/null || stat -c%s "${DRIVE_IMAGE}" 2>/dev/null)
echo "Image size on disk: $((IMAGE_SIZE / 1024)) KB"
echo

# Check if port is available
if lsof -i ":${BASE_PORT}" > /dev/null 2>&1 || lsof -i ":$((BASE_PORT + 1))" > /dev/null 2>&1; then
    echo "Error: Port ${BASE_PORT} or $((BASE_PORT + 1)) already in use"
    echo "Use a different instance ID"
    exit 1
fi

# Boot QEMU
echo "Starting QEMU..."
echo "Drive: ${DRIVE_IMAGE} (${DRIVE_FORMAT})"
echo

# Stagger startup for multi-instance
if [ "${DELAY_SECONDS}" -gt 0 ]; then
    sleep "${DELAY_SECONDS}"
fi

qemu-system-x86_64 \
    -drive file="${DRIVE_IMAGE}",format="${DRIVE_FORMAT}",if=virtio \
    -m 4G \
    -smp 4 \
    -nographic \
    -serial "mon:stdio" \
    -net nic,model=virtio \
    -net "user,hostfwd=tcp::${BASE_PORT}-:22,hostfwd=tcp::$((BASE_PORT + 1))-:8769" \
    -pidfile "${SOCK_PREFIX}/qemu.pid" \
    -name "pixel_linux_${INSTANCE_ID}"