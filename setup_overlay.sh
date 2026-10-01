#!/bin/bash
# Run this INSIDE the Ubuntu VM after boot to set up the overlay disk
# This migrates /home/geometry and /etc/NetworkManager to the fast overlay

set -e

OVERLAY_DISK="/dev/vdb"
OVERLAY_MOUNT="/mnt/overlay"
NEW_HOME="/mnt/overlay/home"
NEW_ETC="/mnt/overlay/etc"

echo "=== Ubuntu Overlay Setup ==="
echo "This will migrate /home/geometry and /etc/NetworkManager to the overlay disk"
echo "Overlay disk: $OVERLAY_DISK"
echo ""

# Check overlay disk exists
if [ ! -b "$OVERLAY_DISK" ]; then
    echo "Error: Overlay disk $OVERLAY_DISK not found"
    echo "Check QEMU startup - is the overlay.qcow2 drive attached?"
    exit 1
fi

# Ask for confirmation
echo "This will:"
echo "  1. Format $OVERLAY_DISK (ALL DATA ON IT WILL BE LOST)"
echo "  2. Copy /home/geometry to $NEW_HOME"
echo "  3. Copy /etc/NetworkManager to $NEW_ETC"
echo "  4. Update /etc/fstab to mount overlay on next boot"
echo ""
read -p "Continue? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo "Aborted"
    exit 0
fi

echo ""
echo "Formatting overlay disk..."
mkfs.ext4 "$OVERLAY_DISK"

echo "Mounting overlay temporarily..."
mkdir -p "$OVERLAY_MOUNT"
mount "$OVERLAY_DISK" "$OVERLAY_MOUNT"

echo "Copying /home/geometry..."
mkdir -p "$NEW_HOME"
cp -a /home/geometry/. "$NEW_HOME/geometry/"
echo "✓ /home/geometry copied"

echo ""
echo "Copying /etc/NetworkManager..."
mkdir -p "$NEW_ETC/NetworkManager"
cp -a /etc/NetworkManager/. "$NEW_ETC/NetworkManager/"
echo "✓ /etc/NetworkManager copied"

echo ""
echo "Updating /etc/fstab..."
cat >> /etc/fstab << 'EOF'

# Overlay disk - fast qcow2 for persistent settings
/dev/vdb    /overlay    ext4    defaults,noatime    0    2
/overlay/home/geometry    /home/geometry    none    bind    0    0
/overlay/etc/NetworkManager    /etc/NetworkManager    none    bind    0    0
EOF
echo "✓ fstab updated"

echo ""
echo "Unmounting..."
umount "$OVERLAY_MOUNT"
rmdir "$OVERLAY_MOUNT"

echo ""
echo "=== Setup Complete ==="
echo "Next steps:"
echo "  1. Create /overlay directory: sudo mkdir /overlay"
echo "  2. Reboot the VM (sudo reboot)"
echo "  3. After reboot, /home/geometry and /etc/NetworkManager will be on the overlay"
echo "  4. Settings saved to these locations will persist immediately (no writeback needed)"
echo ""
echo "Note: The pixel container (main OS) still needs writeback on exit for other changes"