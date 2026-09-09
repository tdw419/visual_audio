#!/bin/bash
#
# sync_hermes_to_guest_direct.sh - Sync host Hermes to guest by direct filesystem access
# Mounts the guest's raw image and copies files directly
#

set -e

INSTANCE_ID="${1:-0}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAW_PATH="${SCRIPT_DIR}/.pixel_instances/${INSTANCE_ID}/rootfs.raw"

echo "=== Hermes Sync: Host → Guest (Direct Mount) ==="
echo "Guest instance: ${INSTANCE_ID}"
echo "Raw image: ${RAW_PATH}"
echo

# Check if raw image exists
if [ ! -f "${RAW_PATH}" ]; then
    echo "✗ Raw image not found at ${RAW_PATH}"
    echo "Run: ./pixel_boot.sh ubuntu_desktop_pxc1_v1 rootfs ${INSTANCE_ID}"
    exit 1
fi

# Stop the guest if running
if [ -f "${SCRIPT_DIR}/.pixel_instances/${INSTANCE_ID}/qemu.pid" ]; then
    PID=$(cat "${SCRIPT_DIR}/.pixel_instances/${INSTANCE_ID}/qemu.pid")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "Stopping guest instance ${INSTANCE_ID}..."
        kill "$PID"
        sleep 3
    fi
fi

# Setup loop device
echo "Setting up loop device..."
LOOPDEV=$(sudo losetup --show -f "${RAW_PATH}")
sudo partprobe "${LOOPDEV}"
echo "✓ Loop device: ${LOOPDEV}"

# Mount root partition
echo "Mounting root partition..."
sudo mkdir -p /mnt/pixel_guest
sudo mount "${LOOPDEV}p4" /mnt/pixel_guest
echo "✓ Mounted root partition"

# Paths
HOST_HERMES="${HOME}/.hermes"
HOST_SKILLS="${HOST_HERMES}/skills"
HOST_PLUGINS="${HOST_HERMES}/plugins"
GUEST_HERMES="/mnt/pixel_guest/home/ubuntu/.hermes"
GUEST_SKILLS="${GUEST_HERMES}/skills"
GUEST_PLUGINS="${GUEST_HERMES}/plugins"

# Create Hermes directories
echo "Creating Hermes directories..."
sudo mkdir -p "${GUEST_SKILLS}"
sudo mkdir -p "${GUEST_PLUGINS}"
echo "✓ Directories created"

# Sync skills
echo
echo "Syncing skills..."
echo "  Host: ${HOST_SKILLS}"
echo "  Guest: ${GUEST_SKILLS}"

sudo cp "${HOST_SKILLS}"/*.md "${GUEST_SKILLS}/" 2>/dev/null || echo "  No skills found"

SKILL_COUNT=$(sudo ls -1 "${GUEST_SKILLS}"/*.md 2>/dev/null | wc -l)
echo "  Skills synced: ${SKILL_COUNT}"

# Fix ownership
sudo chown -R 1000:1000 "${GUEST_HERMES}"
echo "✓ Ownership fixed"

# Sync plugins
if [ -d "${HOST_PLUGINS}" ] && [ "$(ls -A "${HOST_PLUGINS}" 2>/dev/null)" ]; then
    echo
    echo "Syncing plugins..."
    echo "  Host: ${HOST_PLUGINS}"
    echo "  Guest: ${GUEST_PLUGINS}"
    
    sudo cp -r "${HOST_PLUGINS}"/* "${GUEST_PLUGINS}/"
    sudo chown -R 1000:1000 "${GUEST_PLUGINS}"
    
    PLUGIN_COUNT=$(sudo ls -1 "${GUEST_PLUGINS}" 2>/dev/null | wc -l)
    echo "  Plugins synced: ${PLUGIN_COUNT}"
else
    echo
    echo "  No plugins on host, skipping"
fi

# Unmount
echo
echo "Unmounting..."
sudo umount /mnt/pixel_guest
sudo losetup -d "${LOOPDEV}"
echo "✓ Cleanup complete"

echo
echo "✓ Sync complete!"
echo
echo "Guest instance ${INSTANCE_ID} now has access to:"
echo "  - ${SKILL_COUNT} skills"
echo "  - ${PLUGIN_COUNT:-0} plugins"
echo
echo "Start the guest with:"
echo "  ./pixel_boot.sh ubuntu_desktop_pxc1_v1 rootfs ${INSTANCE_ID}"
echo
echo "Inside guest, verify with:"
echo "  ls -la ~/.hermes/skills/ | head -20"