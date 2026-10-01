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

# Auto-detect a pixel_layer.py stack for this container (.pixel_layers/ next to
# this script). If its base_container matches, layer edits get baked into the
# raw export below — no separate `flatten` step needed for them to boot live.
LAYERS_DIR=""
STACK_FILE="${SCRIPT_DIR}/.pixel_layers/layer_stack.json"
if [ -f "${STACK_FILE}" ]; then
    STACK_BASE="$(python3 -c "import json; print(json.load(open('${STACK_FILE}')).get('base_container',''))" 2>/dev/null)"
    RESOLVED_CONTAINER="$(cd "${CONTAINER_DIR}" 2>/dev/null && pwd)"
    if [ -n "${STACK_BASE}" ] && [ "${STACK_BASE}" = "${RESOLVED_CONTAINER}" ]; then
        LAYERS_DIR="${SCRIPT_DIR}/.pixel_layers"
        echo "Layer stack detected: ${LAYERS_DIR}"
    fi
fi

# Export to raw if not already done, or if the container or the layer stack
# changed since the last export.
NEED_EXPORT=0
if [ ! -f "${RAW_PATH}" ] || [ "${CONTAINER_DIR}" -nt "${RAW_PATH}" ]; then
    NEED_EXPORT=1
fi
if [ -n "${LAYERS_DIR}" ] && [ -n "$(find "${LAYERS_DIR}" -newer "${RAW_PATH}" 2>/dev/null)" ]; then
    NEED_EXPORT=1
fi

if [ "${NEED_EXPORT}" -eq 1 ]; then
    echo "Exporting ${SECTION} to raw image..."
    if [ -n "${LAYERS_DIR}" ]; then
        python3 tools/pxc1_raw_export.py "${CONTAINER_DIR}" "${SECTION}" "${RAW_PATH}" --layers "${LAYERS_DIR}"
    else
        python3 tools/pxc1_raw_export.py "${CONTAINER_DIR}" "${SECTION}" "${RAW_PATH}"
    fi
    echo
fi

# Check if raw image exists
if [ ! -f "${RAW_PATH}" ]; then
    echo "Error: Raw image not found at ${RAW_PATH}"
    exit 1
fi

# Every instance, including 0, boots from its own COW snapshot layered on
# the shared raw export. RAW_PATH must stay a read-only backing file: any
# instance booting it directly (format=raw) would mutate it in place and
# silently corrupt every other instance's COW snapshot, which assumes that
# file never changes underneath them (this happened in practice).
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

DRIVE_IMAGE="${COW_PATH}"
DRIVE_FORMAT="qcow2"

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
    -virtfs local,path=/home/jericho/zion,security_model=mapped,mount_tag=host_zion \
    -pidfile "${SOCK_PREFIX}/qemu.pid" \
    -name "pixel_linux_${INSTANCE_ID}"